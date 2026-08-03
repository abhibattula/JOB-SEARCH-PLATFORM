# Contract — section context on a field descriptor

**Direction**: companion (`extension/content/scanner.js`) → app
(`engine/autofill/ext_protocol.py`)
**Protocol version**: `PROTOCOL_V` stays **1**. Additive only.

## Shape

`form_context` is today a bare string (`""` / `"login"` / `"registration"`),
produced by `scanner.js formContext()` and mirrored in
`engine/autofill/watcher.py SERIALIZE_JS`. It gains two sibling keys on the
descriptor, kept flat so the pydantic model stays a simple field set:

```json
{
  "form_context": "",
  "section_label": "Work Experience",
  "section_index": 1
}
```

| key | type | default | meaning |
|---|---|---|---|
| `section_label` | string | `""` | resolved name of the enclosing form section |
| `section_index` | integer | `0` | 0-based ordinal among repeats of that same label in the document |

## Compatibility rules

- **`form_context` keeps its exact current values and meaning.** The login and
  registration paths in `ext_backend` are untouched.
- Both new keys are **optional with defaults** on the pydantic model. A
  companion older than this release omits them, and the app behaves exactly as
  v2.0.0 did — flat grouping, no history filling.
- `section_label: ""` means *undetermined*, not *no section*. The app must
  degrade to flat grouping, never guess. Wrong grouping is worse than none.
- A newer companion talking to an older app sends fields the old model does not
  declare. `Descriptor` must therefore keep tolerating unknown keys — this is
  the 020 lesson where a `Literal` on `widget` rejected an **entire** fields
  message because of one unrecognised value. Pinned by a test asserting both
  directions.

## Resolution order (companion side)

First hit wins:

1. nearest ancestor `fieldset` → its `legend` text
2. nearest ancestor `[data-automation-id$="Section"]`,
   `[data-automation-id$="Panel"]`, `[role=group]` or `[role=region]` → its
   accessible name (`aria-label`, then `aria-labelledby`)
3. nearest preceding heading (`h1`–`h6`) of an ancestor block
4. `""`

Text is taken with the existing `stripControls()` helper, so a section whose
container also renders a control's own text cannot pick that text up — the
019/020 bug class, in a third place.

`section_index` counts prior occurrences of the **same resolved label** in
document order. It is computed per scan and **never** written to the DOM.

## Parity requirement

`scanner.js` and `watcher.py SERIALIZE_JS` must produce byte-identical
descriptors. The existing parity test in `tests/test_extension_assets.py`
covers this and must be extended to the new keys — a serializer that drifts is
how the Playwright escort path and the companion path silently disagree.
