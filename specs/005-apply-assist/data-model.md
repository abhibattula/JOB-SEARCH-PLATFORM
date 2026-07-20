# Data Model: Apply Assist

Extends the existing SQLite schema (`engine/db.py`, WAL mode, idempotent
`CREATE TABLE IF NOT EXISTS`/`ALTER TABLE` migrations). All new timestamps
follow the existing UTC-string convention. Two new tables, two new
`user_profile` columns, one new `settings`-table key convention, and two
resources that intentionally live *outside* SQLite (the bundled model file,
credential secrets).

## New tables

### answer_bank

The reusable "answered once, reused everywhere" store (spec FR-010–FR-013).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY | |
| question_normalized | TEXT | UNIQUE NOT NULL | casefolded/whitespace-collapsed form — exact-match key |
| question_raw | TEXT | NOT NULL | original wording, for display |
| answer | TEXT | NOT NULL | current confirmed answer |
| category | TEXT | NULL | one of the `engine/autofill/fields.py` taxonomy tags, e.g. `work_authorization`, `sponsorship_requirement`, `eeo_disclosure`, `years_experience`, `how_heard`, `free_text_unknown` |
| source | TEXT | DEFAULT 'user' | `user` (typed directly) \| `llm_suggested_confirmed` (AI-drafted, then user-confirmed) — **never** a third "unconfirmed" state, since a row only exists here once confirmed (FR-011) |
| confirmed_at | TEXT | NOT NULL | ISO datetime of first confirmation |
| updated_at | TEXT | NOT NULL | ISO datetime of last edit |

Index: `idx_answer_bank_norm` on `question_normalized` (exact-match lookup
before the `rapidfuzz` fuzzy pass — research item 7).

**Invariant**: a row is only ever inserted/updated via an explicit user
confirmation step (`engine/autofill/answer_bank.py::save()`); no code path
writes an AI draft directly into this table (FR-011, FR-012).

### application_answers

The per-application audit record (spec FR-021, added via clarify session),
distinct from `answer_bank`'s single current-answer-per-question record.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY | |
| job_id | INTEGER | FK → jobs.id, NOT NULL | which application this was used on |
| answer_bank_id | INTEGER | FK → answer_bank.id, NULL | NULL if the answer bank entry was later deleted — record still stands |
| question_raw | TEXT | NOT NULL | the exact wording encountered on this application (may differ slightly from `answer_bank.question_raw`) |
| answer_used | TEXT | NOT NULL | the exact answer text as used at the time — a copy, not a live reference, so later edits to `answer_bank.answer` don't retroactively change history |
| answered_at | TEXT | NOT NULL | ISO datetime |

Index: `(job_id)` — per-application lookup ("what did I submit on this
one?").

**Invariant**: `answer_used` is always a snapshot, never a foreign-key-only
reference to `answer_bank.answer` — this is the whole point of the table
(spec FR-021: "not affected by later edits").

## Modified tables

### user_profile

Two new nullable columns, filled in once on the existing Profile page,
consumed by `answer_bank.suggest()` (research item 7) to keep AI-drafted
suggestions grounded in facts the user actually provided rather than
inventing them:

| Column | Type | Notes |
|---|---|---|
| authorized_without_sponsorship | TEXT | NULL until the user sets it; free-text-or-boolean-ish, kept as TEXT for the same reason `preferences` is a JSON bag — avoids a migration if the UI's exact input shape changes |
| visa_status | TEXT | NULL until set (e.g., "OPT", "H-1B", "citizen") — display/context only, never itself auto-submitted anywhere |

### settings (existing key-value table, no schema change)

New key convention, reusing the established small-KV role (`engine/settings.py`):

| Key pattern | Value | Notes |
|---|---|---|
| `cred_email:{domain}` | email string | "which identifier is saved for this domain" — the **password itself never appears here or anywhere in SQLite**; it lives only in the OS keychain via `keyring` (research item 8) |

## Resources intentionally outside SQLite

- **Bundled local model file**: a single `.gguf` file shipped as PyInstaller
  `datas`, resolved via `paths.resource_path()` (dev) / frozen bundle path
  (installed). Not a DB row — its "availability" is a runtime check
  (`engine/local_llm.py::available()`), not persisted state.
- **Credential secrets**: stored exclusively in the OS keychain
  (`keyring.set_password(domain, email, password)`). SQLite holds only the
  `cred_email:{domain}` hint above — deleting a credential means calling
  `keyring.delete_password` **and** clearing the settings key; neither alone
  is sufficient (`engine/credentials.py::delete()` does both).
- **Downloaded Chromium binary**: lives under
  `paths.data_dir() / "browsers"`, managed by Playwright's own install
  mechanism, not tracked in SQLite. Its presence/absence is what
  `engine/autofill/browser_setup.py` checks to decide whether "Enable Apply
  Assist" needs to run the one-time install.

## State transitions

### Answer bank entry lifecycle

```
(no row) ──user confirms draft or types answer──▶ confirmed (source recorded)
confirmed ──user edits later──▶ confirmed (updated_at bumped, answer_used
                                            snapshots in application_answers
                                            are unaffected)
```

There is no "unconfirmed" persisted state — an AI draft that hasn't been
confirmed yet exists only transiently in the UI/session, never written to
`answer_bank` (FR-011).

### Apply session / queue (in-memory, not persisted to SQLite)

```
idle ──start_queue(job_ids)──▶ running (current_job = job_ids[0])
running ──user clicks "Done, next"──▶ running (current_job = next id)
                                    │
                                    └─▶ idle (queue exhausted)
running ──stop_queue()──▶ idle
```

Deliberately not persisted: if the app restarts mid-queue, the user
re-selects and re-starts rather than resuming an automated browser session
across a process boundary — consistent with "the human is always in the
loop" (no requirement in spec.md calls for cross-restart resumption).

## Validation rules (from FRs)

- `answer_bank` rows for `category IN ('work_authorization',
  'sponsorship_requirement')` MUST only ever be created/updated through the
  explicit-confirmation path — never written by an automated/background
  process (FR-012).
- `application_answers.answer_used` MUST be captured at write time and MUST
  NOT be recomputed from the current `answer_bank` state later (FR-021).
- A saved credential's password MUST NOT be retrievable through any query
  path other than `engine/credentials.py::get()`, which itself only reads
  from the OS keychain (FR-017).
- Deleting a saved credential (`engine/credentials.py::delete()`) MUST clear
  both the keychain entry and the `cred_email:{domain}` settings row —
  leaving either behind is a bug (a stray settings row would show a domain
  as "saved" with no retrievable secret; a stray keychain entry would leak
  outside the app's own bookkeeping).
