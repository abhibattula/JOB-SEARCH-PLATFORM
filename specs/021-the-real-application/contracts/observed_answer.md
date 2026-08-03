# Contract — observed answers (what the applicant types is learned)

**Module**: `engine/autofill/answer_bank.record_observed()`
**Callers**: `engine/autofill/ext_backend._handle_fields` only.

## Capture predicate

An answer is captured **only** when every one of these holds:

1. The app did **not** fill this field (`decision.action != "fill"`, and no
   inflight record for it). This must cover **both** branches of
   `field_core.decide`'s present-value path: a classified field returns
   `settle`/`skipped_existing`, but an unclassified one
   (`tag == "free_text_unknown"`) returns a plain `skip`. Keying only on
   `settle` would miss every essay answer.
2. The field was observed **empty** on an earlier scan of the same document in
   this session, and is non-empty now.
3. Its resolved question is non-empty after stripping.
4. Its classified tag is not on the deny-list below.
5. Its value is not itself a placeholder (`field_core.is_placeholder_value`).

Condition 2 is what separates *the applicant answered this* from *the employer
prefilled it* or *the browser's password manager filled it*. A value present on
first sight is never the applicant's answer.

## Deny-list — refused before any storage, logging or reporting

Refusal happens at the top of `record_observed()`, before the value is copied
anywhere.

| class | source of truth |
|---|---|
| credentials and secrets | `ext_backend._CREDENTIAL_TAGS`, `decision.secret` |
| voluntary self-identification | any tag matching `selfid_*` |
| national identifier | SSN / SIN / NI number / national ID, by tag and by question match |
| date of birth | `dob` tag and question match |
| government identifier | passport, driving licence number, visa number |
| financial detail | bank account, routing, sort code, card |

The question-text matcher is case-insensitive and reuses the existing vocab
patterns rather than introducing a second, divergent list.

**Test requirement**: asserted in **both** directions — a denied field stores
nothing (and appears in no log, report or diagnostic), and an ordinary field
does store. A one-directional test here would pass against a function that
never stores anything at all.

## Write rule

`answer_bank.question_normalized` is `UNIQUE`. Given an existing row:

| existing provenance | action |
|---|---|
| *(none)* | insert with `source="observed"` |
| `observed` | update the answer, refresh `updated_at` |
| `user`, `confirmed`, `auto_saved` | **no write** |
| `model` | overwrite with `observed` — a real answer beats a generated one |

**Implementation constraint (analysis A1).** `record_observed()` must **not**
delegate to `answer_bank.save_with_provenance`. That function's
`ON CONFLICT(question_normalized) DO UPDATE SET` is **unconditional**
(`answer_bank.py:109`) and would destroy a confirmed answer. Use a guarded
upsert whose conflict branch carries
`WHERE answer_bank.source IN ('observed', 'model')`, inside one transaction.
`save_with_provenance` itself is unchanged — its existing callers depend on
overwriting.

## Profile suggestion, never profile write

When an observed answer's tag is in `profile_answers.PROFILE_ANSWER_TAGS`, the
Learned answers page offers a one-click "Save to profile". The profile is
**never** written automatically (FR-020) — reading a value off a page is not
the same as the applicant asserting it as a stored fact about themselves.

## Applicant control

- Every observed answer is listed on the Learned answers page with its
  question, answer, the application it came from, and when.
- Each is editable and deletable individually.
- "Forget everything learned" deletes all rows with `source="observed"` and
  nothing else.
