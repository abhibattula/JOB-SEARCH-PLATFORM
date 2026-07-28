# Research: Feature 017 — The Truthful Fill

**Date**: 2026-07-28 · **Spec**: [spec.md](./spec.md)

All decisions are grounded in the live Akuna Capital Greenhouse run
(2026-07-28) and in code read during planning. File:line references are the
state of `main` at commit `e64245d` (v1.6.0).

---

## R1 — The 170 drafts are historical rows, not a regeneration loop

**CORRECTED 2026-07-28, after reading the code.** An earlier reading of this
defect claimed a self-feeding loop in which each completed draft reset every
other question's backoff. **That is wrong** and no fix should be written for
it:

- `drafter.reset_backoff_for_job` is called from exactly one place,
  `ext_backend._handle_fill_again` (`ext_backend.py:307`) — the *explicit user
  action*. The adjacent `rescan` send on line 308 belongs to the same handler.
- `browser_controller.on_draft_complete` (`:402-416`) sends only a `rescan`
  nudge; it touches no drafter state.
- `drafter._key` already normalises the question (`drafter.py:65`), so
  whitespace or marker variations cannot fragment one question into many keys.
- The live run's own evidence settles it: the **Question activity** list shows
  each question **exactly once** ("Graduation Month*", "What is your GPA?",
  "Have you ever applied…"), which is the in-memory drafter state. Only the
  separate **"AI drafts to review (170)"** block duplicates.

**Actual cause**: that block renders `drafts.list_for_job(job_id)` — the
SQLite `ai_drafts` table (`autofill_status.html:141-148`). `ai_drafts` has
exactly one writer, `drafts.record`, and **no production caller since 016**
(`grep` across `engine/` and `web/` finds only tests). Its rows are therefore
historical: accumulated by earlier app versions across repeated attempts at
the same saved job, never pruned in practice, and re-rendered in full on every
3-second poll. Several of the 170 answers are visibly from older prompts.

**Decision**:

1. Make the review surface reflect the **current run** — the live drafter
   state — rather than a legacy table (this is R23's reconciliation, now
   answered).
2. Bound and de-duplicate `ai_drafts` at the schema level
   (`UNIQUE(job_id, question)`) and give it a real writer, so it can serve as
   the restart-durability store (R3) instead of an orphaned log.
3. Prune on session start so historical rows cannot resurface.

**What this does NOT change**: R2's attempt cap and per-job draft budget are
retained as *bounds*, not as a fix for an observed storm — the drafter is
already correctly idempotent within a run, and the caps exist so a
pathological form cannot become one. The honest justification is prevention,
not repair.

**Alternatives considered**: deleting the legacy table and its UI outright
(loses the only place a user can edit and confirm an answer, and 016 already
replaced the blocking gate with a passive log — the edit affordance is still
wanted); leaving the table and only capping the rendered rows (the block would
still show answers from months-old runs as if they were current).

## R2 — Bounded generation

**Decision**: `MAX_ATTEMPTS_PER_QUESTION = 2` and `MAX_DRAFTS_PER_JOB = 40`.
On exhaustion the record becomes `failed` with reason `attempts_exhausted` /
`job_budget_exhausted`, both added to `_NEEDS_YOU_REASONS` so the field is
flagged on the page rather than silently skipped.

**Rationale**: two attempts covers a transient generator error without ever
producing the 10–15 variants seen in the run. 40 is comfortably above the
distinct-question count of the largest real form observed (~30) while bounding
worst-case model time.

**Alternatives considered**: unlimited with a time budget (unpredictable on a
cold model); one attempt (a single transient timeout would permanently flag a
question the model could answer).

## R3 — Records that survive a restart

**Decision**: persist drafter outcomes to the existing `ai_drafts` table keyed
uniquely on `(job_id, question)` — one row per question, updated in place —
and rehydrate `_records` for the active job on session start. In-memory
`_records` remains the hot path.

**Rationale**: `_records` is process memory (`drafter.py:50`); a crash or
restart re-drafts an entire form. `ai_drafts` already exists with the right
shape and a retention policy (`drafts.prune_stale`).

