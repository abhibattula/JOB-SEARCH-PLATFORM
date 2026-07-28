"""016 (T003, R2/R7): the bounded background drafter.

The ONLY component allowed to invoke generation for form questions. The
bridge decide loop and every message handler stay model-free (R1): they
call `ensure()` (fire-and-forget) and read `answer_for()`; completed
drafts land here first, then flow to the answer bank and the page.

Guarantees (contracts/drafter-api.md):
- one draft per (job, normalized question) per session — the direct fix
  for the observed infinite re-draft loop;
- bounded concurrency (2 workers) feeding the serialized inference owner;
- validated output (option membership / maxlength) — never prose into a
  choice field;
- sensitive questions NEVER generate (structural replacement for the
  removed human approval gate);
- exponential backoff on failure (30 s → ×2 → 600 s cap), reset once per
  explicit user Fill-again;
- completion side-effect order: cache (+version bump) → bank auto-save →
  on-complete callbacks (ledger clear + rescan push are registered by the
  backends, keeping this module free of transport imports).
"""
from __future__ import annotations

import logging
import queue
import re
import threading
import time

from . import fields as _fields_mod

log = logging.getLogger(__name__)

POOL_SIZE = 2
_DEFAULT_BACKOFF_BASE_S = 30.0
_DEFAULT_BACKOFF_CAP_S = 600.0

# 017 (R2, FR-002/FR-003): generation is bounded. The drafter is already
# idempotent per question — `ensure` schedules at most one draft per key and
# the 2026-07-28 live run's activity log confirms one entry per question — so
# these are GUARDS, not repairs. A question that keeps failing ends up with
# the human instead of retrying forever, and no single application can spend
# unbounded model time.
MAX_ATTEMPTS_PER_QUESTION = 2
MAX_DRAFTS_PER_JOB = 40

# Question classes the model must NEVER answer. Left unfilled and flagged
# for the human, or answered from the applicant's own stored values.
#
# 017 renamed this from SENSITIVE_TAGS: "sensitive" stopped describing the
# set once the applicant's own history joined it. An "offer deadlines"
# question is not private — it is simply unknowable from a resume. The old
# name is kept as an alias so 016's vocabulary and tests keep working.
NEVER_GENERATED_TAGS = {
    # legally sensitive / voluntary self-identification
    "eeo_disclosure", "demographics", "disability", "veteran_status",
    "selfid_gender", "selfid_race", "selfid_veteran", "selfid_disability",
    "selfid_orientation", "pronouns",
} | set(_fields_mod.FACTUAL_HISTORY_TAGS)

SENSITIVE_TAGS = NEVER_GENERATED_TAGS  # 016 name, retained

# Auto-saved answers for these tags are scoped to their job — a "why this
# company" essay must never auto-fill another company's form (spec
# clarification 2026-07-27). Everything else saves as reusable fact.
JOB_SCOPED_TAGS = {"cover_letter", "free_text_unknown"}

_lock = threading.Lock()
_records: dict[tuple[int, str], dict] = {}
_tasks: queue.Queue | None = None
_workers: list[threading.Thread] = []
_cache_version = 0
_backoff_base_s = _DEFAULT_BACKOFF_BASE_S
_backoff_cap_s = _DEFAULT_BACKOFF_CAP_S
_max_attempts = MAX_ATTEMPTS_PER_QUESTION
_max_drafts_per_job = MAX_DRAFTS_PER_JOB
# job_id -> generations scheduled this session (successful or not)
_job_generations: dict[int, int] = {}

_generator_override = None
_bank_save_override = None
_on_complete: list = []


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip()).casefold()


def _key(job_id: int, question: str) -> tuple[int, str]:
    return (int(job_id), normalize_question(question))


def _default_generator(question: str, descriptor_ctx: dict, profile: dict):
    """Production generation — the descriptor-aware suggester (T012):
    options → pick-one, combobox → short literal label, prose → maxlength-
    bounded. Post-validation happens in _validate regardless."""
    from . import answer_bank

    return answer_bank.suggest(question, descriptor_ctx.get("tag"), profile,
                               descriptor_ctx=descriptor_ctx)


