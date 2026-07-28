# Feature 016 — "The Fill Release" (v1.6.0)

**Date:** 2026-07-27 · **Status:** approved plan (plan mode, 2026-07-27); this
doc is the durable design record and the seed for `/speckit-specify`.
**Prior:** 015 "The Pairing Release" (v1.5.0) fixed pairing/connection; this
release makes filling itself work, end-to-end, on the page.

## 1. Problem

The user's first real v1.5.0 run: links open in Chrome and the companion
connects, but (a) nothing fills after they click Apply on a Greenhouse
posting; (b) dropdown and yes/no questions get 60–120-word prose drafts;
(c) approving an answer in the app never touches the page; (d) the popup
"Fill this page" silently no-ops while a queue is active; (e) "Tailor for
this job" hard-crashes the whole app. The user's directive: everything works
next phase; review moves onto the web page itself (they correct in place);
the extension gets clearer; the tailor crash is eliminated.

## 2. Root causes (three code traces, 2026-07-27, file:line verified)

**RC1 — the bridge message loop blocks on inline LLM drafts.**
`web/routes_bridge.py:190-200` awaits one handler at a time.
`ext_backend._handle_fields` calls `qa.draft` synchronously mid-loop
(`browser_controller.py:384`; up to 180 s of CPU inference), and fills are
batched until the whole form is decided (`ext_backend.py:340-342`) — so even
already-decided name/email fills are never sent while a draft runs. The
discovery badge floods the same serialized channel every 1.5 s
(`extension/content/discovery.js`), each request doing an uncached
full-table H1B lookup (`engine/db.py:966`). A failed draft returns "skip"
(non-terminal), so the same field re-triggers a fresh multi-minute draft
every 2 s forever. Installed-app log: 413× "queue full", 95× chat timeouts.

**RC2 — choice fields cannot work.**
Options are captured only for native `<select>` (`scanner.js:98`,
`watcher.py:142`); custom comboboxes ship `options: []`; radio groups are
scanned as separate fields whose "question" is literally "Yes"/"No" (no
fieldset/legend/radiogroup handling anywhere). Neither drafting prompt
receives field type or options; `answer_bank.suggest` explicitly asks for
60–120 words of prose (`answer_bank.py:118-147`). The filler has no radio
branch — it overwrites the radio's `.value` property and falsely reports
"filled" (`filler.js:151-155`). `selectByLabel` is exact-match
case-sensitive; combobox option discovery is `[role=option]` only.

**RC3 — confirm never reaches the page.**
`confirm_answer` saves to the DB then calls `resolve_pending(answer)`, which
ignores the answer and, in extension mode, sends nothing
(`browser_controller.py:544-564`). The next 2 s rescan runs the prose
through `match_option`, fails, and writes a terminal `no_match`/
`needs_manual` ledger state (`field_core.py:27`) — never retried. The draft
"Confirm & save" path is double-dead: `resolve_pending` early-returns on
`pending is None`, and the non-empty-is-sacred rule blocks overwriting
(`field_core.py:74-78`, `filler.js:64-67`).

**RC4 — silent operational traps.**
Popup "Fill this page" during a queue → `busy` error the service worker
discards (no "error" case in `service-worker.js:22-39`); new-tab Apply
(embedded Greenhouse boards) is untracked — no `tabs.onCreated`/opener
following; `open_tab` has no ack/retry/expiry (`ext_backend.py:154`);
`rescan()` is a no-op in extension mode (`browser_controller.py:615-626`);
the extension backend never records outcomes/failures; `_inflight` never
expires; `preflight()` launches headless Playwright even in companion mode
(`routes_autofill.py:52`); content-script scan exceptions are swallowed
(`main.js:30`) leaving the tab permanently silent.

**RC5 — tailor crash: uncontained native fault in one serialized inference.**
No serialization bypass exists (verified: only `inference.py` touches
`_chat_impl`/`_embed_impl`). But thread mode cannot contain a native
fault/OOM abort, and tailor is the riskiest call: the app's longest
grammar-constrained JSON generation with `max_tokens=None` (unbounded up to
n_ctx), a prompt up to ~12k chars — 2× the documented safe local band
(`resume_extract.py:147-150`) — no `timeout_s` (2 attempts × 180 s of a
blocked worker), both GGUF models resident (llama "scores" buffers ≈311 MB
chat + ≈537 MB embedder), `semantic._load()` retrying a 330 MB model load on
every embed call (no `_load_attempted` guard), and unbounded `je-suggest`
threads feeding the queue. Installed-app evidence: tailoring has NEVER
persisted and never logged a failure across 16k jobs while the identical
serialized path scored 117 jobs — the process dies mid-inference.
`JOBS_AI_SUBPROCESS` (the 015 spike: supervised child process hosting the
models, proven by tests + frozen smoke, default OFF) is the built
containment.

