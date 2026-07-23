# Data Model: The Copilot Release (010)

All storage stays in SQLite via engine/db.py. Additive column migrations
only (init_db is serialized + idempotent as of 009's race fix). The
companion itself stores nothing durable (stateless by design).

## Changed entities

### answers (existing table — answer bank)

| Column (new) | Type | Notes |
|---|---|---|
| provenance | TEXT DEFAULT 'user' | `user` (typed/confirmed in Profile, incl. 006 flows) · `confirmed` (AI draft explicitly confirmed/edited in app) · `auto_saved` (final on-page text captured on confirmed submission) |
| drafted_at | TEXT | when the AI draft that produced this answer was generated (NULL for pure user answers) |
| source_job_id | INTEGER | job the draft/auto-save came from (provenance display only) |

Rules:
- Saved-answer matching (existing normalized-question match) always runs
  before AI drafting; provenance never affects matching priority.
- `auto_saved` answers are editable/deletable in Profile like any answer
  and display an "auto-saved from application" badge (FR-013).
- Sensitive-tagged questions (work-auth/visa/EEO) can never carry
  `ai_draft` lineage — enforced at generation (allowlist) AND at save.

### ai_drafts (NEW table — session-scoped draft ledger)

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| job_id | INTEGER NULL | NULL for ad-hoc sessions until linked |
| question | TEXT | normalized question text |
| draft_text | TEXT | generated draft as filled |
| status | TEXT | `drafted` → `confirmed` \| `auto_saved` \| `discarded` |
| tier | TEXT | local/cloud (provenance display) |
| created_at | TEXT | |

Lifecycle: `drafted` on fill; → `confirmed` via app review (writes/updates
answers row, provenance `confirmed`); → `auto_saved` on confirmed
submission (writes answers row, provenance `auto_saved`); → `discarded`
by user. Rows are pruned with their job's fill report (same retention).

### applications / job status (existing)

| Column (new) | Type | Notes |
|---|---|---|
| follow_up_at | TEXT NULL | user-set follow-up date (FR-019) |
| notes | TEXT | per-application free text (FR-019) |

Detected submission does NOT write status — it creates a pending
next-action; only user confirmation advances status (FR-020).

### settings (existing key-value)

| Key (new) | Notes |
|---|---|
| bridge_secret | 32-byte random token (hex), generated on first init; NOT a password — machine-local session gate |
| AUTOFILL_BACKEND | `auto` (default) \| `extension` \| `playwright` |

## Session-scoped (in-memory, engine/autofill state — not persisted)

- **CompanionSession**: `{connected, version, chrome_version, last_seen,
  send()}` — at most one; newer hello supersedes (close 4409).
- **Backend**: `_state.backend` chosen at start_queue, sticky per queue.
- **Ad-hoc session**: `{tab_id, url, title, report[]}` keyed by tab;
  offered tracker linkage on completion (match by URL → existing job,
  else create job row on user confirm).
- **Handled ledger**: unchanged from 009 — `(doc_token, je_idx) →
  terminal outcome`, now fed by either backend. New terminal outcome
  vocabulary addition: `ai_draft` (terminal for the session; the field
  is filled and flagged).
- **Next-actions** (derived, not stored): drafts awaiting review (from
  ai_drafts), follow-ups due (follow_up_at <= today), import ready
  (existing profile_import state), submission confirmations pending.

## Extension-side state (explicitly bounded)

- `chrome.storage.local`: last-known-good port ONLY. Never secrets,
  never profile data, never fill values.
- DOM: `data-je-idx` stamps + doc token attributes (survive reloads,
  meaningless outside the page).
- Everything else lives in SW memory and dies with it (stateless by
  design — the app is the source of truth).
