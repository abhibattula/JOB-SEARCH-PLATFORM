# Contract: rich-text scan and write

Makes editable regions (rich-text cover-letter editors) first-class fields.
`PROTOCOL_V` stays **1** — every descriptor field used below already exists.

---

## Scan (`extension/content/scanner.js`, mirrored in `watcher.py`)

`FIELD_SELECTOR` gains:

```
[contenteditable=""], [contenteditable="true"], [role=textbox]
```

**Exclusions** — a rich-text region is skipped when it is:

- inside a credential form (the existing `inCredentialForm` rule), or
- `aria-readonly="true"` / `contenteditable="false"`, or
- not visible by the existing 019 `isVisible` rule (real client rect, not
  hidden, not parked off-screen).

**Descriptor mapping**

| field | source |
|---|---|
| `type` | `"richtext"` |
| `value` | `el.innerText` (trimmed) — an editable `div` has no `.value` |
| `name` | absent; classification falls back to `automation_id`, `id`, label text |
| label | the unchanged 019 ladder: `aria-label` → `aria-labelledby` → wrapping label with controls stripped → preceding sibling |
| `je_idx` | stamped on the editable element itself |

**Guarantees**

- **S1** (FR-016) — a rich-text region is discovered and counted by `probe()`
  and `serialize()` exactly as a `textarea` is, including inside open shadow
  roots (the 019 `deepQueryAll` path).
- **S2** — `"richtext"` is text-ish: it counts toward
  `looksLikeApplicationForm`'s two-text-field floor.
- **S3** — the serializer in `engine/autofill/watcher.py` (`SERIALIZE_JS`)
  produces byte-identical descriptors for the same page. The existing parity
  test covers this and must be extended, not bypassed.
- **S4** — an empty editor reads as empty. A placeholder rendered by the
  editor as a child element must not be mistaken for a user value (the 019
  `isPlaceholderValue` rule applies).

---

## Decide (`engine/autofill/field_core.py`, `fields.py`)

- **D1** — `"richtext"` is decided by the same path as `textarea`: same tag
  classification, same answer sources, same v1.7.0 refusal contract. A
  cover-letter tag on a rich-text box behaves exactly as on a textarea.
- **D2** (FR-019) — a visible, required rich-text region holding no answer
  counts toward `visible_required_pending`, so the escort will not advance past
  an empty cover letter.
- **D3** — with no `name`, classification uses `automation_id`, `id`, and label
  text. It must not fall back to a wrong tag because `name` is missing;
  unclassifiable stays `free_text_unknown`, as today.

---

## Write (`extension/content/filler.js`)

One new `kind: "richtext"` branch. **`filler.js` keeps exactly one raw
`.click(` site** — the 016 pin — and this branch adds none.

Sequence:

1. `el.focus()`
2. select the region's contents (range over the element)
3. insert the text — `beforeinput`/`insertText` where supported, falling back
   to `document.execCommand("insertText")`, and to setting `textContent` only
   as a last resort
4. dispatch `input` (bubbling, `InputEvent`) and then `change`
5. **verify**: re-read `innerText` and compare against the intended value

**Guarantees**

- **W1** (FR-017) — the host page registers the write as user input. React,
  ProseMirror and Quill all ignore a silent DOM mutation, so the dispatched
  `input` event is what makes the value stick.
- **W2** (FR-018) — if step 5 shows the text did not land, the outcome is
  `needs_manual` naming the field. **There is no silent third state**: every
  rich-text field ends as `filled` or as a visible needs-you item.
- **W3** — the existing per-widget budget (`OPTION_WAIT_MS`, 1500 ms) bounds
  the write; a hung editor degrades to `needs_manual` rather than stalling the
  fill.
- **W4** — secrets are never written to a rich-text region: `kind: "secret"`
  and `richtext` are mutually exclusive, and the credential-form exclusion in
  the scan makes such a region unreachable anyway.

---

## Fixtures

| file | shape |
|---|---|
| `tests/fixtures/ats_pages/richtext_cover_letter.html` | Greenhouse-style `div[contenteditable=true]` labelled by `aria-labelledby`, with a required marker |
| `tests/fixtures/ats_pages/lever_richtext.html` | Lever-style `[role=textbox]` inside a wrapping label, with an editor-rendered placeholder child |

Both are exercised by the real-browser suite: discovered, counted, written,
verified — and one is asserted to block the escort while empty (D2).