## 3. Locked decisions (AskUserQuestion, 2026-07-27)

- **D1 — Apply click.** The assistant MAY click form-opening "Apply"
  controls (they only reveal the form). Final "Submit application", login,
  pay, next/continue stay strictly human-only. Requires a narrow
  constitution clarification (v1.1.3 → v1.1.4), the same bounded pattern as
  the 011 (widget clicks) and 012 (read-only overlay) clarifications.
- **D2 — Review flow: fill-first.** Every field is filled immediately with
  the best available answer (choice fields picked from the field's real
  options); uncertain/AI-drafted fields get a visible on-page highlight;
  the user corrects in place. No blocking app approval gate anywhere.
  Answers still auto-save to the answer bank.
- **D3 — Extension UX.** An injected on-page shadow-DOM panel (extending the
  existing overlay): connection status, fill progress, per-field list
  (filled / needs attention), "Fill again".

## 4. Design

### 4.1 WS-A — Companion fill pipeline rebuild (RC1, RC3, RC4)

**Fast message loop.** `ext_backend._handle_fields` becomes decide-fast-only:
profile, answer-bank, and draft-cache lookups — never an LLM call. Fills are
sent incrementally (per decided field or small batch), not after the whole
descriptor loop.

**New unit: `engine/autofill/drafter.py`** — the bounded background drafting
pool (generalizes 015's park-then-draft; replaces the unbounded `je-suggest`
threads and the single-pending park gate).
- API: `ensure(question_key, descriptor_ctx, profile) -> None` (idempotent
  fire-and-forget), `get(question_key) -> {state: drafting|done|failed,
  answer, attempts, next_retry_at}`, `stats()` for doctor/tests,
  `reset_for_tests()`.
- Owns the **draft cache** (one draft per normalized question per session —
  kills the infinite re-draft loop) and the **negative cache** (failed
  drafts back off exponentially instead of retrying every 2 s).
- Bounded worker pool (2 threads) feeding the serialized inference worker;
  completed drafts auto-save to the answer bank (marked AI-drafted, per D2)
  and trigger the **rescan push**: clear that field's ledger entry, send the
  new outbound `rescan` message → content script re-scans → the decide loop
  now hits the cache → the fill goes out.
- `current_job()` exposes a non-blocking "drafting…" list for the app UI
  (replaces the blocking pending panel).

**Ledger repair.** `no_match`/`needs_manual` entries carry a cache-version
stamp and become retryable when a NEW answer arrives for that field;
`_inflight` entries expire (~20 s); the extension backend records real
outcomes (`scan_failed` etc.) like the Playwright path already does.

**Discovery decongestion.** The extension caches the score per job URL and
requests once per page (+ once per SPA URL change; `discovery.js` already
tracks `lastHref`). The app caches `load_h1b_employers()` in memory
(invalidated on sponsorship refresh). Score handling must never delay
`fields` processing.

**Tab following (watch-transfer model).** `chrome.tabs.onCreated` +
`openerTabId`: a tab opened FROM the watched tab becomes the new watch
target. App-side `_watch` stays singular but **transfers** to the newest
child (fields from the old tab then intentionally stop). The service worker
persists watched tab ids to `chrome.storage.session` (the 015
`recordAttempt` pattern) so MV3 worker restarts don't orphan tabs.
`open_tab` gets an ack timeout + one retry + `pending_open` expiry; on
failure the queue advances with a visible `launch_failed` instead of
hanging forever. `_handle_fields`' silent wrong-tab drop increments a
doctor counter.

**Error surfacing.** The service worker handles `error` messages → popup and
panel show "busy — stop the queue first" instead of a silent no-op;
content-script scan exceptions report an additive `scan_error` message shown
by doctor/panel; `rescan()` sends the rescan nudge in extension mode;
`preflight()` is skipped when the companion is live.

**Protocol (PROTOCOL_V stays 1 — all additive).** New outbound: `rescan`
{reason}. New inbound: `scan_error` {message}, `child_tab` {tab_id,
opener_tab_id}. Descriptor gains `members: [{je_idx, label}]` and
`required`; `FillItem` gains `kind: "radio"` and highlight flags
(`Descriptor` is `extra="ignore"` pydantic — verified additive-safe).

### 4.2 WS-B — Choice-aware answering (RC2)

