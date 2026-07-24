# Feature 013 "The Refinements Release" (v1.3.0): fill in the right browser, faster AI, and UI polish

## Context

Real-use feedback after v1.2.0 surfaced one blocking bug and several rough edges.
The blocker: **Apply Assist opened jobs in Edge even though the user's default
browser is Chrome and their companion extension + logins live in Chrome** — so
the fill happened in a browser where they weren't signed in and the companion
wasn't watching, making applications impossible to complete. Alongside that: the
local AI never uses an available **GPU** (and resume extraction is slow), the
feed shows machine dates (`2026-07-24`) instead of human ones, sort affordances
are nearly invisible, the **job detail page has no back button**, and the app
**ships with no icon**. This release fixes the browser routing and does a
focused polish + performance pass.

### User-locked decisions (AskUserQuestion, 2026-07-24)

- **Browser:** Apply Assist should prefer the **OS default browser** (detected;
  Chrome for this user), and strongly prefer the **connected companion** — never
  silently fall back to Edge when the companion is in Chrome.
- **GPU/speed:** **Auto GPU offload + CPU-thread tuning, no installer bloat** —
  use the GPU when the installed AI runtime supports it, tune threads to the
  user's cores, speed up resume extraction; installer stays the CPU build, with
  an opt-in CUDA runtime documented for NVIDIA users.
- **Icon:** I design a **simple branded icon** and wire it everywhere.
- Still $0, offline-first, engine never imports web, fills never auto-submit.

## Architecture (5 workstreams)

### WS-A — Fill in the *right* browser (the blocking bug)

- **`engine/autofill/default_browser.py` (NEW):** `default_channel_order() ->
  tuple[str,...]` — detect the OS default browser and return Playwright channels
  ordered default-first. Windows: read `HKCU\Software\Microsoft\Windows\
  Shell\Associations\UrlAssociations\https\UserChoice\ProgId` (`ChromeHTML`→
  chrome, `MSEdgeHTM`→msedge, `BraveHTML`→chrome, else fall through); macOS/Linux:
  best-effort, default `("chrome","msedge")`. Pure, unit-tested with the registry/
  env read injected so it's testable without a real registry.
- **`engine/autofill/browser_controller.py`:** replace the hardcoded
  `_CHANNELS = ("msedge","chrome")` (line 42) with `default_channel_order()`
  (deduped, all known channels appended) used by `_ensure_context` (~L220) and
  `preflight` (~L248). Result: the assistant window opens the user's **default**
  browser first (Chrome), not Edge.
- **Prefer the companion harder** (`_choose_backend`, ~L116): the companion is
  the whole point of "fill in my own browser". Keep `AUTOFILL_BACKEND` override;
  when a companion has connected this session, prefer it and, if its heartbeat is
  merely stale (not gone), still route to it rather than launching a *different*
  browser. Surface the chosen browser/backend in the Apply Assist status so a
  mismatch ("companion is in Chrome; assistant opened Edge") is visible, not
  silent.
- **"Open posting" respects the default too:** on Windows use `os.startfile(url)`
  (shell default handler) instead of Python's `webbrowser.open` (which can
  resolve to Edge in a frozen app) — `web/routes_api.py:43` and `desktop.py:187`.
- Tests: ProgId→channel mapping; channel order is default-first; `_choose_backend`
  still prefers a live companion; open-posting uses the shell default on Windows.

### WS-B — Human dates + visible sort affordances

- **`humandate` Jinja filter** registered in `web/main.py` (alongside
  `templates.env.globals`, ~L26): `"2026-07-24" | humandate → "24 July 2026"`
  (`%d %B %Y`, day zero-stripped; tolerant of ISO datetimes and None). Apply it
  to the feed's Posted/`seen ~` cells (`partials/feed_table.html:44-45`), the
  job-detail posted line (`job_detail.html:9`), and other prominent date spots
  (tracker/analytics) where quick.
- **Sort arrows:** in `feed_table.html:23,25` the `▾` shows only on the *active*
  column. Make sortability discoverable: render a faint indicator on **both**
  Posted and Match always (inactive `⇅`, active `▾`), styled via a `.sort` class
  in the existing token CSS. Headers already link via `replace_query(sort=…)` —
  keep that.
- Tests: a `humandate` unit/render test (incl. None + datetime input); a feed
  render assertion that both sortable headers carry the indicator + sort link.

### WS-C — Back button on the job detail page

- **`web/templates/job_detail.html`** header (~L4-11): add a `← Back` control that
  returns to the previous view when there is history, else falls back to the feed:
  `<a class="back" href="/" onclick="if(document.referrer&&history.length>1)
  {history.back();return false;}">← Back</a>`. Small `.back` style. Preserves the
  user's feed filters/scroll when they came from the feed.
- Verified by opening a job and clicking Back (smoke); no logic test needed.

