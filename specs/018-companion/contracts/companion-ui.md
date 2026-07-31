# Contract: The companion widget (feature 018)

The single on-page surface. One host element, one shadow root, top frame only.

---

## 1. Mounting

| property | value | requirement |
|----------|-------|-------------|
| host id | `je-companion-host` | exactly one per document (FR-004) |
| shadow root | `open` | so tests can drive controls; CSS isolation is unaffected |
| frame | `window === window.top` only | sub-frames fill but never mount UI |
| parent | `document.body`, falling back to `document.documentElement` | must not throw before `<body>` exists (FR-006) |

### Required inline host style

Applied in this order. `all:initial` **first**, positioning `!important`.

```js
host.style.cssText = "all:initial";
host.style.setProperty("position", "fixed", "important");
host.style.setProperty("inset", "auto 16px 16px auto", "important");
host.style.setProperty("z-index", "2147483647", "important");
host.style.setProperty("display", "block", "important");
```

**Invariant (FR-001/FR-002):** `getComputedStyle(host).position === "fixed"`
and the host's bounding rect intersects the viewport — on a 5000 px document
whose stylesheet declares `div { position: static !important }`.

---

## 2. States

`detection` ∈ `none` | `form` | `posting` | `posting+form`
`session` ∈ `idle` | `starting` | `filling` | `stopped` | `done`

The widget renders only when `detection != "none"` **or** `session != "idle"`.

### Primary action (exactly one, FR-007)

| session | detection | label | id | sends |
|---------|-----------|-------|----|-------|
| `idle` | `posting`, `posting+form` | `Apply with Apply Assist` | `primary` | `apply_here` |
| `idle` | `form` | `Fill this page` | `primary` | `fill_here` |
| `starting` | any | `Starting…` (disabled) | `primary` | — |
| `filling` | any | `Stop` | `primary` | `session_control{stop}` |
| `stopped`, `done` | any | `Fill again` | `primary` | `fill_again` |

**Every click reports an outcome (FR-010).** On refusal or failure the notice
line shows the reason; the button re-enables. A control must never appear to
have done nothing.

---

## 3. Structure (expanded)

```
┌────────────────────────────────┐
│ ● Job Engine            ▁   ✕  │  header: state dot, collapse, dismiss
├────────────────────────────────┤
│  ⟨78⟩ strong match             │  score block — only when scored
│       H-1B sponsor: A          │
│  Akuna Capital                 │
│  Quant Developer               │
├────────────────────────────────┤
│  ▸ Apply with Apply Assist     │  the one primary action
│  ▸ Save to Job Engine          │  secondary — only on a posting
├────────────────────────────────┤
│  Filled 14 · Needs you 3 · 22  │  progress — only while/after filling
│  <notice, when present>        │
├────────────────────────────────┤
│  ⚠ Needs you (3)          ▼    │  expanded by default
│  ✎ AI drafts — review (2)  ▶   │  collapsed
│  ✓ From your profile (14)  ▶   │  collapsed
├────────────────────────────────┤
│  You click apply / submit —    │  never removed, never reworded
│  never us.                     │
└────────────────────────────────┘
```

### Answer row

```
question text
answer text                       (purple when group == "draft")
[Copy] [Insert] [Show me]         Insert/Show me only when je_idx is present
── needs-you only ──
why this needs you (plain language)
[ input                    ] ⏎    Enter saves
```

### Collapsed pill (FR-012)

| condition | content |
|-----------|---------|
| `needs_you > 0` | ⚠ + count |
| `session == "filling"` | `filled`/`seen` |
| `score` present | score + band colour |
| otherwise | wordmark |

---

## 4. Behaviour

| id | control | effect | never |
|----|---------|--------|-------|
| `primary` | primary action | per the table above | clicks a page control |
| `save` | Save to Job Engine | `save_job` | — |
| `collapse` | ▁ / ▲ | toggles card ↔ pill; persists for the tab | — |
| `dismiss` | ✕ | hides for this href; a session start re-shows it | — |
| `copy` | Copy | clipboard only | touches the page |
| `insert` | Insert | fills **exactly one** field, by `je_idx` | touches any other element |
| `jump` | Show me | `scrollIntoView` on that field | changes any value |
| `ask` | needs-you input | `answer_question` | rewrites what was typed |

### Auto-expand (FR-013)

Expands on transition to `session == "filling"`, and on the first time
`needs_you` goes from 0 to non-zero. Never re-expands after the applicant
collapses it for the same condition.

### Re-render (FR-026)

- Rows are matched by `key` and patched in place.
- A row containing `root.activeElement` is **not** touched. (`activeElement` on
  the shadow root — `document.activeElement` returns the host when focus is
  inside an open shadow root.)
- Only new keys create nodes; only vanished keys remove them.

### Accessibility (FR-018)

Keyboard-reachable controls with a visible focus ring; group headers are
`aria-expanded` toggles; the notice line is `role="status"`;
`prefers-reduced-motion` disables the expand/collapse transition.

---

## 5. Safety invariants (unchanged from 012/016/017)

- The companion **never** clicks, types into, submits, or mutates any page
  element, with the single exception of `Insert` placing a value into the one
  field the applicant chose.
- No `.click()` on any page element from the widget module.
- Answer and question text is inserted with `textContent`, never `innerHTML`.
- All styles are inline in the shadow root; no external requests, no
  `web_accessible_resources`, no fonts.
- The pairing secret is never rendered, logged, or received.
> **Superseded in part by 019** (constitution v1.2.0): the companion now
> presses Apply, Sign in, and a completed step's Continue. The footer line
> below became "You press the final Submit — never us." The *guarantee* it
> encodes — a permanent, unremovable statement of what the human always
> does — is unchanged. See `specs/019-door-to-door/contracts/escort-ui.md`.

- "You click apply / submit — never us." is always present when the widget is
  expanded.

---

## 6. Light-DOM mirror (FR-017)

On the host, for observability without piercing the shadow root:

`data-je-score`, `data-je-band`, `data-je-company`, `data-je-sponsor`,
`data-je-saved`, `data-je-collapsed`, `data-je-seen`, `data-je-filled`,
`data-je-needs-you`, `data-je-answers`, `data-je-session`,
`data-je-detection`.

Every attribute asserted by the 012/016/017 suites is carried forward
unchanged on the merged host.

---

## 7. `window.jeOverlay` facade

Preserved so `main.js` and existing tests are unaffected:
`show`, `hide`, `update`, `note`, `setAnswers`, `onAnswer`, `onInsert`,
`onJump`, `onFillAgain`. Each delegates to the panel. New surface
(`setPosting`, `setScore`, `setSession`, `notice`) is added on
`window.jePanel`.