**Scanner upgrades** (both serializers — `extension/content/scanner.js` and
the inline JS in `engine/autofill/watcher.py` — changed in lockstep, guarded
by a new parity test): group RADIO sets by `name`/`role=radiogroup`/fieldset
into ONE logical field whose question is the legend/group label, whose
`options` are the member labels, whose `je_idx` is deterministically the
FIRST member's (stable `(doc, je_idx)` ledger key), plus the additive
`members` list; capture `required`; custom comboboxes stay
`widget=custom_combobox` with options harvested at fill time (clicking a
field's own widget is already constitution-permitted). Checkbox GROUPS
(multi-select questions) are NOT pick-one: members stay individual fields
but gain the group legend as question context; unknown multi-selects are
left unfilled + highlighted (single consent-style checkboxes keep today's
behavior).

**Constrained drafting.** `type`/`options`/`maxlength` flow descriptor →
drafter context → BOTH prompts (`qa.draft`, `answer_bank.suggest`):
- Fields WITH options: pick-one JSON prompt ("answer MUST be exactly one
  of: […]") + hard post-validation (answer ∈ options, else unfilled +
  highlighted).
- Custom comboboxes (options unknown until fill time): draft a SHORT answer
  (≤4 words, "the literal option label"); the existing `fillCombobox`
  harvest then fuzzy-matches; no match ⇒ unfilled + highlighted.
- Yes/no questions answer from profile facts (work auth, sponsorship,
  relocation) BEFORE any LLM call. Prose length obeys `maxlength`.

**Sensitive-question policy (replaces the human gate).** EEO/demographic,
disability, veteran, criminal-history, and reference questions are NEVER
AI-answered — always left unfilled + highlighted for the human. Profile-fact
tags fill from the profile only. Enforced as a tag allowlist in the drafter
(today `answer_bank.suggest` has no such check).

**Filler upgrades** (both fillers): a real radio branch (`.checked = true` +
events on the matching member); select matching normalized/fuzzy (the
definitive option text comes from `fields.match_option`); combobox option
discovery widened beyond `[role=option]` (listbox `li`, common react-select
classes) with harvest-then-match; honest outcomes — never report "filled"
for an unset radio.

**Version-skew gate.** An old companion receiving `kind:"radio"` would
silently mis-fill via the text setter. The app sends new kinds only when the
companion's hello version equals APP_VERSION (doctor already surfaces the
mismatch); otherwise those fields go unfilled + highlighted.

**Fixture upgrade.** The practice/E2E fixture pages gain a radio group, a
custom combobox, and a maxlength'd text field so all of this is testable
end-to-end.

### 4.3 WS-C — Fill-first on-page experience (D1 + D2 + D3)

**Constitution v1.1.4 clarification** (via `/speckit-constitution`), draft
wording: *the automation MAY click a control that ONLY opens or reveals the
application form (e.g., a job posting's "Apply" button that scrolls to or
displays the embedded form), recognized via a strict per-ATS allowlist and
never a control of type submit; it MUST still never click any control that
submits, advances a wizard, saves, logs in, registers, or pays.* The
existing `click_guard` keeps denying "apply" in the FILL path; the new
`openApplication()` step uses its own strict adapter allowlist
(Greenhouse/Lever/Ashby known apply-opener selectors, `type != submit`, not
inside a filled form) and is a separate code path the fill flow cannot
reach.

**Auto-open the form.** On a QUEUE-DRIVEN watched tab on a recognized ATS
page (never for popup "Fill this page" on arbitrary pages) with no fillable
form but a recognized apply-opener, the content script clicks it ONCE —
one-shot keyed per `(doc, href)` so SPA URL changes re-arm it — then the
existing MutationObserver/2 s rescan picks up the revealed form. Logged to
the panel ("opened the application form").

**On-page panel (D3).** Extends `extension/content/overlay.js` shadow DOM:
status line (companion connected / filling / done), counters (N filled, M
need attention), per-field list with jump-to-field, "Fill again", and the
standing "you review and submit" note. **"Fill again" semantics:** clear the
doc's non-`skipped_existing` ledger entries + rescan nudge; user-typed
values stay untouched via the existing write-time `fillable()`/value
re-check guards.

**Uncertainty highlights (D2).** Carried by the EXISTING
`FillItem.flag="ai_draft"` wire field (currently ignored by the filler):
outline + small badge keyed by `je_idx`, surviving the 2 s rescans, cleared
by an input listener when the user edits the field. Unfilled choice and
sensitive fields get the same treatment with a "needs you" flag.

