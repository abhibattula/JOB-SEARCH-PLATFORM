# Quickstart: The Discovery Copilot (feature 012, v1.2.0)

## Prerequisites

- The Job Engine app running locally (`run.bat` / `uvicorn`), with a resume/
  profile saved so a real match can be computed.
- The browser companion installed (unpacked) and **connected** (green dot) — same
  setup as Apply Assist. After pulling this feature, **reload the unpacked
  extension** (`chrome://extensions` ↻) so the new `discovery.js` and manifest
  load — browsers cache the old background/content scripts until reload.

## Try it (scripted / dev)

1. Start the app; open the practice page or any bundled discovery fixture served
   at a local URL.
2. `pytest -m browser tests/integration/test_discovery_badge.py` runs the real
   Edge/Chrome, loads the extension, opens the JSON-LD / LinkedIn / Indeed
   fixtures, and asserts the badge renders with a numeric score and the right
   company, and that clicking Save persists the job (`source="manual"`, status
   `saved`) and dedups on repeat.

## Try it (manual live gate)

1. With the app running + companion connected, browse to:
   - a **Greenhouse/Lever/Ashby** posting (JSON-LD path), and
   - a **LinkedIn** `…/jobs/view/…` posting, and
   - an **Indeed** job page.
2. On each, a small badge appears bottom-right within ~2s showing your **match
   score**, an **H-1B sponsorship** pill for the company, and a **Save to Job
   Engine** button.
3. Click **Save** → the badge confirms "Saved ✓". Open the app → the job is in
   the feed and the **Saved** view with the correct title/company/link.
4. Reopen the same posting → the badge shows **Already saved** (no duplicate).
5. Confirm the badge can be **collapsed** and **dismissed**, never covers page
   controls, and that the companion took **no action** on the page itself.
6. Confirm **coexistence**: start an Apply Assist fill on an application page —
   fills work exactly as before while the discovery badge is present elsewhere.

## Expected results

- No badge on non-job pages, on search-result lists, or when the app is closed /
  companion disconnected.
- Companies without sufficient H-1B evidence show **"H-1B: unknown"**, never a
  fabricated grade.
- No resume saved → the badge shows an **"add your resume"** prompt instead of a
  misleading score.

## Verification battery (before ship)

- `pytest -q` ×2 (full engine + extension asset suites) green.
- `pytest -q -m browser` green (discovery badge + all existing 010/011 browser
  tests — no interference).
- `pytest -q -m slow` offline gates green.
- Frozen build + `packaging/smoke_test.py` PASS (asserts `discovery.js` bundled +
  version 1.2.0).
- Manual live gate above on real LinkedIn/Indeed/Greenhouse postings.