### WS-D — App icon (window, taskbar, installer, favicon)

- **Create the art:** a clean "Job Engine" mark (target/scope ring over a check —
  matches the datasheet/scope-screen theme). Generate `packaging/icon.ico`
  (16/32/48/256 multi-size) and `packaging/icon.icns` (macOS) from one source PNG,
  plus a `web/static/favicon.ico` (+ `<link rel="icon">` in `base.html`).
- **Wire it in:** PyInstaller spec (`icon=packaging/icon.ico` for the exe →
  this also gives the pywebview window + taskbar its icon on Windows; `icon=
  icon.icns` for the mac app); `packaging/windows.iss` add `SetupIconFile=
  ..\packaging\icon.ico`, `UninstallDisplayIcon={app}\{#MyAppExeName}`, and
  `IconFilename` on the `[Icons]` shortcuts; macOS `.app`/dmg icon from the icns.
- Tests: an asset test asserting the icon files exist and are referenced by
  `windows.iss` and the spec; `smoke_test.py` already verifies the frozen shell —
  extend it to assert the shipped exe has a non-empty icon resource if cheap.

### WS-E — GPU offload + CPU tuning + faster resume extraction

- **`engine/local_llm.py::_load_model` (L35-41):** pass `n_gpu_layers` and
  `n_threads` to `Llama(...)`:
  - `n_gpu_layers`: env `JOBS_GPU_LAYERS` (int) if set; else **auto** — attempt
    full offload (`-1`) and, on load/inference failure, **retry once with 0**
    (CPU) so a CPU-only bundled wheel degrades gracefully with no user action.
  - `n_threads`: `JOBS_LLM_THREADS` if set, else `os.cpu_count()`.
  Cache the working config so the fallback happens once.
- **`engine/semantic.py` (Llama load, ~L46):** same `n_gpu_layers`/`n_threads`
  treatment for the embeddings model.
- **Resume extraction speed (`engine/resume_extract.py`):** the latency is the
  local-model call, so WS-E's threads/GPU directly help; additionally skip
  re-extraction when the resume text is unchanged (hash guard in
  `engine/profile_import.py`) and keep the single-shot path when the text fits
  (already the case) so most resumes are one inference, not many.
- **Docs (Settings + USER_MANUAL):** the installer ships the **CPU** AI build; to
  use an **NVIDIA GPU**, install a CUDA `llama-cpp-python` wheel (one pip command)
  — then GPU auto-offload kicks in. Threads help everyone with no setup.
- Tests: `_load_model`/semantic pass env-driven `n_gpu_layers`/`n_threads`
  (monkeypatch `Llama` to capture kwargs); the GPU→CPU graceful retry (first
  construct raises → second call uses 0); extraction hash-skip.

## Constitution guardrails (enforced by test)

$0 (GPU is optional, no paid dep) · offline-first preserved (CPU path unchanged
and always works) · engine never imports web (`default_browser`, `local_llm`,
`semantic` stay pure) · no installer bloat (CPU wheel unchanged) · Apply Assist
still never auto-submits and still fills only in the user's own/default browser.

## Verification (must pass before shipping)

- Unit: default-browser mapping + channel order; `humandate`; `_load_model`
  gpu/threads kwargs + graceful CPU fallback; extraction hash-skip.
- Run the app: open a job → **Back** returns to the feed; feed shows **"24 July
  2026"** + visible sort arrows on Posted & Match; **Open posting** and Apply
  Assist use the **default browser (Chrome)** / the connected companion (not
  Edge); the window/taskbar/installer show the **icon**.
- Perf: with `JOBS_LLM_THREADS` set, resume extraction is faster; with a CUDA
  wheel installed, `n_gpu_layers=-1` is exercised (and falls back cleanly on the
  CPU wheel).
- Full `pytest -q` ×2 + `-m browser` + `-m slow` green; frozen build +
  `packaging/smoke_test.py` PASS (icon + discovery assets); manual live gate:
  a real application fills in Chrome via the companion.
- Ship: version **1.3.0**, What's New entry, merge → mirror `main:001-ai-job-engine`
  → tag `v1.3.0` → verify BOTH installers (exe `MZ`/dmg `78 01`) + SHA-256.

## Process

New branch `013-refinements` → design doc → full speckit chain (specify →
clarify → plan → checklist → tasks → analyze, fix all findings BEFORE
implementation) → hybrid `/speckit-implement` + superpowers TDD → docs → frozen
smoke → live gate → ship v1.3.0. (Same pipeline as 010/011/012; ask before
implementation.)

## Non-goals

Shipping a separate CUDA/NVIDIA installer (opt-in wheel + docs instead) ·
multi-browser simultaneous fills · a full icon/brand redesign beyond the app mark ·
reworking the feed's sort backend (the `sort=date|score` query already exists) ·
per-column ascending/descending toggle (single-direction sort as today).
