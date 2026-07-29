# Companion Quality Checklist: 018

**Purpose**: Gate the on-page widget before v1.8.0 is tagged
**Created**: 2026-07-29
**Feature**: [spec.md](../spec.md) · [contracts/companion-ui.md](../contracts/companion-ui.md)

## Visibility (the R1 class)

- [x] `getComputedStyle(host).position === "fixed"` on a plain page
- [x] Still `fixed` on a page declaring `div { position: static !important }`
- [x] Host rect intersects the viewport on a 5000 px-tall document, unscrolled
- [x] Still visible after scrolling to the bottom of that document
- [x] `all:initial` appears **before** any positioning declaration in the source
- [x] Renders when `document.body` does not yet exist
- [x] Exactly one companion host per document
- [x] No companion host inside a cross-origin sub-frame

## Controls actually work (the R2 class)

- [x] Primary action on a posting → app receives `apply_here` → session starts
- [x] Primary action on a form-only page → app receives `fill_here`
- [x] Primary action while filling → app stops the queue
- [x] Primary action after a pass → re-runs the fill
- [x] Save → job persisted, button reflects saved state
- [x] Collapse / expand / dismiss each do what they say
- [x] Copy puts the answer on the clipboard
- [x] Insert fills exactly one field and changes nothing else
- [x] Show me scrolls that field into view
- [x] Needs-you input saves the answer and it fills on the next scan
- [x] **Every one of the above is asserted by a click in a real browser**, not by
      a string appearing in a source file
- [x] A refused action shows the reason; no control ever appears inert

## Answers (the R4/R5/R6 class)

- [x] Every decided field appears in the feed — profile fills included
- [x] Every item carries a `je_idx`, or renders Copy only
- [x] Groups are needs-you (open) → drafts → profile (collapsed), each counted
- [x] Typed text survives ≥3 scan cycles with focus intact
- [x] A row containing the focused element is never rebuilt
- [x] An unchanged scan pushes no answer payload
- [x] Truncation is stated on-screen when it happens
- [x] Answer text is inserted as text, never as markup
- [x] No field decided as a secret ever appears in the feed

## Presentation

- [x] Rests as a pill; expands on click; choice persists across SPA navigation
- [x] Auto-expands on fill start and on the first needs-you
- [x] Stays inside the viewport; scrolls internally on a short viewport
- [x] Does not cover the field being filled
- [x] Every control is keyboard-reachable with a visible focus ring
- [x] `prefers-reduced-motion` disables the expand transition
- [x] Contrast is legible against both light and dark job boards
- [x] No external request: no font, no CDN, no `web_accessible_resources`

## Safety (unchanged invariants)

- [x] The widget module contains no `.click(` on a page element
- [x] No submit, login, next or apply control is ever clicked
- [x] Zero submit clicks across every fixture in the browser suite
- [x] The read-only probe stamps nothing — no `data-je-idx`, no `data-je-doc`
- [x] "You click apply / submit — never us." is present whenever expanded
- [x] The pairing secret appears in no message, log, report or diagnostic
- [x] `PROTOCOL_V` is still `1`; old payloads still validate

## Release

- [x] Full battery passes twice
- [x] `-m browser` passes
- [ ] Offline-model gates pass
- [ ] Frozen smoke passes with `JOBS_AI_SUBPROCESS` default on
- [x] Version is consistent everywhere `check_version.py` looks, `windows.iss` included
- [x] USER_MANUAL, README and `WHATS_NEW["1.8.0"]` updated
- [ ] Both installers verified: magic bytes + SHA-256 against the release body