def _default_bank_save(*, question: str, answer: str, tag: str,
                       origin: str, job_id: int | None) -> None:
    from . import answer_bank

    answer_bank.save_auto(question=question, answer=answer, tag=tag,
                          origin=origin, job_id=job_id)


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def _validate(answer: str | None, descriptor_ctx: dict):
    """Returns (ok, canonical_answer_or_None, fail_reason)."""
    if not answer or not str(answer).strip():
        return False, None, "empty"
    answer = str(answer).strip()
    # 017 (R4, FR-006): the model declined because the applicant's own
    # material does not answer the question. Terminal — retrying cannot
    # conjure a fact, and the question belongs to the human.
    from . import answer_bank as _bank

    if _bank.is_refusal(answer):
        return False, None, "cannot_answer"
    options = descriptor_ctx.get("options") or []
    if options:
        wanted = _normalize_for_match(answer)
        for option in options:
            if _normalize_for_match(option) == wanted:
                return True, option, None  # canonical option text wins
        return False, None, "no_valid_option"
    if (descriptor_ctx.get("widget") or "") == "custom_combobox":
        # options unknown until fill time — the answer must LOOK like an
        # option label (the harvest fuzzy-matches it on the page)
        if len(answer.split()) > 4:
            return False, None, "not_an_option_label"
    maxlength = descriptor_ctx.get("maxlength")
    if maxlength and len(answer) > int(maxlength):
        answer = answer[:int(maxlength)].rstrip()
    return True, answer, None


def _worker_loop(tasks: queue.Queue) -> None:
    global _cache_version
    while True:
        item = tasks.get()
        if item is None:  # shutdown sentinel
            return
        key, question, descriptor_ctx, profile = item
        generator = _generator_override or _default_generator
        try:
            raw = generator(question, descriptor_ctx, profile)
        except Exception as exc:  # noqa: BLE001 — a draft may never crash a worker
            log.warning("draft generation failed for %r", question,
                        exc_info=True)
            raw, gen_error = None, f"generator_error: {exc}"
        else:
            gen_error = None
        ok, canonical, reason = _validate(raw, descriptor_ctx)
        if gen_error is not None:
            ok, reason = False, "generator_error"
        if ok:
            with _lock:
                rec = _records.get(key)
                if rec is None:
                    continue  # reset happened mid-flight
                rec.update(state="done", answer=canonical, reason=None)
                _cache_version += 1
            _run_completion_effects(key[0], question, canonical,
                                    descriptor_ctx)
        else:
            with _lock:
                rec = _records.get(key)
                if rec is None:
                    continue
                rec["attempts"] += 1
                if reason in _NEVER_RETRY_REASONS:
                    # 017: a refusal (or any terminal reason) ends the
                    # question — retrying cannot conjure a fact.
                    rec.update(state="failed", reason=reason,
                               next_retry_at=float("inf"))
                elif rec["attempts"] >= _max_attempts:
                    # 017 (FR-002): out of attempts — hand it to the human
                    # rather than retrying on every scan for the rest of the
                    # session. Terminal: even Fill again will not re-arm it.
                    rec.update(state="failed", reason="attempts_exhausted",
                               next_retry_at=float("inf"))
                else:
                    delay = min(_backoff_cap_s,
                                _backoff_base_s * (2 ** (rec["attempts"] - 1)))
                    rec.update(state="failed", reason=reason,
                               next_retry_at=time.monotonic() + delay)