**Alternatives considered**: a new table (duplicates `ai_drafts`); no
persistence plus a bigger cap (still re-runs the whole form after the crash
banner the user saw).

## R4 — The drafter must be able to refuse

**Decision**: `answer_bank.suggest` gains the refusal contract `qa.draft`
already has (`qa.py:34`, `_REFUSAL_TOKEN = "CANNOT_ANSWER"`): the system prompt
states that anything not present in the applicant's own resume/profile must be
answered with the refusal token, and `drafter._validate` maps that token to
`(False, None, "cannot_answer")`, a non-retryable needs-you reason.

**Rationale**: the live path has **no** refusal branch (`answer_bank.py:198-211`
always returns text), which is why the model asserted the applicant had
interned at Akuna, completed Akuna's course, held an offer deadline, and lived
in California. The legacy `qa.draft` path already solved this; the mechanism
just never reached the path 016 actually uses.

**Alternatives considered**: post-hoc fact-checking of generated text (needs a
second model call and cannot verify a negative); a confidence score (models are
poorly calibrated on autobiographical facts they were never given).

## R5 — Prompt isolation is already correct; keep it that way

**CORRECTED 2026-07-28.** An earlier reading blamed the fabrications on job
context leaking into the factual prompt. **The live path does not pass job
context at all**: `answer_bank.suggest` builds its grounding as
`f"RESUME/PROFILE:\n{resume_text[:4000]}"` (`answer_bank.py:170`) and receives
no job argument. The company name reaches the model only inside the question
text itself ("…with **Akuna** in the past?"), which is legitimate and
unavoidable.

The drafts that read like contamination — "I am currently an embedded systems
intern at Akuna Capital University", which is the app's own company field —
are consistent with R1's finding that most of the 170 rows are **historical**,
produced by the pre-016 flow where `qa.draft(question, tag, profile, job)` did
receive the job.

**Decision**: keep the current separation and pin it with a regression test —
the factual prompt asserts no company/role/description text, and only the
cover-letter prompt may receive them. This is a guard against reintroducing an
old defect, not a repair of a current one.

**Consequence**: the fabrication fix rests entirely on **R4 (the refusal
contract)** and **R6 (never generating factual-history answers)**. The live
run's own activity log confirms the current path still fabricates — "Have you
ever applied to a full time or internship position with Akuna in the past?" →
"Yes, I have applied…" — because `suggest` has no way to say it does not know.

## R6 — Factual-history questions are never AI-answered

**Decision**: a new tag class — `applied_before`, `worked_here_before`,
`prior_industry_experience`, `completed_course`, `offer_deadlines`,
`residency_state`, `currently_employed` — joins the never-generated set and
resolves from the profile / answer library or becomes needs-you.

**Naming**: `drafter.SENSITIVE_TAGS` is renamed `NEVER_GENERATED_TAGS`, with
`SENSITIVE_TAGS` retained as a module-level alias so existing tests and the
016 vocabulary keep working. "Sensitive" no longer describes the set: an
"offer deadlines" question is not sensitive, it is simply unknowable from a
résumé. This name is used consistently across spec, data-model and tasks.

**Rationale**: these are unknowable from a resume; every one of them was
fabricated in the run. They are also exactly the questions a user can answer
once and reuse forever (D7).

**Alternatives considered**: allowing generation with a refusal fallback (R4
would catch most, but a resume that mentions any options firm would still let
the model assert prior market-making experience).

## R7 — Answer shape must match field shape

**Decision**: a shared, pure predicate decides whether a candidate value may be
written to a descriptor, enforced in **both** `field_core.decide` (before
emitting a fill) and `drafter._validate` (before accepting a generation):

| Field shape | Accepts |
|---|---|
| choice with known options | exactly one option (after canonical matching) |
| choice with unknown options (custom combobox / nested input) | a short option-like label: ≤ 4 words, no sentence punctuation |
| radio group / checkbox group | member labels only |
| free text with `maxlength` | text within the limit |
| free text, work-auth/date/description intent | a structured profile value — never a yes/no token |

