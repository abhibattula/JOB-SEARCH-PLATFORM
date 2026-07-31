# Contract: Escort UI (019) — widget, popup, app surfaces

Extends `specs/018-companion/contracts/companion-ui.md`. Where the two
conflict, THIS contract wins (the 018 footer line is superseded — noted
there, not rewritten).

## Panel (companion widget) states

| Session state | Pill shows | Card shows | Primary action |
|---|---|---|---|
| `needs_login` (vault entry exists) | 🔑 | "Signing you in with your saved login…" | (none — automatic) |
| `needs_login` (no vault entry) | 🔑! | "No saved login for <domain>" + inline save form (identifier + password + Save) + "or open Settings" | Save login |
| `escorting` | filled/seen counts | progress + answer groups (018 layout unchanged) | Pause escort |
| `your_turn_captcha` | ⚠ | "Your turn: solve the check on the page. I'll continue after." | (none) |
| `ready_for_review` | ✓ | "Review & submit — your turn. Everything I could fill is in; the Submit stays yours." | (none — prominent state styling) |
| `paused_cap` | ⚠ | "I've advanced 12 pages — please look before we go further." | Continue escort |

Rules:
- The inline save form's password input is `type=password`; its value is
  sent ONLY in `credential_save` and cleared from the DOM immediately after
  send; it never enters the answers feed, `data-*` mirrors, or storage.
- Version mismatch renders a persistent notice pinned above all states:
  "App and companion versions differ — reload the companion at
  chrome://extensions (↻)."
- The footer line (all states) becomes:
  **"You press the final Submit — never us."**
  (`tests/test_extension_assets.py` footer pin updated in the same commit.)
- `Pause escort` flips only automated progression; filling continues.

## Popup

- Shows mismatch state with the same reload instruction when
  `chrome.storage.session` carries `mismatch: true`.
- Otherwise unchanged from 018.

## App surfaces

- `companion.html` connect wizard: amber state on version mismatch (server
  compares the `hello` version) — tick stays green ONLY on exact match.
- `settings.html` saved-logins section gains: "Apply Assist uses these to
  sign you in automatically during a session. It never clicks Create
  account, and never presses Submit. Turn the escort off below to make all
  clicks manual." plus the `escort_enabled` toggle.
- Apply Assist record: renders the Progression Click Record trail (kind,
  control description, outcome, time) per job.

## Never-rendered list (unchanged + extended)

Secrets (password values) never render anywhere — including previews,
tooltips, aria labels, and the activity trail (`target` carries the
control's name, e.g. "Sign In button", never field values).

## Click-safety copy (final-class)

Wherever the UI names what is never clicked, the canonical list is:
"Submit application · Review and submit · Submit · Create account ·
Register / Sign up · Pay / Checkout · any CAPTCHA — and nothing at all on
LinkedIn."
