# Phase 0 Research: The Refinements Release

Design decisions, each grounded in code read during planning.

## D1. Detecting the OS default browser → Playwright channel order

- **Decision**: `engine/autofill/default_browser.py::default_channel_order() ->
  tuple[str,...]`. Windows: read `HKCU\Software\Microsoft\Windows\Shell\
  Associations\UrlAssociations\https\UserChoice` value `ProgId` and map:
  `ChromeHTML`/`BraveHTML`/`ChromiumHPKF...`→`chrome`, `MSEdgeHTM`→`msedge`
  (Firefox/Opera/etc. → no chromium channel, fall through). macOS/Linux:
  best-effort (`LSCopyDefaultHandlerForURLScheme` / `xdg-settings`), default
  `("chrome","msedge")`. Return the detected channel first, then the remaining
  known automatable channels (`chrome`, `msedge`) deduped, so `_ensure_context`
  always has a fallback. The registry/OS read is injected (a `_read_progid`
  seam) so tests don't need a real registry.
- **Rationale**: directly fixes the bug — the assistant window opens the user's
  actual default browser (Chrome) instead of Edge-first. Matches the user's
  locked choice ("use the default").
- **Alternatives rejected**: hardcode Chrome-first (wrong when Edge is the real
  default); a Settings dropdown to pick the browser (more UI; the OS already
  knows the answer — can add later if needed).

## D2. Prefer the connected companion harder

- **Decision**: keep `AUTOFILL_BACKEND` override and `ext_backend.is_live()`
  selection, but when the companion has connected this session, prefer it even if
  the heartbeat is briefly stale (widen the acceptable age at queue start), rather
  than launching a *different* browser mid-flow. Surface the chosen
  backend+browser in the Apply Assist status so a mismatch is visible (FR-004).
- **Rationale**: the companion IS "fill in my own browser"; a transient heartbeat
  gap shouldn't bounce the user into an Edge Playwright window where they aren't
  signed in.
- **Alternatives rejected**: always use the companion if it ever connected (too
  aggressive if it truly died); never fall back (breaks the no-companion path).

## D3. GPU offload + CPU threads (offline model)

- **Decision**: `local_llm._load_model` passes `n_gpu_layers` and `n_threads` to
  `Llama(...)`. `n_gpu_layers`: env `JOBS_GPU_LAYERS` if set, else auto = attempt
  `-1` (offload all) and, on load/first-inference failure, **retry once with 0**
  (CPU); cache the working value so the fallback happens once. `n_threads`: env
  `JOBS_LLM_THREADS` else `os.cpu_count()`. Same treatment on `semantic.py`'s
  embeddings `Llama`.
- **Rationale**: the bundled wheel is CPU-only, so GPU offload is a no-op there
  and must fail gracefully; a CUDA/Metal wheel (opt-in) unlocks GPU with zero
  code change. Thread tuning helps *everyone* (llama.cpp otherwise under-uses
  cores). Matches the locked "auto GPU + CPU tuning, no bloat" choice.
- **Alternatives rejected**: shipping a CUDA build in the installer (bloat,
  NVIDIA-only — a non-goal); a hard GPU requirement (breaks offline-first).

## D4. Faster resume extraction

- **Decision**: latency is the local-model call, so D3's threads/GPU do most of
  the work. Additionally, `profile_import` skips extraction when the resume text
  hash is unchanged from the last successful import (avoids re-running the model
  on re-open). The single-shot path already applies when the resume fits the
  context (`resume_extract.extract`), so most resumes are one inference.
- **Rationale**: cheap, safe wins on top of the inference speedup; no behavior
  change for a genuinely new resume.
- **Alternatives rejected**: shrinking the model/quant (quality risk); dropping
  chunking for long resumes (context overflow — the 009 bug this replaced).

## D5. Human dates (presentation only)

- **Decision**: a `humandate` Jinja filter registered in `web/main.py`
  (`templates.env.filters["humandate"]`): parse an ISO date/datetime string →
  `"%d %B %Y"` with the leading zero stripped → **"24 July 2026"** (clarified
  title-case). Tolerant of `None`/empty/already-formatted input (returns it
  unchanged rather than raising). Applied only to the **feed** (`feed_table.html`
  Posted + `seen ~` first_seen) and **job detail** (`job_detail.html`) per the
  clarified scope; the "approximate" marker for source-less dates is preserved.
- **Rationale**: presentation-only, no stored-data change; one reusable filter.
- **Alternatives rejected**: uppercase/abbreviated month (user picked title-case);
  reformatting in Python at query time (couples data to presentation).

## D6. Persistent sort arrows

- **Decision**: `feed_table.html` already links the Posted/Match headers via
  `replace_query(sort=…)` and shows `▾` only when active. Add a persistent
  indicator: inactive shows a faint `⇅`, active shows `▾`, styled by a `.sort`
  class in the existing token CSS. Single-direction (newest/highest first) as
  today — per the non-goal, no asc/desc toggle.
- **Rationale**: makes sortability discoverable without a new sort backend.
- **Alternatives rejected**: full asc/desc toggle (non-goal); JS-driven client
  sort (the server sort already exists).

## D7. Back button

- **Decision**: `job_detail.html` header gets `← Back` — `history.back()` when
  there is prior history (preserves feed filters/scroll), else `href="/"`.
- **Alternatives rejected**: always link to `/` (loses the user's feed state).

## D8. App icon (one source → every surface)

- **Decision**: `packaging/make_icon.py` (Pillow, already installed) renders one
  source mark into `packaging/icon.ico` (16/32/48/64/128/256), `icon.icns`
  (macOS), and `web/static/favicon.ico`; the assets are committed so builds don't
  depend on regeneration. Wire: `jobengine.spec` EXE `icon=icon.ico` (→ Windows
  window/taskbar icon comes from the exe), BUNDLE `icon=icon.icns`; `windows.iss`
  `SetupIconFile` + `UninstallDisplayIcon` + `[Icons] IconFilename`; `base.html`
  `<link rel="icon">`. pywebview needs no icon arg (inherits the exe icon on
  Windows). Also fix the stale `CFBundleShortVersionString` to `APP_VERSION`.
- **Design**: a simple "scope-ring + check" mark in the app's accent color —
  matches the datasheet/scope-screen themes; not a full brand system (non-goal).
- **Alternatives rejected**: hand-authoring platform icons by hand (error-prone);
  runtime icon generation at startup (build-time asset is simpler and reproducible).

## Testing strategy (Principle V)

Unit: `default_channel_order` mapping + order + fallbacks (ProgId injected);
`humandate` (valid/None/datetime); `local_llm`/`semantic` load kwargs from env +
GPU→CPU graceful retry; `profile_import` hash-skip. Wiring: `browser_controller`
uses the default order and still prefers a live companion; open-posting uses the
OS default handler. Assets: icon files exist and are referenced by `windows.iss`
and the spec; `smoke_test.py` asserts they ship. Manual: real fill in Chrome via
the companion; feed shows human dates + arrows; Back works; icon on all surfaces.
