# Quickstart: The Refinements Release (feature 013, v1.3.0)

## Prerequisites

- App running locally; companion installed. After pulling this feature, **reload
  the unpacked companion** (`chrome://extensions` ↻) — no companion code changed,
  but reloading is harmless and keeps habits consistent.

## Verify each fix

### 1. Fill in the right browser (P1 — the bug)
- Make Chrome your Windows default; connect the companion in Chrome.
- Run Apply Assist on a saved job → it opens/fills **in Chrome** (companion),
  and the status shows the active backend/browser.
- Disconnect the companion, run again → the assistant window opens in your
  **default browser (Chrome)**, not Edge. Click **Open posting** → opens in the
  default browser.

### 2. Human dates + sort arrows + Back (P2)
- Open the feed → dates read **"24 July 2026"**; a source-less date still shows
  "seen ~ …".
- Both **Posted** and **Match** headers show a clickable sort arrow (faint when
  inactive); click each → the list re-sorts and the active arrow updates.
- Open a job → click **← Back** → you're back on the feed as you left it. Open a
  job by direct URL → Back still lands on the feed.

### 3. Faster AI (P3)
- Import a resume → extraction is faster (CPU threads). Re-import the same file →
  it does **not** re-run extraction.
- Set `JOBS_GPU_LAYERS=-1` with a CUDA/Metal `llama-cpp-python` installed →
  the model offloads to GPU (faster). On the stock CPU wheel it falls back to CPU
  automatically (no error). `JOBS_LLM_THREADS` overrides the core count.

### 4. App icon (P3)
- Launch the app → window + taskbar show the icon.
- The browser tab shows the favicon.
- The installer file and its desktop/start-menu shortcuts show the icon.

## Verification battery (before ship)

- `pytest -q` ×2 (incl. new `test_default_browser`, `test_local_llm`, humandate,
  browser-controller order) green.
- `pytest -q -m browser` green (existing fills + discovery unaffected).
- `pytest -q -m slow` green.
- Frozen build + `packaging/smoke_test.py` PASS (icon assets shipped + version
  1.3.0).
- Manual live gate: a real application fills in Chrome via the companion.
