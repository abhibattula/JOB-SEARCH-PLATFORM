# Feature 009 — The Live Fill Engine: Apply Assist Rebuilt + Profile Import That Imports

**Date:** 2026-07-23 · **Status:** Approved by Abhinav (brainstorming dialogue, this date)
**Branch:** `009-live-fill-engine` · **Ships as:** v0.9.0

## Why

v0.8.0 fixed the browser *launch* (installed Edge/Chrome now opens), which
exposed the deeper truth the user then verified: **the fill engine has never
been able to fill real ATS pages**, and **profile import is invisible even
when it runs**. Two deep code investigations (2026-07-23) confirmed the
one-shot fill architecture is wrong in independent, individually-fatal ways
— this feature is a rebuild, not a patch. The user additionally chose to
fold in a small "trust polish" layer (a bundled practice application that
proves Apply Assist works on their machine) and made the offline model the
default AI tier.

## Root causes (confirmed, file:line evidence in plan/research)

**Apply Assist — "browser opens, nothing fills":**
- A1 Scan-at-load: fields serialized the instant `goto` returns; ATS forms
  are JS-rendered → 0 fields → job marked `unrecognized` → fill never
  attempted (browser_controller.py:254→276). *Sufficient alone.*
- A2 Wrong URL: `job.url` is the posting page, not the form (Lever form =
  `/apply`; Ashby stores `jobUrl` though the API offers `applyUrl`;
  Workable/Indeed have no form on the landing page). *Sufficient alone.*
- A3 One-shot: no retry mechanism of any kind.
- A4 Iframe-blind: main-frame-only serialization; embedded Greenhouse
  forms invisible.
- A5 The `framenavigated` auto-rescan is greenlet-unsafe → throws →
  swallowed: multi-page refill **has never worked**.
- A6 No dedicated thread despite the docstring: Playwright objects touched
  from multiple FastAPI request threads (forbidden) → jobs #2+, Re-scan,
  confirm-answer all unreliable.
- A7 Classifier regexes miss raw attributes (`first\s*name` ≠ `first_name`).
- A8 Selectors built from raw ids/names are malformed for bracket names
  (`job_application[123][value]`, `urls[LinkedIn]`) → silent skips.

**Profile import — "did nothing":**
- B1 All extraction runs synchronously inside the form POST (30s–3min on
  the local model) with zero progress UI — the window looks frozen.
- B2 Local tier deterministically overflows: `n_ctx=4096` vs a
  24,000-char prompt → extraction fails silently 100% of the time on the
  offline model → resume sections can never populate.
- B3 Fill-only-blank + an already-complete profile = invisible no-op;
  conflict banners easy to miss; names never fill via the regex fallback.

## Decisions (user-approved)

| Decision | Choice |
|---|---|
| Scope | Two rebuilds **+ trust polish** (practice application, auto-scroll/highlight for review items) |
| AI default | **Offline model preferred by default** (`PREFER_LOCAL_LLM=1`); Groq key = automatic fallback on local failure; one-click toggle in Settings |
| Import semantics | Explicit **review screen** — every field shown current-vs-resume with Keep / Use resume's / Merge; nothing silent; visa fields never imported |
| Fill engine | **Full rebuild: live watcher + per-ATS adapters** on a dedicated worker thread |
| Release | One v0.9.0 |

## WS-A · The Live Fill Engine

**Principle: stop trying to fill a page once; watch the page and fill
fields the moment they exist.** Constitution unchanged: the app NEVER
clicks submit/login/next/apply — it only fills.

- `engine/autofill/worker.py` (NEW): one daemon thread owns ALL Playwright
  objects for the app session. Command queue (`OPEN_JOB | FORCE_TICK |
  CLOSE_PAGE | RESOLVE_PENDING | SHUTDOWN_CONTEXT`); the queue-wait
  timeout (~2s) is the tick scheduler. `_assert_worker_thread()` guards
  every Playwright touch. Fixes A5/A6 structurally.
- `engine/autofill/watcher.py` (NEW): one tick = walk `page.frames` (≤15)
  → per frame ONE JS eval that serializes all fields AND stamps each
  element `data-je-idx=N` (all later actions address `[data-je-idx="N"]`
  in the right frame — no CSS from raw ids/names, kills A8; descriptors
  carry `focused`/`visible`) → classify (adapter first, generic fallback)
  → idempotent fill: skip non-empty (sacred) · skip focused (never touch a
  field the user is typing in) · skip already-filled (frame,idx) · re-check
  empty+unfocused immediately before writing. Values via the existing
  `_value_for_tag` (credentials, profile, answer bank, tailored-PDF
  preference — preserved). `unrecognized` is no longer terminal: the
  watcher keeps watching while the job is current, so SPA renders,
  user-clicked Apply reveals, and multi-page Next flows all fill when
  their fields appear (kills A1/A3/A4). `framenavigated` handler deleted.
