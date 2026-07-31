# Quickstart: Door to Door (019) — manual verification

Run after the full suites are green. §5 is the pre-tag gate (the 018 lesson:
real pages, real clicks, real effects).

## 1. Setup

1. Install the v1.9.0 build (or run from source: `python -m web.main`).
2. `chrome://extensions` → Job Engine Companion → **↻ Reload** (mandatory
   after every app upgrade).
3. App → Companion page: the tick must be GREEN with matching versions.
   - **Skew check**: temporarily load the v1.8.0 bundle instead → the page
     must go AMBER with reload instructions; popup and panel must show the
     same. Reload the 1.9.0 bundle; green returns.
4. Settings → Saved logins: confirm the new consent copy and the
   **Escort** toggle (default ON).

## 2. Fixture pass (fast, local)

`pytest -m browser tests/integration/test_escort.py` covers this, but to see
it live: open each fixture from `tests/fixtures/ats_pages/` and confirm —
- `login_wall.html`: widget appears in sign-in state (it must NOT be
  invisible); with no saved login it offers the inline save form.
- `wizard_multipage/step1.html`: one press escorts step1 → step2 → parks at
  `review.html` with the Submit button provably un-clicked.
- `captcha_frame.html`: "Your turn: solve the check" — zero interaction with
  the frame.
- `workday_prompt_options.html` / `placeholder_select.html` /
  `shadow_form.html` / `aria_labelledby.html` / `fixed_modal_form.html`:
  every field fills or shows a reason in the panel.

## 3. Real Workday (the priority path)

1. Pick a real `*.myworkdayjobs.com` posting (new-grad queue).
2. First visit — no saved login: panel shows "No saved login"; save one via
   the inline form (or create the account by hand once: the registration
   fill generates the password, saves it to Windows Credential Manager, and
   YOU press Create account, then handle the verification email).
3. From the posting press **Apply with Apply Assist**:
   - the SAME tab runs the session (no duplicate tab — watch the tab strip);
   - the login wall fills and Sign in is clicked for you, once;
   - each wizard step fills, then advances by itself; anything unanswered
     pauses with the panel expanded; answering resumes it;
   - the session parks at Workday's review page in a prominent
     "Review & submit — your turn" state.
4. **Verify the STOP**: the Submit control is untouched. Read the
   application. Press Submit yourself.
5. App → Apply Assist record: the click trail lists open-apply / sign-in /
   each advance with outcomes.

## 4. Real Greenhouse + LinkedIn control

1. Greenhouse: a `job-boards.greenhouse.io` posting whose Apply navigates —
   Apply is clicked for you, the application page fills, single-page form
   parks at ready-for-review (no advance needed).
2. LinkedIn Easy Apply posting: filling works, but ZERO clicks happen —
   no Apply, no Next, no sign-in. The panel behaves like fill-only v1.8.0.

## 5. Pre-tag gate (all must hold)

- [ ] Version-skew amber fires with a stale bundle; zero silent fill drops
      (doctor counter visible instead).
- [ ] Apply-here fills the pressed tab; tab count unchanged.
- [ ] A real Workday wall: saved-login sign-in with zero manual clicks.
- [ ] A real Workday wizard: escorted to review; Submit untouched; trail
      recorded; cap and pause states reachable (force with the looping
      fixture if the real posting is short).
- [ ] Greenhouse navigate-apply works end to end.
- [ ] LinkedIn: zero clicks.
- [ ] `pytest` full battery ×2 green; `pytest -m browser` green;
      `tests/test_secret_hygiene.py` green (no secret outside the vault).
- [ ] Frozen smoke green, including keyring backend pinning in the frozen
      app and the version-skew check.
- [ ] Escort toggle OFF ⇒ behavior is exactly v1.8.0 fill-only.

## 6. Ship

Version bump everywhere (engine/__init__.py, extension/manifest.json,
packaging/windows.iss — byte-safe edit) → tag v1.9.0 → GitHub Actions builds
both installers → verify magic bytes + SHA-256 against the release body →
update memory + docs indexes.
