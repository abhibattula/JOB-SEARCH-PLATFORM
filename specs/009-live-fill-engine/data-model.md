# Data Model — Feature 009 (The Live Fill Engine)

**No SQLite schema migration.** Everything new is session-scoped memory,
settings KV, or bundled assets.

## In-memory: fill-engine state (engine/autofill)

`_State` (browser_controller, preserved fields + additions):

| Field | Type | Notes |
|---|---|---|
| `job_ids/index/running/outcomes/pending/fill_reports/interrupted/summary` | as 008 | semantics preserved (queue machine, reason classes, masked reports, single pending slot, batch summary) |
| `activity` | dict | `{phase: idle\|opening\|watching\|waiting_for_form\|interrupted\|error, fields_seen: int, fields_filled: int, message: str, last_scan_at: iso\|None, url: str\|None}` |
| `filled_keys` | set[(frame_key, je_idx)] per job | idempotency + report dedupe |
| `practice` | bool | current queue entry is the practice page (no DB job row) |

Worker command (engine/autofill/worker.py):

| Field | Type |
|---|---|
| `name` | `OPEN_JOB \| OPEN_PRACTICE \| FORCE_TICK \| CLOSE_PAGE \| RESOLVE_PENDING \| SHUTDOWN_CONTEXT` |
| `payload` | dict (job_id · url · frame_key/je_idx/answer) |
| `done` | optional `threading.Event` (only RESOLVE_PENDING waits, ≤0.5s) |

Field descriptor (watcher serialization, superset of 008's):
`{je_idx, tag, type, name, id, label_text, placeholder, aria_label,
autocomplete, value, options, focused: bool, visible: bool}` — je_idx is
the ONLY element address ever used for actions.

## In-memory: import state (engine/profile_import.py)

`_state` (updates.py pattern): `{state: idle|extracting|ready|applied|
failed, stage: contact|skills|sections, chunk_done: int, chunk_total:
int, error: str|None, proposal: dict|None, started_at}`.

**Proposal** (also the review-screen contract):

```json
{
  "generated_at": "...", "resume_filename": "...", "tier": "local|cloud",
  "has_differences": true,
  "fields": [
    {"field": "first_name", "kind": "text", "current": "", "proposed": "Abhinav", "default": "apply"},
    {"field": "email", "kind": "text", "current": "a@x.com", "proposed": "b@y.com", "default": "keep"},
    {"field": "skills", "kind": "list", "current": ["..."], "proposed": ["..."], "default": "merge"},
    {"field": "target_titles", "kind": "list", "...": "..."},
    {"field": "target_locations", "kind": "list", "...": "..."},
    {"field": "resume_sections", "kind": "sections",
     "current_summary": {"experience": 3, "education": 1, "projects": 2},
     "proposed_summary": {"experience": 4, "education": 1, "projects": 2},
     "edited_at": "iso|null", "default": "keep"}
  ]
}
```

Identity fields: first_name, last_name, email, phone, linkedin_url,
portfolio_url. Visa/work-authorization NEVER appear. Every field listed
even when identical (`default: "none"`, rendered "no change");
`has_differences=false` → compact confirmation UI. Decisions payload:
`{field: "apply"|"keep"|"merge"}`.

## Settings (KV)

| Key | Default | Purpose |
|---|---|---|
| `PREFER_LOCAL_LLM` | `"1"` | offline model preferred for all AI features; cloud key = automatic fallback on local failure |

Removed-from-use: `PENDING_IDENTITY_CONFLICTS` (no longer written;
endpoint kept one release).

## Changed pydantic / engine surfaces

- `resume_extract`: `_split_chunks(text, target=5000) -> list[str]`,
  `_merge(parts: list[ResumeSections]) -> ResumeSections`, extract(...,
  on_progress=callable|None) — schema classes unchanged.
- `local_llm._load_model(path, n_ctx=8192)`.
- `apply_urls.resolve(job: Mapping) -> str` (pure).
- `adapters.classify(ats: str|None, descriptor: dict) -> str|None` (pure);
  `ats_from_url(url) -> str|None`.
- `ashby.py`: stored url = `applyUrl or jobUrl`.

## Bundled assets

`web/templates/practice_apply.html` + `practice_frame.html` — served at
`/practice/apply` and `/practice/frame` (Jinja, no data dependencies);
`tests/fixtures/ats_pages/*.html` — test-only, not shipped in installer.
