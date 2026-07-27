# Quickstart: The Fill Release (016) — manual verification

Run from the repo with the project venv (`.venv\Scripts\python.exe`).
Automated equivalents exist for every step (WS-E); this is the
human-checkable walkthrough, Windows-first.

## 0. Setup

1. `.venv\Scripts\python.exe desktop.py` (or `cli.py serve`).
2. Companion connected in Chrome (015 wizard: /companion → 3 green steps).
   Repeat key flows once in Edge.
3. Diagnostics → Companion & pairing: all OK; note "AI isolation: on
   (default)" and restart count 0.

## 1. Fill-first on the practice form (US1+US2 core)

1. Apply Assist → practice apply (companion mode).
2. EXPECT within ~2 s of the form appearing: name/email/phone/links
   filled. No approval prompt anywhere.
3. The work-authorization SELECT shows a real option (profile-consistent),
   the yes/no RADIO group has the correct member checked, the custom
   combobox holds a matched option, the maxlength field respects its cap.
4. The EEO-style fixture question is EMPTY with a "needs you" highlight.
5. On-page panel (bottom corner): "Connected · N filled · M need you",
   per-field list, Fill again, "you review and submit" note.
6. App → Apply Assist: passive activity log lists drafted/filled/needs-you
   items; NO blocking "Question needs your review" box exists.

## 2. Slow-draft responsiveness (US1 / RC1 regression)

1. Set `JOBS_AI_TEST_ECHO=1` with a `SLEEP:30` unknown question (fixture)
   or watch a real unknown free-text question draft.
2. While the draft runs: profile fields are ALREADY filled; app status
   stays fresh (< 5 s), popup shows connected; nothing is blocked.
3. When the draft lands: the answer appears in the field WITHOUT any
   click, with the `ai_draft` highlight; editing the field clears the
   highlight. The activity log shows drafting → filled.
4. Re-scan repeatedly: the question is NOT re-drafted (one draft/session).

## 3. Apply-opener + new-tab transfer (US3 / D1)

1. Queue the fixture posting whose form is hidden behind an Apply button:
   EXPECT exactly one automated Apply click, the revealed form fills,
   panel logs "opened the application form".
2. Queue the new-tab variant (opener opens the form in a child tab):
   EXPECT filling continues in the child tab.
3. Fixture's submit-click log records ZERO automated submit clicks (the
   E2E asserts this; eyeball the log once).
4. On a NON-recognized posting: no automated click; open the form
   yourself; filling proceeds.

## 4. Corrections + Fill again (US3)

1. Hand-edit a filled field to a custom value.
2. Panel → Fill again: EXPECT other retryable fields refill; your edited
   value is untouched; failed drafts get one immediate retry.

## 5. Busy + error surfacing (RC4)

1. While a queue runs, open the popup → Fill this page: EXPECT a visible
   "busy — stop the queue first" explanation (no silent no-op).
2. App → Re-scan during a companion fill: EXPECT `{"nudged": true}` and a
   fresh scan (watch the panel counters tick).
3. Diagnostics doctor shows `dropped_fields` / `scan_errors` counters.

## 6. Tailor + fault containment (US4 / RC5)

1. Job detail → "Tailor for this job": EXPECT an in-progress state with
   "can take a few minutes"; on success the page reloads with tailoring
   persisted (check reopening shows it); on induced failure a rendered
   error appears — the app NEVER closes.
2. Fault injection (dev): `JOBS_AI_TEST_ECHO=1`, kill the `je-ai-child`
   process mid-call: EXPECT the request fails cleanly, Diagnostics restart
   count increments, next AI call works.
3. `JOBS_AI_SUBPROCESS=0` env: thread mode restores (escape hatch).

## 7. Battery + frozen gates (ship ritual)

```powershell
.venv\Scripts\python.exe -m pytest -q          # x2, isolation default ON
.venv\Scripts\python.exe -m pytest -q -m browser
.venv\Scripts\python.exe -m pytest -q -m slow
# frozen build then:
python packaging\smoke_test.py                  # incl. tailor smoke + stamp gates
```

All green + both installers verified (magic bytes + SHA) before tagging
v1.6.0.