**Gate-removal blast radius (explicit).** `/api/autofill/answers/confirm`
and `/drafts/{id}/confirm` stay (they edit the bank; the 015 sentinel guard
remains) but no longer gate filling; `resolve_pending` and the pending
panel are replaced by the drafting list + a passive activity log (what was
drafted/filled where, linking to the bank). A dedicated sweep task rewrites
ALL pending/confirm-flow tests (015's drafting-state test, sentinel tests,
park-then-draft tests, conftest's draft-join teardown) — the stale-pin
lesson applied proactively.

### 4.4 WS-D — AI runtime containment + tailor (RC5)

- **Subprocess isolation default ON.** `JOBS_AI_SUBPROCESS` defaults to "1"
  (env "0" still forces thread mode). The full test battery + frozen smoke
  run in this mode on both OSes — the 015 GO gates, now as the default. A
  native fault kills only the AI child; the app surfaces "AI runtime
  restarted" (doctor/diagnostics already count restarts). Unit tests are
  unaffected: `set_executors_for_tests` bypasses the child (verified,
  `inference.py:104`).
- **Generation bounds.** Explicit `max_tokens` per purpose (scoring/tailor
  JSON ≈1.5k, drafts ≈512) carried in the chat payload; the tailor prompt
  is capped to the documented safe local band (resume+job trimmed to ≤6k
  chars total, matching `resume_extract`'s bound); tailor passes
  `timeout_s≈300` and drops to 1 local attempt.
- **Load hygiene.** `semantic._load_attempted` guard (mirrors `local_llm`);
  cap the embedder's `n_batch` (its scores buffer is ≈537 MB today); the
  drafter pool bounds background drafting (replaces unbounded threads).
- **Tailor UX.** Keep the sync route: honest long-spinner with "can take a
  few minutes" text and a clean rendered failure state on 502 (today it
  reads as a dead app); success reloads as now.

### 4.5 WS-E — Verification (TDD throughout; superpowers + speckit hybrid)

- **Bridge responsiveness:** a slow draft in flight while `fields`/`pong`
  keep processing — last_seen stays fresh; profile fills dispatch
  immediately (deterministic via the drafter/executor test seams).
- **One-draft-per-question:** hammer the scan loop; the drafter runs once
  per unique question.
- **Choice fills:** unit + E2E — radio group checked correctly, select set
  via normalized match, combobox harvest-then-pick, prose never sent to a
  choice field, honest outcomes.
- **Pairing E2E (both browser families; real uvicorn + real Chromium, so
  `tabs.onCreated` is exercisable):** extended fixture with an apply-opener
  button (form revealed only after the click — asserts D1), radio/combobox
  fields, a new-tab opener case (asserts watch transfer), and panel
  presence. The fixture's submit control logs clicks server-side so the
  test asserts ZERO submit clicks.
- **Serializer parity:** the same fixture HTML through `scanner.js` (real
  browser) and `watcher.py`'s inline serializer yields the same logical
  fields/groups (no parity guard exists today; grouping doubles drift risk).
- **Fault containment:** with subprocess mode ON (echo seam), an induced
  child crash/hang during a tailor call leaves the app alive, surfaces the
  502/restart, and increments the restart counter.
- **Frozen smoke:** runs with subprocess default ON; a tailor smoke call is
  added. Full battery ×2 + browser + slow markers green before ship.

## 5. Guardrails

$0 · offline-first · engine never imports web · no JS framework/Node build ·
secrets never in diagnostics or storage · **the human still performs every
final submit/login and advances every wizard** (D1 permits form-OPENING
clicks only, via the v1.1.4 clarification) · PROTOCOL_V stays 1 (all new
messages/fields additive) · Apply Assist never auto-submits.

## 6. Non-goals

Workday/Taleo deep adapters (Greenhouse/Lever/Ashby first) ·
store-published extension · Firefox · code signing · fill-core scoring
changes · cloud AI changes (Groq fallback untouched) · auto-replacing an
already-filled AI draft with a later "better" draft (the user may have
accepted it; their edits are always sacred).

## 7. Success criteria

1. E2E in both browser families: queue → auto-open Apply → revealed form
   fills including radio, select, and combobox fields; zero submit clicks.
2. Bridge stays responsive: status fresh (<5 s) and profile fills dispatched
   (<2 s from `fields`) while a simulated slow draft runs.
3. Exactly one draft per unique question per session under a scan hammer.
4. An induced AI-child fault during tailor cannot close the app; tailor
   completes in frozen smoke with subprocess ON.
5. Every drafted/uncertain field is visibly highlighted on the page; the
   panel shows live progress; sensitive questions are never AI-answered.
6. Full battery ×2, browser + slow markers, frozen smoke (subprocess ON),
   and both installers verified on the release.

## 8. Process

Constitution v1.1.4 clarification → branch `016-fill` → speckit chain
(specify → clarify → plan → checklist → tasks → analyze) → hybrid
`/speckit-implement` + superpowers TDD → docs (USER_MANUAL §20, README,
WHATS_NEW 1.6.0) → frozen smoke (subprocess ON) → ship v1.6.0 via the
standard tag ritual; verify BOTH installers.
