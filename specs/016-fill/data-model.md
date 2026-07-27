# Data Model: The Fill Release (016)

All storage is additive: two new answer-bank columns (guarded `ALTER
TABLE`), extension session storage, and in-memory caches. No new files, no
schema rewrites.

## 1. Logical field (wire descriptor, additive)

Existing `Descriptor` (ext_protocol) gains:

| Field | Type | Notes |
|---|---|---|
| `members` | list of `{je_idx: int, label: str}` (default `[]`) | radio-group members; empty for non-groups |
| `required` | bool (default false) | from `required`/`aria-required` |

Grouping rules (both serializers, parity-tested):
- Radios sharing `name` (or under `role=radiogroup`/one fieldset) → ONE
  descriptor: `type="radio_group"`, `label_text` = legend/group label,
  `options` = member labels, `je_idx` = first member's, `members` filled.
- Checkbox groups: NOT merged; each member keeps its own descriptor with
  the group legend prefixed into its question context.
- Native selects unchanged (options already captured). Custom comboboxes
  unchanged (`widget=custom_combobox`, options harvested at fill time).

Identity: ledger key stays `(doc_token, je_idx)`; a group's identity is
its first member's index, deterministic across rescans of the same DOM.

## 2. Draft record (in-memory, `engine/autofill/drafter.py`)

| Field | Type | Notes |
|---|---|---|
| `key` | `(job_id, normalized_question)` | normalization: casefold, collapse whitespace, strip punctuation |
| `state` | `drafting \| done \| failed` | |
| `answer` | str \| None | validated (options / length) before `done` |
| `attempts` | int | |
| `next_retry_at` | monotonic float | exponential backoff 30 s ×2, cap 600 s |
| `descriptor_ctx` | `{type, options, maxlength, tag}` | drives constrained prompting |

Lifecycle: `ensure()` is idempotent per key; completion writes the answer
bank (see §6) and triggers ledger-clear + `rescan` push. `Fill again`
resets `next_retry_at` for the page's keys. Session-scoped (cleared on
app restart); `reset_for_tests()` provided.

## 3. Watch target (extension session + app memory)

- Service worker: `watched` set persisted to `chrome.storage.session`
  (survives MV3 worker restarts; dies with the browser session).
- App: `_watch = {tab_id, job_id, pending_open{req_id: deadline}}` —
  singular; `child_tab` transfers `tab_id` to the newest child.
- `open_tab`: ack deadline 5 s, one retry, then `launch_failed` outcome
  and queue advance.

## 4. Field outcome (ledger entry, extended)

| Field | Type | Notes |
|---|---|---|
| `outcome` | `filled \| skipped_existing \| no_match \| needs_manual \| focused \| not_found` | as today |
| `cache_version` | int | drafter cache generation used for the decision |

Retryability: a terminal entry whose `cache_version` is older than the
current answer for that question is treated as retryable on the next scan.
`_inflight` entries expire after 20 s.

## 5. On-page annotation (extension DOM state)

| Field | Notes |
|---|---|
| `je_idx` | anchor element |
| `flag` | `ai_draft` (drafted answer placed) \| `needs_you` (unfilled: sensitive/no-match/version-gated) |
| cleared by | `input` event on the element |

Rendered as outline + badge from the overlay's shadow DOM; recomputed
per fill batch; survives rescans (reapplied while the flag holds).

## 6. Answer bank (SQLite, additive columns)

`answer_bank` gains:

| Column | Type | Notes |
|---|---|---|
| `origin` | TEXT DEFAULT 'human' | `'ai'` for auto-saved drafts |
| `job_id` | INTEGER NULL | non-NULL = job-scoped (job-specific prose) |

Reuse rules: lookup for job B ignores rows where `job_id IS NOT NULL AND
job_id != B`. Job-specific prose tags (`cover_letter`, why-us style
`free_text_unknown` drafts) auto-save with `job_id` set; job-agnostic
factual tags save unscoped. Human-confirmed saves keep today's behavior
(unscoped, `origin='human'`).

## 7. AI runtime status (existing, defaults change)

`JOBS_AI_SUBPROCESS` unset/`"1"` → isolated child (default);` "0"` →
thread mode. Restart count + mode already surfaced via doctor/diagnostics
(015); no shape change.

## 8. Employer cache (in-memory, `engine/db.py`)

`load_h1b_employers()` memoized (module-level, invalidated by the
sponsorship refresh write path). Extension-side: score result cached per
`href`; re-requested only on URL change.

## 9. Activity log entry (app UI payload, additive)

`current_job()` / autofill status payload gains `activity`: list of
`{question, state: drafting|drafted|filled|needs_you, answer_preview,
bank_id?}` replacing the blocking `pending` object (which is removed).

## 10. Doctor counters (additive)

`/api/companion/doctor` gains `dropped_fields` (wrong-tab fields
messages) and `scan_errors` (content-script reported scanner failures).
Secret continues to NEVER appear in doctor output.
