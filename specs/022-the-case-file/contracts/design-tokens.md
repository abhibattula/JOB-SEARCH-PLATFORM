# Contract — Design tokens

**Consumers**: `web/static/styles.css`, every template, `extension/content/panel.js`.
**Enforced by**: `tests/test_design_system.py`.

## The contract

1. **Single source.** Every colour used anywhere in the product is one of the
   nine semantic tokens or its `-tint`. A component never writes a colour
   literal.

2. **Two bindings.** Every *colour* token has a light value and a dark value;
   the dark binding remaps the same names, so no colour token exists in one
   theme only. Non-colour tokens (spacing, type scale, radii, motion) are
   theme-independent and are declared once.

3. **Explicit choice wins.** `[data-theme="light"|"dark"]` overrides the OS.
   `@media (prefers-color-scheme: dark)` applies **only** when neither
   `data-theme` value is set. (Preserves the existing cascade at
   `styles.css:70-119`, which already gets this right.)

4. **Contrast.** Every foreground/background pairing that the stylesheet actually
   declares meets WCAG 2.1 AA in both themes: 4.5:1 for body text, 3:1 for text
   at 18.66px+ bold or 24px+, and 3:1 for meaningful non-text boundaries.

5. **Shadow-root injection.** The panel cannot inherit tokens through
   `all:initial`, so the same declarations are injected into its shadow root.
   The values are generated from one shared source, never hand-copied.

## Naming

`--paper --leaf --ink --ink-soft --rule --seal --pencil --flag --stop`
plus `--seal-tint --pencil-tint --flag-tint --stop-tint`.

Names describe **meaning in this product**, not hue. A future theme may make
`--seal` any colour; it must remain the one that says "done".

## Type

| Role | Family | Restriction |
|---|---|---|
| display | Archivo, expanded 700, tight tracking | tab labels, page titles |
| body | Archivo 400/600 | everything not display or data |
| data | IBM Plex Mono 400/600 | **only** scores, ids, dates, counts, versions, paths, form field names |

Each stack ends in a system fallback. A missing font file degrades, never breaks
layout (FR-007).

## Prohibitions

- No colour literal outside the token blocks — **in the stylesheet or the panel**.
- No `@import`, no `url()` pointing at any host. Every asset is a relative path.
- No token referenced that is not defined. (The `--bg` / `--border` bug in
  `styles.css:563-564` is exactly this failure and is removed.)
- Monospace on prose, headings, labels, buttons or nav is a contract violation.

## Test assertions

| # | Assertion |
|---|---|
| T1 | Every class used in `web/templates/**` resolves to a selector in the stylesheet |
| T2 | Zero colour literals outside `:root` / `[data-theme]` blocks, in the stylesheet and in `panel.js` |
| T3 | Every `var(--x)` reference resolves to a defined token |
| T4 | Every **colour** token declared in `:root` is re-bound in the dark block. Spacing, type, radii and motion are theme-independent and legitimately live in `:root` alone — requiring them to be repeated would be noise, not a contract. |
| T5 | Every declared fg/bg pairing meets AA in both themes (luminance computed in-test) |
| T6 | No external URL in any CSS or template; every `@font-face` src exists on disk |
| T7 | The panel's injected token names match the app's exactly |
