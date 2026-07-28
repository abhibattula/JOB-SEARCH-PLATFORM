# Phase 0 Research: The Fill Release (016)

Decisions R1–R14. Each records the choice, rationale, and rejected
alternatives. Evidence base: the three 2026-07-27 code traces (bridge/fill
trigger chain; choice-field + confirm pipeline; tailor crash) plus
installed-app forensics (app.log, jobs.db).

## R1 — Decide-fast bridge loop with incremental fills

**Decision**: `ext_backend._handle_fields` may only consult fast sources
(profile, answer bank, drafter cache) — never invoke a model. Fills
dispatch as decided (per field or small batch), not after the loop.
The handler's decision path must contain no blocking model call
(regression-tested via a poisoned executor that fails the test if
entered from the handler).
**Rationale**: the trace showed one `fields` message blocking the whole
serialized socket loop for up to 180 s inside `qa.draft`
(`browser_controller.py:384`), starving heartbeats and withholding
already-decided fills (`ext_backend.py:340-342`). Incremental dispatch
makes profile fields land in ~one scan regardless of AI state.
**Alternatives**: (a) parallelize the socket loop — rejected: reorders
messages, races the ledger, larger blast radius; (b) keep batch-at-end but
add a timeout — rejected: still withholds decided fills and still blocks
the loop.

## R2 — Background drafter: cache key, backoff, push-via-rescan

**Decision**: new `engine/autofill/drafter.py`: a bounded pool (2 worker
threads) feeding the serialized inference owner. Draft cache keyed
`(job_id, normalized_question)`; job-agnostic factual categories may also
consult the cross-job answer bank as today, but job-specific prose
(cover-letter/why-us tags) never reuses across jobs (spec clarification).
Negative cache: exponential backoff 30 s → ×2 → cap 10 min. Completion
push: write cache + scoped auto-save to bank (origin=ai) + clear the
field's ledger entry + send outbound `rescan`; the content script's next
scan re-serializes and the decide loop now hits the cache.
**Rationale**: one draft per question per session is the direct kill for
the observed infinite re-draft loop (skip → re-draft every 2 s). Push via
rescan (rather than a direct app-initiated fill) avoids trusting stale
element indexes across DOM churn — the fill always follows a fresh scan.
**Alternatives**: (a) direct `fill` push with remembered je_idx — rejected:
stale-index writes on rerendered forms; (b) unbounded thread-per-question
(015 behavior) — rejected: thread floods contributed to the 413×
queue-full log evidence; (c) drafting inside the inference worker itself —
rejected: serializes drafts behind interactive calls and vice versa.

## R3 — Ledger retryability + inflight TTL + real outcomes

**Decision**: ledger entries record the draft-cache version used; a field
whose terminal state (`no_match`/`needs_manual`) predates a newer answer
becomes retryable. `_inflight` entries expire after 20 s. The extension
backend records job-level outcomes (`scan_failed`, `launch_failed`) like
the Playwright path.
**Rationale**: the trace showed confirm-then-`no_match` deadlocks — the
unlock ran before the terminal state existed, and `needs_manual` was never
cleared; `_inflight` leaked forever on a lost `fill_result`.
**Alternatives**: making those outcomes non-terminal — rejected: without a
version stamp that reintroduces every-2 s retries of hopeless fills.

## R4 — Watch transfer, persisted watches, open acknowledgment

