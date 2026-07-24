# Contract: widget fill + click guard (011)

Extends the 010 bridge protocol (contracts/bridge-protocol.md). Additive
only — every existing message/kind is unchanged.

## Descriptor additions (ext → app, in `fields`)

```
Descriptor += {
  widget: "native_select" | "custom_combobox" | "typeahead" | "",
  automation_id: string,   // Workday data-automation-id, else ""
}
```
`options` may now list a custom widget's readable option labels; `value` is
its currently displayed value. Byte-compatible with the Playwright
`SERIALIZE_JS` output (both backends emit the same shape → one classifier).

## FillItem additions (app → ext, in `fill`)

```
FillItem.kind ∈ { ...existing, "combobox", "typeahead" }
  combobox:  { je_idx, kind:"combobox", value, option_label }
  typeahead: { je_idx, kind:"typeahead", value }
```

## Executor contract (both backends)

- **combobox**: safeClick(control) → wait ≤1500ms for options → match
  `option_label` by normalized label → safeClick(option) → recheck displayed
  value changed → dispatch input+change. Fail/timeout → Escape, report
  `needs_manual`.
- **typeahead**: native-set `value` + input → wait ≤1500ms for suggestions →
  safeClick the matching suggestion. No match → report `needs_manual`.
- Every click on either backend passes through the guard: **refuse** if
  `is_denylisted(el)` (self + descendants, never ancestors). A refused click
  is never performed; the field reports `needs_manual`.

## Invariants (contract-level, tested)

1. The ONLY clicks either backend makes are through the guarded path; a
   denylisted (submit/apply/next/continue/save/finish/login/register/pay)
   control is never clicked — proven in JS unit-parity, Python unit matrix,
   and a real-browser fixture where a submit button is styled as an option.
2. Non-empty custom widgets are sacred; focused widgets are skipped;
   just-before-write recheck applies; the ledger is idempotent.
3. Sensitive tags (work-auth/visa/EEO) presented as a combobox still route
   through the confirm-gate and are never AI-drafted.
4. Report/outcome vocabulary and shapes are unchanged (new fills appear as
   `filled`/`no_match`/`needs_manual` like any field).
