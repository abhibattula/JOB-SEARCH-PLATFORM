# Implementation Plan: The Refinements Release

**Branch**: `013-refinements` | **Date**: 2026-07-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-refinements/spec.md`

## Summary

A fix + polish + performance pass after v1.2.0. The headline is a **blocking-bug
fix**: Apply Assist's assistant window is hardcoded to try Edge first
(`browser_controller._CHANNELS = ("msedge","chrome")`), so fills landed in Edge
even when the user's default browser and companion are in Chrome — make it prefer
the **OS default browser** and the **connected companion**. Plus: auto **GPU
offload + CPU-thread tuning** for the offline model (graceful CPU fallback, no
installer bloat) and faster resume extraction; **human dates** ("24 July 2026")
on the feed and job detail; **persistent sort arrows**; a **Back button** on job
detail; and a **branded app icon** on window/taskbar/installer/favicon.

## Technical Context

**Language/Version**: Python 3.11+ (engine/web); Jinja2 templates; no JS
framework. **Primary Dependencies**: existing — Playwright, llama-cpp-python,
Pillow 12.3 (present; generates the icon), PyInstaller + Inno Setup. No new
runtime deps. **Storage**: none changed (no schema migration). **Testing**:
pytest; default-browser detection and channel order unit-tested with the OS read
injected (no real registry). **Target Platform**: Windows/macOS desktop app +
companion. **Project Type**: desktop web-app (`engine/` + thin `web/`) +
`extension/`. **Performance Goals**: resume extraction ≥30% faster on CPU (thread
tuning, SC-003); GPU offload lowers inference latency where supported.
**Constraints**: $0, offline-first (CPU path always works), engine never imports
web, installer size unchanged, Apply Assist never auto-submits.

## Constitution Check

*GATE: evaluated against constitution v1.1.3. Re-checked after Phase 1.*

- **I. Speed-to-Value** — PASS. Unblocks completing applications (fills were going
  to the wrong browser) and makes the AI faster — both directly serve "get hired
  sooner". No deferred capability built.
- **II. Zero-Subscription Cost** — PASS. GPU is optional and free; no paid dep;
  installer keeps the CPU model (no bloat); Pillow already vendored.
- **III. no-bot-bypass / no auto-submit** — PASS. Browser automation still fills
  only in the user's own/default browser, never bypasses bot protection, never
  auto-submits; opening a posting uses the OS default handler.
- **IV. Reusable Core, Thin Web Layer** — PASS. New logic is pure engine
  (`default_browser`, `local_llm`, `semantic`); `web/` gains only a presentation
  date filter, template tweaks, and an OS-default open call. Engine never imports
  web.
- **V. Tested Core Logic** — PASS. Default-browser mapping, channel order,
  `humandate`, and the model gpu/threads config (incl. graceful CPU fallback) all
  get pytest coverage before wiring.

No violations → Complexity Tracking omitted.

## Project Structure

### Documentation (this feature)

```text
specs/013-refinements/
├── plan.md ├── research.md ├── data-model.md ├── quickstart.md
├── checklists/requirements.md └── tasks.md  (tasks.md via /speckit.tasks)
```
(No contracts/ — this release exposes no new external interface.)

### Source Code (repository root)

```text
engine/autofill/
├── default_browser.py        # NEW — default_channel_order(): OS default → Playwright channels
├── browser_controller.py     # EDIT — _CHANNELS → default_channel_order(); _choose_backend prefers companion harder; surface active browser
engine/
├── local_llm.py              # EDIT — _load_model passes n_gpu_layers (auto + graceful CPU fallback) + n_threads
├── semantic.py               # EDIT — same n_gpu_layers/n_threads on the embeddings Llama
└── profile_import.py         # EDIT — skip re-extraction when the resume text is unchanged (hash guard)

web/
├── main.py                   # EDIT — register `humandate` Jinja filter
├── routes_api.py             # EDIT — open posting via OS default handler (os.startfile on Windows)
└── templates/
    ├── partials/feed_table.html  # EDIT — | humandate on dates; persistent sort arrows
    ├── job_detail.html           # EDIT — | humandate; add Back control
    └── base.html                 # EDIT — <link rel="icon"> favicon
desktop.py                    # (window/taskbar icon comes from the frozen exe icon — no code change)

packaging/
├── make_icon.py              # NEW — generate icon.ico/.icns/favicon.ico from one source (Pillow)
├── icon.ico / icon.icns      # NEW committed assets
├── jobengine.spec            # EDIT — EXE icon=icon.ico, BUNDLE icon=icon.icns (+ CFBundleShortVersionString from APP_VERSION)
├── windows.iss               # EDIT — SetupIconFile, UninstallDisplayIcon, [Icons] IconFilename; version 1.3.0
└── smoke_test.py             # EDIT — assert icon assets shipped
web/static/favicon.ico        # NEW committed asset

tests/
├── test_default_browser.py   # NEW — ProgId→channel map, default-first order, unknown/missing fallback
├── test_browser_controller.py# EDIT — channel order uses default; _choose_backend still prefers a live companion
├── test_local_llm.py         # NEW — gpu/threads kwargs from env + graceful GPU→CPU fallback (semantic too)
├── test_api.py / test_web    # EDIT — humandate filter; open-posting uses the default handler
└── test_packaging assets     # EDIT — icon files exist + referenced by windows.iss/spec
```

**Structure Decision**: existing desktop-web layout. One new engine module
(`default_browser.py`) and one new packaging helper (`make_icon.py`); everything
else is an additive edit to the file that already owns the concern. No DB change,
no new dependency, no contracts/.

## Phasing (maps to user stories)

- **Foundational**: `default_browser.py` + `humandate` filter + `local_llm`/
  `semantic` gpu-threads config — pure, unit-tested first (TDD).
- **US1 (P1)**: wire `browser_controller` to the default order + companion
  preference + surface the active browser; open-posting via OS default.
- **US2 (P2)**: human dates + persistent sort arrows on feed/detail; Back button.
- **US3 (P3)**: gpu/threads in the load paths; resume-extraction hash-skip.
- **US4 (P3)**: generate + wire the icon everywhere; smoke asserts it ships.
- **Polish/Ship**: docs (Settings GPU note, USER_MANUAL/GUIDE, What's New 1.3.0),
  version bump, verification battery, frozen smoke, live gate, ship v1.3.0.

## Complexity Tracking

No constitution violations — intentionally empty.
