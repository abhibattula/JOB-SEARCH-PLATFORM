# Specification Analysis Report — Feature 021

**Run**: 2026-08-02, after `/speckit.tasks`, before implementation.
**Artifacts**: `spec.md`, `plan.md`, `tasks.md`, `research.md`, `data-model.md`,
`contracts/*`, `.specify/memory/constitution.md` (v1.2.0).

Read-only analysis. Every finding below was verified against the actual source
at the cited location, not inferred from the artifacts alone.

## Findings

| ID | Category | Severity | Location | Summary | Recommendation |
|---|---|---|---|---|---|
| A1 | Contract vs. code | **CRITICAL** | `engine/autofill/answer_bank.py:109` vs `contracts/observed_answer.md` | `save_with_provenance` upserts with an **unconditional** `ON CONFLICT … DO UPDATE SET`. FR-019's "never overwrite `user`/`confirmed`" is **unimplementable** by calling it, and T066 as written would silently destroy confirmed answers. | Add a guarded write. Do not modify `save_with_provenance` — other callers depend on its overwrite semantics. |
| A2 | Breaking change | **CRITICAL** | `engine/matcher.py:50`; 4 engine callers, 8 test assertions | T054 changes `scoring_tier()`, which is called **zero-arg** by `profile_import`, `resume_extract`, `upgrade` and `_chat`, and asserted in `test_matcher.py` (lines 100–116, 224–238) and `test_inference.py:231`. A signature or semantic change breaks all of them. | Add a **keyword-only** `purpose` parameter defaulting to today's exact behaviour. Zero-arg calls must return what they return now. |
| A3 | Breaking change | **CRITICAL** | `tasks.md` T022 vs `extension/content/panel.js:773,778,797,827,828` and `page_answers.py:46` | T022 says "keep `je_idx` as a list on the surviving row". `panel.js` uses `item.je_idx` as a **string** in five places, and it is a member of `_RENDERED`, which feeds the render digest. A list breaks Insert, Show me, the ask-input and change detection. | Keep `je_idx` a string (the first element). Add `je_idx_all: list[str]` and include it in `_RENDERED`. Purely additive. |
| A4 | Sequencing | **HIGH** | `plan.md` "Phase sequencing", `tasks.md` T012→T018 | T012 is a **manual capture on a live employer page**. As written it gates T018, which gates all of US1 and US2 — the entire P1 scope is serialised behind an action only the applicant can perform. | Split the gate. R1's three mechanisms are read from source and **certain**; only the field-count question is open. Build the fixture from the mechanisms plus the labels the applicant already pasted, ship US1/US2 against it, and let the real capture **validate and refine** rather than block. Only T028/T029 (`_frame_seen`) genuinely need T012. |
| A5 | Underspecification | **HIGH** | `tasks.md` T039 vs `engine/resume_extract.py:85` | T039 adds `location`, `is_current`, `field_of_study`, `gpa` to the entry models, but `_SYSTEM` pins "matching **exactly this schema**" and does not list them — so extraction would never populate them and US2 would fill nothing new from a fresh resume. Enlarging the prompt also spends budget that `resume_extract` documents as tight (a >6k-char prompt failed silently 100% of the time). | Add an explicit task to extend the extraction schema **and** re-measure prompt length against the documented safe band. Provide a deterministic fallback so the fields work with zero AI. |
| A6 | Coverage gap | **HIGH** | `engine/autofill/field_core.py:287-290` vs `contracts/observed_answer.md` | A field holding a value returns `settle`/`skipped_existing` **only when `tag != "free_text_unknown"`**; otherwise it returns a plain `skip`. US4's capture predicate keys off the settle path, so it would miss **every unclassified free-text field** — exactly the essay answers the applicant most wants learned. | The capture predicate must cover both branches. Add an explicit test for an unclassified free-text question. |
| A7 | Failure mode | **MEDIUM** | `engine/matcher.py:24` | `DEFAULT_MODEL = "llama-3.3-70b-versatile"`. Hosted model ids get retired. A tier switch that fails with an opaque 404 would recreate the exact silent-failure class FR-022 exists to remove. | Add an explicit unknown-model / auth-failure path that names the problem and falls back on-device. Do not let a cloud misconfiguration read as "the AI is broken". |
| A8 | Silent truncation | **MEDIUM** | `engine/autofill/ext_backend.py:207,775` | `MAX_PAGE_ENTRIES = 200` silently drops entries once reached. On the applicant's 156-field page this is close, and T027's pruning changes when it is hit. A silent cap on a review surface is the failure mode 018/019 were spent eliminating. | Surface the truncation in the panel (the `truncated` channel already exists) rather than dropping quietly. |
| A9 | Risk | **MEDIUM** | `tasks.md` T060 | KV-cache type quantization can fail model load outright on some llama-cpp builds. A hard failure here breaks **all** on-device AI. | Wrap in the existing load-retry pattern (`_load_model` already retries once on CPU) and abandon the setting on any load failure. |
| A10 | Ambiguity | **LOW** | `spec.md` FR-009 / `tasks.md` T026 | "absent from the last N scans" never fixes N. | Pin N = 3 in the data model; a single missed scan during a re-render must not evict a live field. |

## Coverage Summary

All 33 functional requirements map to at least one task; all 10 success
criteria map to a verifying task.

| Requirement group | Tasks | Notes |
|---|---|---|
| FR-001–003 (evidence) | T004–T012, T018 | A4 re-scopes the gate |
| FR-004–010 (review surface) | T019–T034 | A3 corrects the `je_idx` shape |
| FR-011–014 (history) | T035–T047 | A5 adds the extraction-prompt gap |
| FR-015–020 (learning) | T062–T073 | A1 and A6 are both blocking |
| FR-021–026 (responsiveness) | T048–T061 | A2 and A7 |
| FR-027–030 (placement) | T074–T081 | clean |
| FR-031–033 (breadth) | T082–T091 | clean |
| SC-001–010 | T033, T047, T044, T050, T051, T061, T073, T078, T086, T099 | clean |

**Unmapped tasks**: none.

## Constitution Alignment

No violations. Re-checked against v1.2.0:

- **Principle I** — no click added, removed or relaxed; the click-guard tests
  are extended, never edited.
- **Principle II** — cloud tier is a free tier already shipped; app remains
  fully functional with no key and no network (FR-026, T056).
- **Principle III** — every new source is an official public JSON endpoint
  through `base.py`'s existing rate limiter (T091).
- **Principle IV** — both new engine modules are pure; the import-boundary
  test covers them.
- **Principle V** — every new deterministic path is unit-tested first, and
  every refusal test is paired with a substance test (CHK004, CHK009, T063).

## Metrics

- Functional requirements: 33 · Success criteria: 10 · Tasks: 105 → **112**
  after remediation
- Requirement coverage: **100%**
- Critical findings: **3** (A1, A2, A3) — all breaking, all fixed before
  implementation
- High findings: **3** (A4, A5, A6)
- Ambiguity count: 1 (A10) · Duplication count: 0

## Next Actions

The three CRITICAL findings would each have produced a working-looking
implementation that silently destroyed data or broke the panel. All ten
findings are remediated in the artifacts **before** any code is written:
`tasks.md` gains T106–T112, T012/T018/T022/T039/T054/T060/T066 are rewritten,
and `data-model.md` pins N = 3.

Implementation may proceed after that remediation, starting at T001.