**Decision**: `chrome.tabs.onCreated` + `openerTabId`: a tab created from
the watched tab becomes the new single watch target (app `_watch`
transfers; old tab's fields intentionally stop). The service worker
persists the watched set in `chrome.storage.session`. `open_tab` gets an
ack timeout (5 s) + one retry; `pending_open` entries expire; failure
surfaces as `launch_failed` and advances the queue. Wrong-tab `fields`
drops increment a doctor counter.
**Rationale**: embedded job boards open the real form in a child tab —
today invisible; MV3 worker restarts wiped the in-memory watch map; a
lost `tab_opened` bricked the queue silently.
**Alternatives**: multi-tab concurrent watching — rejected: one
application at a time is the product model; concurrent fill targets
multiply ledger/report complexity for no user value.

## R5 — Discovery decongestion

**Decision**: extension requests a score once per page state (keyed by
href, re-armed on SPA URL change — `discovery.js` already tracks
`lastHref`); the app caches `load_h1b_employers()` in memory (invalidated
by the sponsorship refresh path).
**Rationale**: the trace showed a 1.5 s score flood, each doing an
uncached full-table read + fuzzy match, head-of-line blocking `fields` on
the serialized socket.
**Alternatives**: separate socket/queue for discovery — rejected: more
moving parts; caching removes ~all the traffic at lower complexity.

## R6 — Radio-group model (and checkbox stance)

**Decision**: scanners group radios by `name`/`role=radiogroup`/fieldset
into one logical descriptor: question = legend/group label; `options` =
member labels; `je_idx` = first member's (stable ledger key); additive
`members: [{je_idx, label}]`. `FillItem` gains `kind: "radio"` whose
`value` is the chosen member label. Checkbox GROUPS are not pick-one:
members stay individual fields with the group legend as question context;
unknown multi-selects stay unfilled + flagged; single consent checkboxes
unchanged. Both serializers change in lockstep behind a parity test.
**Rationale**: today each radio is its own field whose "question" is
literally "Yes" — unanswerable by construction; grouping restores the real
question + options.
**Alternatives**: keeping per-radio descriptors and reconstructing groups
app-side — rejected: the app lacks the DOM context (fieldset/legend) to
group reliably, and the assistant-window path would need it duplicated
anyway.

## R7 — Option-constrained drafting + sensitive policy

**Decision**: descriptor context (type/options/maxlength) flows into both
prompts. Option-bearing fields use a pick-one JSON prompt with hard
post-validation (answer ∈ options else unfilled+flag). Comboboxes draft a
≤4-word literal option label, matched at fill time against harvested
options. Profile-fact yes/no (work auth, sponsorship, relocation) answers
from the profile with no model call. A sensitive-tag denylist
(EEO/demographic, disability, veteran, criminal history, references) is
enforced IN the drafter: those never generate — unfilled + flagged.
**Rationale**: prose-for-dropdowns was guaranteed by prompts that request
60–120 words and never see options (`answer_bank.py:118-147`); the
sensitive denylist replaces the removed human approval gate with a
stronger, structural guarantee.
**Alternatives**: option-matching prose after the fact — rejected: that is
today's failing `match_option`-on-essays behavior; constraining the
generation is strictly better.

## R8 — Filler upgrades + version-skew gate

**Decision**: real radio branch (`.checked = true` + input/change on the
matched member); select matching uses the option text `fields.match_option`
resolved (normalized), not strict equality; combobox harvest widened
(listbox `li`, `[class*="option"]` under an open listbox) with
harvest-then-match; outcomes must reflect the page (an unset radio is
never "filled"). New fill kinds are sent only when the companion's hello
version equals APP_VERSION; otherwise the field goes unfilled + flagged.
**Rationale**: the filler falls through to `setNativeValue` for radios and
lies "filled"; strict-equality select matching breaks on normalization;
an old companion receiving `kind:"radio"` would text-set it silently.
**Alternatives**: bumping PROTOCOL_V — rejected: 4426 hard-rejects old
companions entirely; the version gate degrades gracefully instead.

## R9 — Apply-opener (`openApplication`) allowlist

**Decision**: new `extension/content/opener.js`, active only on
queue-driven watched tabs (never popup-initiated fills). Per-ATS
allowlist selectors (Greenhouse `#apply_button`/apply anchor, Lever
`.postings-btn`/apply href, Ashby apply button patterns) with structural
guards: not `type=submit`, not inside a form containing filled inputs.
One-shot per `(doc, href)` (SPA changes re-arm). Click logged to the
panel. Fill-path `click_guard` unchanged — "apply" stays denied during
filling.
**Rationale**: D1 (locked) + constitution v1.1.4. Keeping the opener as a
separate allowlisted step preserves the fill path's deny-everything
stance; the user's evidence case (Greenhouse posting with embedded form)
is exactly this shape.
**Alternatives**: generic text-match "apply" clicking — rejected: too easy
to hit a submit-adjacent control on unknown ATSes; allowlist-first is the
constitutional bound.

## R10 — On-page panel + highlights + Fill again

**Decision**: `overlay.js` grows a shadow-DOM panel (status, filled /
needs-attention counters, per-field list with jump-to, Fill again, the
standing "you review and submit" note). Highlights ride the existing
`FillItem.flag` ("ai_draft", new "needs_you"): outline + badge keyed by
`je_idx`, cleared by that element's input listener. Fill again = clear the
doc's non-`skipped_existing` ledger entries + reset drafter backoff for
the page's questions + rescan nudge; user-typed values survive via the
existing `fillable()`/value re-check guards.
**Rationale**: D2/D3 (locked). The flag field already crosses the wire
unused — no protocol change needed for highlights.
**Alternatives**: Chrome side panel — offered, user chose the on-page
panel; app-window review — explicitly rejected by the user.

## R11 — Approval-gate removal and its blast radius

**Decision**: fill-first everywhere. `browser_controller` drops the
single-pending park gate for a drafting list (all unknowns drafted
concurrently-bounded); `resolve_pending` retires; confirm/draft endpoints
become bank-curation only (sentinel guard kept); the status partial's
blocking review box becomes a passive activity log (drafted/filled/
needs-you per field + drafting list). A dedicated sweep task rewrites all
pending/confirm-flow tests (015 drafting-state, sentinel, park-then-draft,
conftest draft-join) — the recurring stale-pin lesson, handled proactively.
DB: answer bank gains `origin` (ai/human) and nullable `job_id` scope
columns (additive migration) to implement the reuse clarification.
**Rationale**: locked D2; the trace proved the gate never delivered
answers to the page anyway.
**Alternatives**: fixing the gate (push-on-confirm) — offered, user chose
removal.

## R12 — Subprocess AI isolation becomes the default

**Decision**: `_subprocess_enabled()` returns True unless
`JOBS_AI_SUBPROCESS == "0"`. The full battery, browser marker, slow gate,
and frozen smoke all run in this default mode on both OSes.
**Rationale**: 015 proved the mode (tests + frozen smoke, both installers)
and shipped it dark; RC5 shows thread mode cannot contain a native fault —
the tailor crash class requires process isolation. Unit tests are
unaffected (`set_executors_for_tests` bypasses the child).
**Alternatives**: keeping it opt-in + only wrapping tailor — rejected: any
single inference can fault (scoring proved 117 successes, but the crash
evidence is real); partial wrapping leaves the app killable.

## R13 — Generation bounds, load hygiene, tailor UX

**Decision**: explicit `max_tokens` per purpose (json/scoring+tailor
≈1536, drafts ≈512, prose ≈768) carried in the chat payload; tailor prompt
trimmed to the documented safe local band (≤6k chars combined resume+job),
`timeout_s=300`, 1 local attempt (cloud fallthrough unchanged);
`semantic._load_attempted` guard mirrors `local_llm`; embedder `n_batch`
capped (256) to halve its ≈537 MB scores buffer; tailor button gets an
honest long-running state and a rendered failure instead of a silent 502.
**Rationale**: tailor is the longest grammar-constrained generation with
unbounded output and a 2× over-band prompt — the highest-risk single
inference in the app; the embedder retry-loads 330 MB on every embed
today.
**Alternatives**: background-job tailor with polling — rejected for this
release (cheapest correct option chosen; isolation already removes the
crash risk).

## R14 — Verification harness

**Decision**: extend `tests/integration/test_pairing_e2e.py` (both browser
families): fixture posting where the form appears only after the
apply-opener click; a new-tab opener variant (watch transfer); radio +
native select + custom combobox fills asserted against the DOM; a
server-side submit-click log asserting ZERO automated submit clicks; a
serializer parity check (same fixture through `scanner.js` and the
watcher serializer → same logical fields). Engine-side: bridge
responsiveness (slow-draft seam; heartbeat stays fresh; profile fills
dispatch), one-draft hammer, fault containment on the default path
(child kill during tailor → app alive, restart counted). Frozen smoke
adds a tailor call and runs with the new default isolation.
**Rationale**: every reported symptom maps to an automated regression;
the 015 E2E harness (real uvicorn + Playwright `channel="chromium"` +
Edge) already supports extension loading and real tabs.
**Alternatives**: mock-level-only coverage — rejected: 015's history shows
the human path breaks precisely where mocks end.
