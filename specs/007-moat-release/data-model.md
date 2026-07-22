# Data Model: The Moat Release (007)

All schema changes use the established idioms: `_MIGRATIONS` guarded
ALTER TABLE additions in `engine/db.py`, JSON-in-TEXT columns registered
in `_PROFILE_JSON_FIELDS`, and `_PROFILE_COLUMNS` as the single source of
truth for profile writes.

## user_profile (extended)

| Column | Type | Notes |
|---|---|---|
| `resume_file_path` | TEXT | absolute path of the stored original upload under `data_dir()/resume/`; NULL until a resume is uploaded post-007 (legacy profiles have text only) |
| `resume_sections` | TEXT (JSON) | `ResumeSections` payload (below); register in `_PROFILE_JSON_FIELDS` + `_PROFILE_COLUMNS` |
| `sections_edited_at` | TEXT | UTC timestamp of last manual edit; NULL means "as extracted, never touched" — drives the keep-vs-re-extract prompt |

### ResumeSections JSON shape (pydantic-validated in `engine/resume_extract.py`)

```json
{
  "experience": [{"title": "", "organization": "", "start": "", "end": "", "bullets": [""]}],
  "education":  [{"degree": "", "institution": "", "start": "", "end": "", "details": ""}],
  "projects":   [{"name": "", "description": "", "bullets": [""]}],
  "skills":     [""]
}
```

Validation rules: every list defaults empty (partial extraction is valid);
entries with no non-empty field are dropped; extraction failure → None
(never a crash, FR-016/17 fallback).

## companies (extended)

| Column | Type | Notes |
|---|---|---|
| `h1b_denials` | INTEGER | summed denial counts from USCIS files (0 when absent) |
| `wage_level_median` | TEXT | "I"–"IV" or NULL |
| `wage_offered_median` | REAL | annualized median offered wage or NULL |
| `cap_exempt` | INTEGER | 0/1 heuristic flag |
| `sponsor_grade` | TEXT | "A"–"F" or NULL (NULL renders as existing UNKNOWN path); assigned only when approvals+denials ≥ 10 |

`sponsor_grade`, `cap_exempt`, and the wage medians are recomputed inside
`sponsorship.apply_to_companies()` (existing post-load join point).

## h1b_employers (extended)

| Column | Type | Notes |
|---|---|---|
| `denials` | INTEGER | per-employer summed denials |
| `wage_level_median` | TEXT | from DOL engineering-SOC rows |
| `wage_offered_median` | REAL | from DOL engineering-SOC rows |

## Tailored PDF cache (filesystem, not DB)

- Path: `paths.data_dir()/tailored/<job_id>.pdf` + sidecar
  `<job_id>.fingerprint` (SHA-256 over resume_sections JSON + tailor_json).
- Serve/attach only on fingerprint match; else re-render then serve.
- `data_dir()/resume/` and `data_dir()/tailored/` created on demand.

## settings table (existing KV — new keys)

| Key | Values | Notes |
|---|---|---|
| `THEME` | `light` / `dark` / unset | explicit user choice wins over OS preference |
| `ONBOARDING_DISMISSED` | `1` / unset | hides checklist after completion/dismissal |
| `AUTOFILL_USE_TAILORED_PDF` | `1` (default) / `0` | FR-002 toggle |

## In-memory only (browser_controller state — deliberately not persisted)

- **Queue session**: ordered job list, index, per-job state
  (pending/current/done/failed), `interrupted` flag for browser-closed
  recovery. Cleared on app restart (spec assumption).
- **Fill report**: per job, list of `{label, tag, value_preview, outcome}`;
  credential passwords recorded pre-masked ("•••") at write time — the
  secret never enters controller state.
- **Batch summary**: derived from per-job outcomes at queue end.

## Invariants

- Passwords: OS keychain only (unchanged); the fill report stores the mask,
  never the value.
- Refresh updates never touch `resume_*` columns, statuses, or grades'
  underlying user data (existing upsert protections unchanged).
- `sponsor_grade` NULL ⇔ insufficient evidence (floor of 10) ⇔ UI shows
  UNKNOWN — a grade is never fabricated (SC-003).
- Extraction never overwrites `resume_sections` when `sections_edited_at`
  is set, except via the explicit re-extract confirmation (FR-016).