- `engine/autofill/apply_urls.py` (NEW): `jobs.lever.co/...`→`+/apply`;
  `jobs.ashbyhq.com/...`→`+/application`; Greenhouse as-is; everything
  else as-is with on-screen guidance. Plus ingest fix: `ashby.py` prefers
  `applyUrl` (kills A2).
- `engine/autofill/adapters.py` (NEW): deterministic name/id/autocomplete
  → tag maps for Greenhouse (`first_name`, `job_application[...]`), Lever
  (`name`, `urls[LinkedIn]`, `resume`), Ashby (`_systemfield_*`), plus a
  shared HTML-autocomplete map. Generic classifier (regexes fixed to
  `[\s_-]*` separators — A7) is always the fallback.
- `browser_controller.py` REWRITTEN as a thread-safe facade: public API
  and all 005-008 semantics preserved (queue state machine, reason
  classes, fill report with password masking, pending-answer single-slot
  flow, interruption/resume, batch summary); every Playwright path becomes
  enqueue-to-worker; `start_queue` returns instantly.
- UI: live activity feed — *"watching page — 12 fields seen · 9 filled ·
  waiting for you to click Apply/submit"*; emphasized guidance when no
  form is visible; Re-scan becomes "force a fill pass now".

## WS-A+ · Trust polish

- **Practice application** (`Test Apply Assist` button): a bundled,
  realistic local application page (name/email/phone/resume-upload/
  work-auth dropdown/custom question + one delayed-render section + one
  iframe section) served by the app itself and queued like a real job —
  the user watches their own data fill live within seconds, no real
  posting involved. The same page family (plus Lever/Ashby/typing-race
  variants) IS the automated real-browser fixture suite.
- **Auto-scroll + highlight** for anything requiring user attention
  (review items, conflicts, pending answers).

## WS-B · Profile import rebuilt (offline-first)

- `engine/profile_import.py` (NEW): background state machine on the proven
  `updates.py` pattern (`idle → extracting(contact → skills → sections
  chunk i/N) → ready(proposal) → applied | failed(error)`;
  `background=False` test path). Upload returns instantly (B1).
- **Local tier fixed** (B2): `local_llm` `n_ctx` 4096→8192 AND chunked
  map-reduce extraction for the local tier — split on blank-line
  boundaries (~5,000 chars/chunk), per-chunk grammar-constrained JSON,
  deterministic merge (ordered sections concat; casefold-deduped skills
  union; first-non-empty contact overlaid with the regex fallback);
  per-chunk progress; one bad chunk costs only itself. Cloud tier keeps
  single-shot. Regression test: every local prompt ≤ ~6,000 chars.
- **Import review screen** (B3): `POST /api/profile/import` (+ `status`,
  `proposal`, `apply` endpoints); proposal lists EVERY field — identity,
  skills, target titles, locations, resume-sections summary — as current
  vs from-resume with Keep / Use resume's / Merge per row (blanks default
  apply, conflicts default keep, lists default merge; hand-edited sections
  warn and default keep — applying is the explicit consent; visa/work-auth
  excluded, FR-024 preserved). Profile page `#import-region` polls: progress
  banner → review screen → "Apply selected" → toast + refreshed profile.
  Applying re-derives search terms unless user-owned. `POST /api/profile`
  is slimmed to storage-only, enforced by a monkeypatch-to-raise test.
- **`PREFER_LOCAL_LLM` default "1"**: matching, tailoring, and extraction
  run on the bundled model by default; automatic fall-through to the
  cloud key on local failure; Settings checkbox to flip.

## Verification (the layer whose absence let this ship broken twice)

1. Unit suites for watcher/adapters/apply_urls/import state machine (all
   Playwright faked; no-click invariant extended to the locator path).
2. **Real-browser fixture suite** (`@pytest.mark.browser`, headless
   installed-channel Playwright vs a local HTTP server): delayed-render,
   iframe-embedded, bracket-name, Ashby-style, form-behind-Apply-button
   (the TEST clicks; the watcher fills), and typing-race pages. Default
   `pytest` run excludes them; CI/pre-release runs them explicitly.
3. **Live gate** (release-blocking): one real Greenhouse, Lever, Ashby,
   and Indeed/Workable posting each — correct form URL, fills within ~2
   ticks of fields appearing, multi-page refill, nothing ever clicked.
4. **Offline-tier gate**: real chunked extraction of a 3-page fixture
   resume on the bundled model must produce sections with ≥1 experience
   entry.
5. Frozen-shell smoke additions: `/api/autofill/status` has `activity`;
   `/api/profile/import/status` answers; practice page serves.

## Out of scope

Auto-click/submit/login (banned), custom React combobox widgets (require
clicks — reported honestly as no-match), auth-walled Indeed Smart Apply
flows beyond filling what renders, macOS-specific work, code signing.

## Process

Speckit chain (specify → clarify → plan → checklist → tasks → analyze)
seeded from this document → hybrid TDD implementation → docs → frozen
smoke → live gate → ship v0.9.0 (merge → mirror → tag → both installers
verified).