def _run_completion_effects(job_id: int, question: str, answer: str,
                            descriptor_ctx: dict) -> None:
    tag = descriptor_ctx.get("tag") or "free_text_unknown"
    scoped_job = job_id if tag in JOB_SCOPED_TAGS else None
    bank_save = _bank_save_override or _default_bank_save
    try:
        bank_save(question=question, answer=answer, tag=tag, origin="ai",
                  job_id=scoped_job)
    except Exception:  # noqa: BLE001 — bank trouble must not lose the draft
        log.warning("auto-save to answer bank failed", exc_info=True)
    try:
        # 016 (R2): push — the active backend re-scans so the cached answer
        # reaches the page without user action. Lazy import; no-op when no
        # queue is running.
        from . import browser_controller

        browser_controller.on_draft_complete(job_id)
    except Exception:  # noqa: BLE001
        log.warning("draft-completion push failed", exc_info=True)
    for callback in list(_on_complete):
        try:
            callback(job_id, question, answer)
        except Exception:  # noqa: BLE001
            log.warning("drafter on_complete callback failed", exc_info=True)


def _ensure_workers() -> queue.Queue:
    global _tasks
    if _tasks is None:
        _tasks = queue.Queue()
    while len(_workers) < POOL_SIZE:
        worker = threading.Thread(target=_worker_loop, args=(_tasks,),
                                  name=f"je-drafter-{len(_workers)}",
                                  daemon=True)
        _workers.append(worker)
        worker.start()
    return _tasks


def ensure(job_id: int, question: str, descriptor_ctx: dict,
           profile: dict) -> None:
    """Idempotent, non-blocking: schedule at most one draft per key."""
    key = _key(job_id, question)
    with _lock:
        rec = _records.get(key)
        tag = (descriptor_ctx or {}).get("tag")
        if tag in SENSITIVE_TAGS:
            if rec is None:
                _records[key] = {"question": question, "state": "failed",
                                 "reason": "sensitive", "answer": None,
                                 "attempts": 0, "next_retry_at": float("inf"),
                                 "at": time.monotonic()}
            return
        if rec is not None:
            if rec["state"] in ("drafting", "done"):
                return
            if time.monotonic() < rec["next_retry_at"]:
                return
        # 017 (FR-003): one application cannot spend unbounded model time.
        # Counted at schedule time, so concurrent scans cannot race past it.
        spent = _job_generations.get(int(job_id), 0)
        if spent >= _max_drafts_per_job:
            _records[key] = {"question": question, "state": "failed",
                             "reason": "job_budget_exhausted", "answer": None,
                             "attempts": (rec or {}).get("attempts", 0),
                             "next_retry_at": float("inf"),
                             "at": time.monotonic()}
            return
        _job_generations[int(job_id)] = spent + 1
        if rec is not None:
            rec.update(state="drafting")
        else:
            _records[key] = {"question": question, "state": "drafting",
                             "reason": None, "answer": None, "attempts": 0,
                             "next_retry_at": 0.0, "at": time.monotonic()}
        tasks = _ensure_workers()
    tasks.put((key, question, dict(descriptor_ctx or {}), dict(profile or {})))


def mark_needs_you(job_id: int, question: str, reason: str) -> None:
    """Record a question the HUMAN must answer (missing profile fact,
    sensitive class) without ever generating — it shows in the activity
    log and drives the on-page needs-you flag."""
    key = _key(job_id, question)
    with _lock:
        if key not in _records:
            _records[key] = {"question": question, "state": "failed",
                             "reason": reason, "answer": None, "attempts": 0,
                             "next_retry_at": float("inf"),
                             "at": time.monotonic()}


def clear(job_id: int, question: str) -> None:
    """Drop a record (e.g. a needs-you fact the profile now answers)."""
    with _lock:
        _records.pop(_key(job_id, question), None)


# 017: exhausting the attempt cap or the job budget hands the question to the
# human, exactly like a sensitive or missing-fact question — it must be
# highlighted on the page, not silently skipped.
_NEEDS_YOU_REASONS = ("sensitive", "no_valid_option", "profile_fact_missing",
                      "attempts_exhausted", "job_budget_exhausted",
                      "cannot_answer", "never_generated", "wrong_shape")


