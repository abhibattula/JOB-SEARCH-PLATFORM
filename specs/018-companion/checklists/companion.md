# Companion Quality Checklist: 018

**Purpose**: Gate the on-page widget before v1.8.0 is tagged
**Created**: 2026-07-29
**Feature**: [spec.md](../spec.md) · [contracts/companion-ui.md](../contracts/companion-ui.md)

## Visibility (the R1 class)

- [ ] `getComputedStyle(host).position === "fixed"` on a plain page
- [ ] Still `fixed` on a page declaring `div { position: static !important }`
- [ ] Host rect intersects the viewport on a 5000 px-tall document, unscrolled
- [ ] Still visible after scrolling to the bottom of that document
- [ ] `all:initial` appears **before** any positioning declaration in the source
- [ ] Renders when `document.body` does not yet exist
- [ ] Exactly one companion host per document
- [ ] No companion host inside a cross-origin sub-frame

## Controls actually work (the R2 class)

- [ ] Primary action on a posting → app receives `apply_here` → session starts
- [ ] Primary action on a form-only page → app receives `fill_here`
- [ ] Primary action while filling → app stops the queue
- [ ] Primary action after a pass → re-runs the fill
- [ ] Save → job persisted, button reflects saved state
- [ ] Collapse / expand / dismiss each do what they say
- [ ] Copy puts the answer on the clipboard
- [ ] Insert fills exactly one field and changes nothing else
- [ ] Show me scrolls that field into view
- [ ] Needs-you input saves the answer and it fills on the next scan
- [ ] **Every one of the above is asserted by a click in a real browser**, not by
      a string appearing in a source file
- [ ] A refused action shows the reason; no control ever appears inert

## Answers (the R4/R5/R6 class)

- [ ] Every decided field appears in the feed — profile fills included
- [ ] Every item carries a `je_idx`, or renders Copy only
- [ ] Groups are needs-you (open) → drafts → profile (collapsed), each counted
- [ ] Typed text survives ≥3 scan cycles with focus intact
- [ ] A row containing the focused element is never rebuilt
- [ ] An unchanged scan pushes no answer payload
- [ ] Truncation is stated on-screen when it happens
- [ ] Answer text is inserted as text, never as markup
- [ ] No field decided as a secret ever appears in the feed

## Presentation

- [ ] Rests as a pill; expands on click; choice persists across SPA navigation
- [ ] Auto-expands on fill start and on the first needs-you
- [ ] Stays inside the viewport; scrolls internally on a short viewport
- [ ] Does not cover the field being filled
- [ ] Every control is keyboard-reachable with a visible focus ring
- [ ] `prefers-reduced-motion` disables the expand transition
- [ ] Contrast is legible against both light and dark job boards
- [ ] No external request: no font, no CDN, no `web_accessible_resources`

## Safety (unchanged invariants)

- [ ] The widget module contains no `.click(` on a page element
- [ ] No submit, login, next or apply control is ever clicked
- [ ] Zero submit clicks across every fixture in the browser suite
- [ ] The read-only probe stamps nothing — no `data-je-idx`, no `data-je-doc`
- [ ] "You click apply / submit — never us." is present whenever expanded
- [ ] The pairing secret appears in no message, log, report or diagnostic
- [ ] `PROTOCOL_V` is still `1`; old payloads still validate

## Release

- [ ] Full battery passes twice
- [ ] `-m browser` passes
- [ ] Offline-model gates pass
- [ ] Frozen smoke passes with `JOBS_AI_SUBPROCESS` default on
- [ ] Version is consistent everywhere `check_version.py` looks, `windows.iss` included
- [ ] USER_MANUAL, README and `WHATS_NEW["1.8.0"]` updated
- [ ] Both installers verified: magic bytes + SHA-256 against the release body
