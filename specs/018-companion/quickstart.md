# Quickstart — 018 The Companion

How to see the feature work, and how to reproduce each defect it fixes.

---

## 1. Reproduce the defects on v1.7.0 (before)

With v1.7.0 installed and the companion loaded:

| # | Do this | v1.7.0 behaviour |
|---|---------|------------------|
| R1 | Open any long job posting | The card is **not** in the corner — scroll to the very bottom of the page to find it |
| R2 | Scroll to the badge, click **Apply with Apply Assist** | Nothing happens. No session starts, no error, no console message |
| R4 | Start a fill from the app, scroll to the panel | Answers show only **Copy** — no Insert, no Show me |
| R5 | Compare the panel's list against the form | Name, email, phone, location, work auth are filled on the page but **absent** from the panel |
| R6 | Type into a needs-you input, wait 2 s | The text disappears mid-typing |
| R7 | Open a Greenhouse `…/application` URL directly | **No widget at all** |

---

## 2. Run it (after)

```powershell
# from the repo root
python -m uvicorn web.main:app --port 8765
```

Load the companion once: `chrome://extensions` → Developer mode → **Load
unpacked** → select the `extension/` folder shown on the app's Companion page.
The app and the companion ship as one version and the gate is exact-match, so
after any app upgrade press ↻ on the Job Engine Companion card.

---

## 3. The five-minute walkthrough

1. **Open a job posting** (LinkedIn, Indeed, Greenhouse, Lever, Ashby).
   → A pill appears **in the corner of the viewport**, showing the match score.
2. **Click the pill.** → The card expands: score, sponsorship, company, title.
3. **Click "Apply with Apply Assist".** → The session starts *on this tab*. The
   card shows progress; it expands on its own when the first question needs you.
4. **Read the answers.** Needs-you is open first. Expand "AI drafts" to review
   what was written for you; expand "From your profile" to confirm the ordinary
   fields.
5. **Fix one.** Type into a needs-you input and press Enter. It fills that field
   on the next scan and is remembered for every future application. Keep typing
   through a scan cycle — nothing is lost.
6. **Use an answer.** Click **Insert** to place it in its field, or **Show me**
   to scroll there, or **Copy**.
7. **Stop whenever.** The primary button is **Stop** while filling. You never
   have to switch to the app.
8. **You submit.** The companion never clicks apply, submit, next, or login.

Open a bare `…/application` URL directly and the pill still appears, with
**"Fill this page"** as its action.

---

## 4. Verify the fixes

```powershell
# unit + contract (fast)
python -m pytest tests/test_page_answers.py tests/test_ext_protocol.py `
                 tests/test_ext_backend.py tests/test_extension_assets.py -q

# the real-browser proof — this is the suite that would have caught R1 and R2
python -m pytest tests/integration/test_companion_widget.py -m browser -q

# everything
python -m pytest -q
python -m pytest -m browser -q
```

### What the browser suite asserts

| Test | Catches |
|------|---------|
| computed `position == "fixed"` and rect on-screen, on a 5000 px page with `div{position:static!important}` | R1 |
| clicking the primary action makes the app start a session | R2 |
| the companion appears on a metadata-less application fixture | R7 |
| every listed answer carries a `je_idx`; Insert puts the value in that field | R4 |
| a profile-filled field appears in the feed | R5 |
| typed text and focus survive ≥3 scan cycles | R6 |
| exactly one companion host exists | FR-004 |
| **zero** submit clicks on any fixture | the standing safety invariant |

---

## 5. Manual end-to-end before release

1. Install v1.8.0, reload the companion at `chrome://extensions`.
2. Profile → **Reset learned answers** if any old fabrications remain.
3. Open a real Greenhouse posting → Apply with Apply Assist.
4. Confirm, without ever switching to the app: the pill is visible, the card
   expands, answers are grouped, Insert works, a typed answer saves, Stop stops.
5. Open the same job's `…/application` URL directly → the pill appears with
   "Fill this page".
6. Confirm nothing was submitted and the app's Apply Assist page shows the same
   session.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No pill anywhere | Companion not paired, or the app is not running | Toolbar popup names the reason and offers **Connect now** |
| Pill appears, primary action refuses | Another session is running | The card says so; Stop it, or finish it |
| Pill on a page with no application | Probe false positive | Dismiss (✕); report the URL so the heuristic can be tightened |
| Keyboard shortcut does nothing | Chrome dropped a conflicting suggested key | Set your own at `chrome://extensions/shortcuts` |
| Card shows "companion is older than the app" | Version gate | ↻ on the Job Engine Companion card |