**Rationale**: two separate defects share one cause. `qa.profile_fact_answer`
returns "Yes"/"No" for any `work_authorization` / `sponsorship_requirement`
label, so four Akuna free-text questions ("when does it expire?", "what is your
current immigration status?", "list any extension options", "additional
detail") each received "Yes". Symmetrically, prose reached dropdowns because
`drafter._validate`'s word cap is keyed on the `custom_combobox` flag
(`drafter.py:105`) and the offending element didn't carry it.

**Alternatives considered**: fixing only the yes/no case (leaves the prose case
and any future shape mismatch); trusting the classifier to be more specific
(the label genuinely is a work-authorization question — the field shape is the
discriminator, not the topic).

## R8 — Stop double-capturing custom dropdowns

**Decision**: both serializers drop a candidate element when an **ancestor is
also captured and is a choice widget** (`[role=combobox]`, `[role=listbox]`,
`[aria-haspopup=listbox]`, `[class*=select__control]`). Any input that still
survives inside such an ancestor inherits `widget: "custom_combobox"`.

**Rationale**: a React-select control yields two descriptors — the wrapper
(`custom_combobox`) and its nested search `<input>`, which `jeWidget` scores as
`""` (scanner.js:25-37) and which owns the `<label for>`, so it inherits the
450-character acknowledgement text and becomes a free-text essay question. The
wrapper is the field; the inner input is part of the widget, and `fillCombobox`
already drives it through the wrapper.

**Alternatives considered**: excluding inputs by class name (brittle across
libraries); keeping both and de-duplicating app-side by label (loses the stable
`je_idx` ledger key and would still draft twice on the first scan).

## R9 — Checkbox groups become one logical question, with no protocol change

**Decision**: merge same-name/same-fieldset checkbox sets into ONE descriptor
(`type: "checkbox_group"`, question from the legend, `options` from member
labels, `je_idx` from the first member — the radio-merge pattern from 016), but
emit **one existing `kind:"checkbox"` FillItem per selected member**, addressed
by that member's `je_idx`.

**Rationale**: the Akuna pronoun group produced five separate essay drafts
("… — She/her/hers", "… — He/him/his", …) because 016 deliberately never merges
checkboxes. Merging fixes the drafting side; emitting per-member checkbox fills
means **no new wire kind**, so old companions cannot mis-fill and no version
gate is needed. This reverses a 016 decision, deliberately and narrowly:
multi-select is preserved because several members may be checked.

**Alternatives considered**: a new `checkbox_group` FillItem kind (needs a
version gate and a new filler branch for no behavioural gain); leaving
checkboxes unmerged and suppressing drafting for them (the group question would
still be unanswerable).

## R10 — Classifier repairs and document-level name layout

**Decision**:
- `_PHONE_RE` → word-bounded (`\bphone\b|\bmobile\b|\btelephone\b|\bcell\b`).
- Name patterns require self-reference; a possessive third-party context
  (`their|his|her|employee|referrer|reference|manager|supervisor|contact`
  within a short window before "name") disqualifies every name tag.
- New `preferred_name` and `middle_name` tags matched **before** the full-name
  rule, so `\bname\b` can no longer swallow "Preferred Name".
- New pure `field_core.name_layout(descriptors) -> dict[je_idx, tag]`: if the
  document contains a `last_name` field, a sibling `full_name` is demoted to
  `first_name`; a lone name field stays `full_name`.

**Rationale**: `_PHONE_RE` (`fields.py:71`) has no word boundary, so
"**phon**etically" matched and the phone number went into the name-pronunciation
box. `_FULL_NAME_RE` (`fields.py:75`) ends in a bare `\bname\b`, so "please
list **their** name" received the applicant's own name. Classification is
per-descriptor with no page context (`fields.py:91-162`), so first-vs-full can
only be resolved with a document-level pass.

**Alternatives considered**: dropping `\bname\b` entirely (breaks Lever's bare
`name=` attribute, pinned by `tests/test_fields.py:222`); resolving names in
each backend separately (drift between the two executors).

## R11 — Profile storage: additive columns

**Decision**: extend `user_profile` with additive `TEXT` columns through the
existing `_MIGRATIONS` list (`db.py:201-217`) and `_PROFILE_COLUMNS`
(`db.py:1146`). Work history, education and projects are **not** duplicated —
they already live in `resume_sections`. Fix the latent `target_titles` drop in
the same pass.

**Rationale**: the migration mechanism is designed for exactly this and every
consumer reads `profile.get("x")`. A JSON blob would need flattening on read to
keep `_value_for_tag` simple, and a side table would add a join for a
single-row entity.

**Alternatives considered**: `profile_details` JSON column (opaque to queries,
no per-field migration story); a key/value `profile_fields` table (over-general
for a single-user, single-row profile).

## R12 — One resolver module

**Decision**: new pure `engine/autofill/profile_answers.py` exposing
`PROFILE_ANSWER_TAGS` and `answer_for(tag, descriptor, profile) -> str | None`.
`browser_controller._value_for_tag` delegates to it before the answer-bank →
drafter path; `qa.PROFILE_FACT_TAGS` / `qa.profile_fact_answer` fold into it.

**Rationale**: `_value_for_tag` is already a 75-line `if tag ==` ladder
(`browser_controller.py:324-399`) and this feature roughly triples the tag
count. A pure module is unit-testable without a browser, keeps `engine/` free
of web imports, and gives R7's shape rule one place to consult.

**Alternatives considered**: growing the ladder (untestable in isolation,
duplicated between backends); a table-driven mapping only (some tags need
derivation, e.g. full name from parts, yes/no from sponsorship state).

## R13 — The pre-answered library is tag-keyed, not text-matched

**Decision**: common application questions get classifier tags and resolve
through `profile_answers`. `answer_bank` remains the free-form fallback and the
store for D7-captured answers.

**Rationale**: `answer_bank.lookup` normalises and fuzzy-matches the question at
`ratio ≥ 85` (`answer_bank.py:34-55`). Real phrasings of the same question
diverge far more than that — "Are you 18 years or older?" vs "Are you at least
18 years of age?" scores well below the threshold — so a text-keyed library
would silently miss and fall through to generation.

**Alternatives considered**: lowering the fuzzy threshold (raises false
positives, which on an application means a confidently wrong answer);
embedding-based question matching (a model call on the hot path, and still
unbounded).

## R14 — Canonical vocabulary and a fourth matching pass

**Decision**: new pure `engine/autofill/vocab.py` holding canonical values and
synonym sets per family (gender, race/ethnicity, veteran, disability,
orientation, pronouns, yes/no, work authorization, education level, remote
preference, decline-to-answer). `fields.match_option(answer, options, tag=None)`
gains a fourth pass: canonicalise the answer and each option within the tag's
family and compare canonical forms. Passes 1–3 (exact, prefix,
`rapidfuzz ≥ 87`) are untouched.

**Rationale**: `Male` vs `Man` scores ≈ 57 and `Y` vs `Yes` scores 50, both far
below the threshold, so today they simply do not match. Canonical comparison is
exact — it adds no fuzziness, which matters because the same function decides
authorization dropdowns where a wrong answer is worse than a blank.

**Alternatives considered**: lowering `OPTION_MATCH_CONFIDENCE` (would let
"Male" match "Female" at some thresholds); embedding similarity (non-deterministic,
model-dependent, and unavailable offline on a cold start).

## R15 — Self-identification: never generated, but answerable (supersedes 016 FR-013)

**Decision**: split `_EEO_RE` into real producer tags — `selfid_gender`,
`selfid_race`, `selfid_veteran`, `selfid_disability`, `selfid_orientation`,
`pronouns` — and add producers for `criminal_history` and `references`. All
remain in the never-generated set; all resolve from stored self-ID values
through `profile_answers` + `vocab`. Blank stays blank.

**Rationale**: 016 refused these questions entirely; the user asked for them to
be answered from their own stored values (D1). Two live defects also require
the tag split: a bare "Gender" label does not match `_EEO_RE` (which requires
"gender identity", `fields.py:41-44`) and therefore reaches the drafter today,
and `criminal_history` / `references` sit on the denylist with **no producer**,
so they fall through to `free_text_unknown` and are generated.

**Alternatives considered**: keeping one coarse `eeo_disclosure` tag (cannot
map a stored gender onto the right question); storing self-ID as answer-bank
rows as today (fragile in two stages — question fuzzy-match, then option match).

## R16 — Acknowledgements split by consequence (D5)

**Decision**: new `acknowledgement` tag ("I acknowledge", "I certify", "I
agree", "I consent", "By submitting", "I understand that"), sub-classified as
**binding** when exclusivity language is present ("top preference", "will not
be considered", "sole application", "not be considered for other", "non-compete").
Routine acknowledgements resolve from the library; binding ones are never
answered and are surfaced with full question text.

**Rationale**: the Akuna exclusivity acknowledgement received a paragraph, and
answering it "Yes" would have withdrawn the applicant from every other Tech and
Quant role at that firm for the season. Consequence, not topic, is the right
discriminator.

**Alternatives considered**: treating all acknowledgements as binding (adds
clicks to every application for terms/accuracy boilerplate); auto-answering all
of them (the failure is unrecoverable and invisible).

## R17 — Resume transport: through the service worker, with verification

**Decision**: the content script requests the file from the background service
worker (`{type: "fetch_file", path}`); the SW resolves it against
`http://127.0.0.1:<port>` from `pairing.json`, fetches with its host
permission, and returns `{name, mime, bytes}`. `filler.js` builds the `File`
from that. The response is rejected unless it looks like the expected document
(PDF magic bytes `%PDF`, non-zero length, size within tolerance of the
app-declared size).

**Rationale**: `ext_backend.py:430` emits a **relative** `file_url`, which a
content script resolves against the job board. On Greenhouse that path returns
the SPA's HTML with status 200, so `attachFile` (`filler.js:120-129`) wraps
HTML in a `File` named `resume.pdf` and reports `filled` — the applicant would
submit an HTML page as their résumé. Making the URL absolute does not help:
MV3 content-script fetches carry the page's origin and are subject to CORS, and
the app sets no CORS headers. The SW does hold
`host_permissions: ["http://127.0.0.1/*"]`, and `main.js:22` already states the
rule that content scripts must not hit loopback directly.

**Alternatives considered**: adding CORS headers to the bridge file route and
using an absolute URL (widens a loopback endpoint to every page origin);
`web_accessible_resources` (the file is user data, not a bundled asset).

## R18 — Which document is attached (D6)

**Decision**: attach the tailored PDF only when tailoring was actually
performed for that job — i.e. the job row carries a non-empty `tailor_json` —
otherwise attach `profile.resume_file_path`, the applicant's own upload. The
resolved filename travels to the page (R19) and is shown in the panel.

**Rationale**: `_resume_file_for_job` (`browser_controller.py:298-310`)
currently calls `resume_pdf.tailored_resume_path(job_id)` whenever the setting
is on, and that function renders from `resume_sections` even when no tailoring
ran. In the live run the attached file was `6532.pdf` — an app-generated
rendering — on a job the applicant had not tailored. The user's own PDF is the
document they chose to represent them.

**Alternatives considered**: always the upload (loses the tailored document the
user explicitly asked for when they do tailor); asking per job (a click on
every application).

## R19 — Protocol additions (PROTOCOL_V stays 1)

**Decision**, all additive with defaults, per the rule documented at
`ext_protocol.py:68-72`:

| Direction | Message / field | Purpose |
|---|---|---|
| app → ext | `answers` `{tab_id, job_id, items:[{je_idx, question, answer, state, reason}]}` | full answer text on the page (FR-034) |
| app → ext | `rescan` — **implement the existing handler** | FR-037 |
| ext → app | `answer_question` `{tab_id, je_idx, question, answer}` | D7 capture (FR-045) |
| ext → app | `apply_here` `{tab_id, url, title, company, description}` | badge launcher (FR-038) |
| field | `FillItem.filename`, `FillItem.mime` | real upload name (FR-031) |
| field | `Descriptor.type: "checkbox_group"`, reuses `members` | R9 |

No new `FillItem.kind` is introduced, so the existing exact-version gate
(`ext_backend.py:443-455`) needs no new entry and an older companion cannot
mis-fill; it simply ignores unknown message types (`protocol.js:22-27` drops on
version only, and unknown types hit `default: break`).

**Rationale**: bumping `PROTOCOL_V` hard-rejects every older companion with
close code 4426 (`routes_bridge.py:143-148`) — rejected for the same reason as
in 016.

## R20 — One floating widget (D4)

**Decision**: the discovery badge (`je-discovery-badge-host`, bottom-right,
**open** shadow root) becomes the launcher and calls `window.jeOverlay.show()`;
the fill panel (`je-companion-overlay-host`) switches from a **closed** to an
**open** shadow root with `dataset` mirrors. The badge continues to write
nothing to the page — its new button only sends `apply_here`.

**Rationale**: both content scripts share one isolated world, so
`window.jeOverlay` is directly reachable from `discovery.js`; no message hop is
needed. The badge already uses an open root explicitly so integration tests can
drive its Save button (`discovery.js:186-188`) — the panel needs the same for
its new answer list to be assertable. The read-only static guard on
`discovery.js` (`tests/test_extension_assets.py:159-180`) still holds because
`addEventListener` is not `.click(`.

**Alternatives considered**: a third floating element (clutter, and the user
explicitly asked for one); keeping the panel closed and asserting via the
fixture beacon only (cannot verify copy/insert affordances).

## R21 — Status UI that can always be stopped

**Decision**: split `partials/autofill_status.html` so the controls (Stop,
Done, Re-scan) live in a **sticky, non-polled** region outside the htmx swap
target; give the polled region `hx-swap="innerHTML show:none"` so a swap never
moves the viewport; render at most 20 drafts with a "show all" disclosure; and
skip the poll while the user is focused inside the panel.

**Rationale**: the whole status page is one swap target polled every 3 s
(`autofill.html:127`) and renders every draft (`autofill_status.html:141-181`).
With 170 drafts the page grew past the point where the user could scroll to
Stop. Fixing R1–R3 removes the 170, but the controls must be reachable
regardless of form size.

**Alternatives considered**: pagination alone (still re-anchors the scroll on
every swap); a floating stop button (duplicates state; the sticky region is the
same markup).

## R22 — Purging fabricated answers

**Decision**: an explicit "reset learned answers" action deleting `answer_bank`
rows whose `source = 'ai'` and `ai_drafts` rows not confirmed by the user,
surfaced on the Profile answer-bank section, with a count shown before
confirming. D7-captured answers are stored as the applicant's own
(`source = 'user'`, FR-046) and are never removed by it.

**Rationale**: the drafter auto-saves accepted answers to the bank
(`drafter._run_completion_effects` → `answer_bank.save_auto(origin="ai")`), so
the run's fabrications will refill on future applications until removed. The
`source` column already distinguishes provenance (`db.py:218-223`).

## R23 — Reconcile the draft-review surface before changing it

**Decision**: before touching the in-app review UI, pin its actual data source
with a test, then converge it on the same feed the page uses.

**Rationale**: `INSERT INTO ai_drafts` has exactly one writer (`drafts.record`)
and no production caller, yet the app rendered 170 editable draft rows in the
live run. One of those two observations is wrong, and changing the UI before
knowing which would be guesswork.

## R24 — Test strategy

**Decision**: every defect above gets a failing test first. The Akuna form is
reproduced as fixture markup — a React-select dropdown with a 400-character
acknowledgement label and a nested search input, a binding-exclusivity variant,
a pronoun checkbox group, a "list their name" field, a work-auth expiry text
field, a gender select worded "Man/Woman/Prefer not to say", a location
typeahead, and a lone-"Name" variant — plus a `change` handler and
`resume_filename` / `resume_size` beacon fields on the existing file input,
which nothing observes today.

**Rationale**: the fixture is the only place these shapes can be asserted
end-to-end; extension-opened tabs are invisible to Playwright, so the fixture's
self-reporting beacon (`practice_apply.html:129-149`) remains the observation
channel.
