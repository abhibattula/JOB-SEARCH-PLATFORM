# Phase 1 Data Model: The Refinements Release

**No database schema change** and no migration. This release adds transient,
computed configuration only. Stored dates are unchanged (presentation-only).

## Computed / config entities (not persisted)

### BrowserChannelOrder
The ordered list of Playwright channels Apply Assist's assistant window will try,
derived from the OS default browser at launch.

| Field | Type | Notes |
|-------|------|-------|
| order | tuple[str,...] | e.g. `("chrome","msedge")` when Chrome is default; default-first, remaining automatable channels appended, deduped |
| source | str | how it was derived (registry ProgId / fallback) — for logging/status only |

Produced by `engine/autofill/default_browser.default_channel_order()`; consumed by
`browser_controller._ensure_context` / `preflight`. Not stored.

### AIRuntimeConfig
How the offline model is loaded.

| Field | Type | Source |
|-------|------|--------|
| n_gpu_layers | int | env `JOBS_GPU_LAYERS`, else auto (-1 → 0 on failure) |
| n_threads | int | env `JOBS_LLM_THREADS`, else `os.cpu_count()` |

Applied in `local_llm._load_model` and `semantic`. Not stored; the working value
is memoized in-process after the first successful load.

### ResumeExtractionGuard
A hash of the last successfully-extracted resume text, held on the profile-import
state so an unchanged re-import skips the model call.

| Field | Type | Notes |
|-------|------|-------|
| last_resume_hash | str \| None | sha of the resume text; unchanged → skip extraction |

Lives with the existing `engine/profile_import` module state (session-scoped, like
its other state) — no DB column.

### AppIcon asset
The single branded mark rendered to the formats each surface needs.

| Surface | Format | Path |
|---------|--------|------|
| Windows exe / window / taskbar | .ico | `packaging/icon.ico` (via spec `icon=`) |
| macOS app | .icns | `packaging/icon.icns` (via BUNDLE `icon=`) |
| Installer + shortcuts | .ico | `packaging/icon.ico` (windows.iss) |
| Browser tab | .ico | `web/static/favicon.ico` (`<link rel="icon">`) |

Committed build assets, generated once by `packaging/make_icon.py`.

## Presentation change (no data change)

- Dates in the feed and job detail render via the `humandate` filter as
  "24 July 2026". The underlying stored `posted_date`/`first_seen` strings and the
  `posted_approx` flag are unchanged; the "seen ~ …" approximate marker stays.
