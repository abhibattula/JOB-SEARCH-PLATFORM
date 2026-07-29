# Contract: Answer resolution and shape (feature 017)

The single ordered path from a scanned field to a value written on the page.
Both fill backends (companion and Playwright) consume this identically through
`engine/autofill/field_core.decide`.

---

## 1. Resolution order

```
descriptor
  │
  ├─ 1. document-level name layout          (field_core.name_layout)
  ├─ 2. per-ATS adapter tag                 (adapters.classify)
  ├─ 3. generic classifier tag              (fields.classify)
  │
  ├─ 4. NEVER-GENERATED gate                (drafter never sees these)
  │        self-ID · factual history · criminal history · references
  │        · binding acknowledgement
  │
  ├─ 5. profile resolver                    (profile_answers.answer_for)   ← NEW
  ├─ 6. answer bank (user/confirmed first)  (answer_bank.lookup)
  ├─ 7. drafter cache                       (drafter.answer_for)
  └─ 8. schedule a draft, return None       (drafter.ensure)
```

**Rules**

- Step 4 is absolute: a tag in the never-generated set never reaches steps 7–8.
  It is answered at step 5 or 6, or it becomes needs-you.
- Step 5 precedes the bank so a corrected profile immediately overrides a stale
  learned answer.
- A bank row with `source = 'ai'` is returned wrapped as a draft (purple
  highlight); `user`/`confirmed` rows are returned as settled values.
- `None` at every step ⇒ `Decision("skip")`; the field is untouched and, when a
  drafter record marks it needs-you, highlighted.

---

## 2. Shape predicate (FR-012)

`field_core.value_fits(descriptor, value) -> (bool, reason)` — pure, shared by
`decide()` (before emitting a fill) and `drafter._validate` (before accepting a
generation).

| Descriptor shape | Accepts | Rejects with |
|---|---|---|
| choice, options known | exactly one option after canonical matching | `no_valid_option` |
| choice, options unknown (custom combobox, or an input nested in one) | an option-like label: ≤ 4 words, no sentence-ending punctuation, ≤ 60 chars | `not_an_option_label` |
| `radio_group` | one member label | `no_valid_option` |
| `checkbox_group` | one or more member labels | `no_valid_option` |
| free text with `maxlength` | text truncated to the limit | — |
| free text, **descriptive intent** (expiry, status, detail, extension, explain, describe, list) | a structured profile value | `wrong_shape` for a bare yes/no token |
| file | an existing readable path | `wrong_shape` for any non-path |

**The yes/no rule (C5).** `authorized_without_sponsorship` derives `Yes`/`No`.
That derivation may fill a **yes/no-shaped choice control only**. Four Akuna
questions matched the work-authorization regex but were free text asking for a
date, a status, extension options and a description — each received "Yes".
Under this contract each resolves from its own profile column
(`work_auth_expiry`, `work_auth_status`, `work_auth_extensions`,
`sponsorship_detail`) or becomes needs-you.

**The prose rule (C6/C7).** Prose never reaches a choice control, including one
whose options are not yet readable. The predicate consults the descriptor's
shape *and its ancestry*, so an input nested inside a choice widget is judged
as a choice control even if its own attributes look like free text.

---

## 3. Generation contract (FR-006, FR-007)

The drafter may generate for **open-ended, résumé-grounded** questions only:
`cover_letter`, `free_text_unknown`, and free-text fields whose answer is
derivable from the résumé.

**Prompt inputs**

| Prompt | Receives | Never receives |
|---|---|---|
| factual / short answer | résumé text, profile fields | company name, role title, job description |
| cover letter / motivation | résumé text, profile fields, company + role + description | — |

**Refusal**: when the answer is not present in the applicant's own material the
model MUST return the refusal token `CANNOT_ANSWER`. `_validate` maps it to
`(False, None, "cannot_answer")`, a non-retryable needs-you reason. An empty or
whitespace answer is treated as a refusal, not an error to retry indefinitely.

**Bounds**: at most `MAX_ATTEMPTS_PER_QUESTION` (2) generations per question and
`MAX_DRAFTS_PER_JOB` (40) per job session. Completing one draft MUST NOT reset
any other question's backoff.

---

## 4. Option matching (FR-024, FR-025)

`fields.match_option(answer, options, tag=None)` — four ordered passes:

1. exact after `strip().casefold()`
2. prefix ending on a word boundary (`"Yes"` → `"Yes, I am authorized…"`)
3. `rapidfuzz.fuzz.ratio ≥ 87`
4. **canonical** — map the answer and each option into `tag`'s vocabulary
   family and compare canonical forms (NEW)

Pass 4 is exact-on-canonical and therefore adds no fuzziness. For
`work_authorization` and `sponsorship_requirement` the family is `yes_no` with
**no loose synonyms**, preserving today's strictness (FR-025). No match at any
pass ⇒ `no_match`, epoch-retryable, never approximated.

---

## 5. Never-generated set

Self-identification (`selfid_*`, `pronouns`, `eeo_disclosure`) · factual
history (`applied_before`, `worked_here_before`, `prior_industry_experience`,
`completed_course`, `offer_deadlines`, `residency_state`,
`currently_employed`) · `criminal_history` · `references` · binding
`acknowledgement`.

Each resolves from the profile or the answer library, or becomes needs-you with
`askable = true` so the panel can capture it once and reuse it forever (D7).

**Binding vs routine acknowledgement (D5)**: binding when exclusivity language
is present — "top preference", "will not be considered", "sole application",
"not be considered for other", "non-compete". Binding is never answered by any
path, including the library, and is surfaced with its full question text.

---

## 6. Invariants that must never regress

1. A non-empty existing value is sacred — the applicant's own input is never
   overwritten.
2. The focused field is never written to.
3. No submit, login, registration, payment or wizard-advance control is ever
   clicked.
4. No binding commitment is agreed on the applicant's behalf.
5. Credentials never enter the answer feed, the bank, the drafts table, logs,
   reports or diagnostics.
6. An unmatched or unfitting value leaves the field untouched and flagged —
   never guessed, never approximated, never partially written.