def list_for_job(job_id: int, limit: int = 50) -> list[dict]:
    """Activity-log entries for one job, newest first (data-model §9)."""
    with _lock:
        records = [dict(rec) for key, rec in _records.items()
                   if key[0] == int(job_id)]
    records.sort(key=lambda rec: rec.get("at", 0.0), reverse=True)
    entries = []
    for rec in records[:limit]:
        if rec["state"] == "done":
            state = "drafted"
        elif rec["state"] == "failed" and rec["reason"] in _NEEDS_YOU_REASONS:
            state = "needs_you"
        else:
            state = "drafting"  # in flight, or failed-and-will-retry
        answer = rec.get("answer") or ""
        entries.append({
            "question": rec["question"],
            "state": state,
            "answer_preview": answer[:120],
            "reason": rec.get("reason"),
        })
    return entries


def get(job_id: int, question: str) -> dict | None:
    with _lock:
        rec = _records.get(_key(job_id, question))
        return dict(rec) if rec is not None else None


def answer_for(job_id: int, question: str) -> str | None:
    with _lock:
        rec = _records.get(_key(job_id, question))
        if rec is not None and rec["state"] == "done":
            return rec["answer"]
        return None


# 017: Fill again re-arms retryable failures only. Re-arming an exhausted
# question would just burn the same budget on the same failure.
_NEVER_RETRY_REASONS = ("sensitive", "profile_fact_missing",
                        "attempts_exhausted", "job_budget_exhausted",
                        "cannot_answer", "never_generated")


def reset_backoff_for(job_id: int, questions: list[str]) -> None:
    """Fill-again support: failed keys become immediately retryable
    (sensitive/fact questions stay with the human)."""
    with _lock:
        for question in questions:
            rec = _records.get(_key(job_id, question))
            if rec is not None and rec["state"] == "failed" \
                    and rec["reason"] not in _NEVER_RETRY_REASONS:
                rec["next_retry_at"] = 0.0


def reset_backoff_for_job(job_id: int) -> None:
    """Fill-again (T016): one explicit user action re-arms every failed
    draft of the job (sensitive/fact questions stay with the human)."""
    with _lock:
        for key, rec in _records.items():
            if key[0] == int(job_id) and rec["state"] == "failed" \
                    and rec["reason"] not in _NEVER_RETRY_REASONS:
                rec["next_retry_at"] = 0.0


def cache_version() -> int:
    with _lock:
        return _cache_version


def stats() -> dict:
    with _lock:
        states: dict[str, int] = {}
        for rec in _records.values():
            states[rec["state"]] = states.get(rec["state"], 0) + 1
        return {"records": len(_records), "by_state": states,
                "cache_version": _cache_version}


def register_on_complete(callback) -> None:
    _on_complete.append(callback)


def set_generator_for_tests(fn) -> None:
    global _generator_override
    _generator_override = fn


def set_bank_save_for_tests(fn) -> None:
    global _bank_save_override
    _bank_save_override = fn


def reset_for_tests(backoff_base_s: float | None = None,
                    backoff_cap_s: float | None = None,
                    max_attempts: int | None = None,
                    max_drafts_per_job: int | None = None) -> None:
    global _tasks, _records, _cache_version, _generator_override, \
        _bank_save_override, _backoff_base_s, _backoff_cap_s, \
        _max_attempts, _max_drafts_per_job, _job_generations
    with _lock:
        tasks = _tasks
        worker_count = len(_workers)
    if tasks is not None:
        for _ in range(worker_count):
            tasks.put(None)
    for worker in _workers:
        worker.join(timeout=2)
    _workers.clear()
    with _lock:
        _tasks = None
        _records = {}
        _cache_version = 0
        _generator_override = None
        _bank_save_override = None
        _on_complete.clear()
        _backoff_base_s = backoff_base_s or _DEFAULT_BACKOFF_BASE_S
        _backoff_cap_s = backoff_cap_s or _DEFAULT_BACKOFF_CAP_S
        _max_attempts = max_attempts or MAX_ATTEMPTS_PER_QUESTION
        _max_drafts_per_job = max_drafts_per_job or MAX_DRAFTS_PER_JOB
        _job_generations = {}
