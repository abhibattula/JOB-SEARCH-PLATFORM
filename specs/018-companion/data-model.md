# Data model — 018 The Companion

**No database change.** No table is added, altered or migrated. Everything here
is either live session state or a message payload. The only persistence this
feature touches is the existing answer bank, through the existing
`answer_bank.save()` path, unchanged from 017.

---

## 1. `PageAnswer` — one question as shown on the page

In-memory, per live session. Assembled in `ext_backend._handle_fields`, where
every field decision already passes and where `je_idx` is already in hand.

| field | type | source | notes |
|-------|------|--------|-------|
| `key` | str | `field_core.key(raw)` | the existing stable ledger key; also the panel's reconciliation key |
| `je_idx` | str | `raw["je_idx"]` | **new to the feed** — makes Insert and Show me possible (FR-020) |
| `question` | str | `label_text` → `placeholder` → `aria_label` | full text, not truncated |
| `answer` | str | `decision.preview` / drafter record | `""` when nothing was filled |
| `group` | enum | derived | `needs_you` \| `draft` \| `profile` |
| `reason` | str \| null | `drafter` record | why it was declined; drives the plain-language line |
| `askable` | bool | derived | `group == "needs_you"` and the question is answerable by typing |
| `state` | enum | derived | `filled` \| `drafted` \| `drafting` \| `needs_you` \| `refused` |

### Group derivation

| condition | group |
|-----------|-------|
| `decision.action == "skip"` **and** a drafter record marks it needs-you/refused | `needs_you` |
| `decision.ai_draft` is true | `draft` |
| any other decision that produced a value | `profile` |
| `decision.action == "ignore"` | *not listed* |

`needs_you` sorts first, then `draft`, then `profile`. Within a group, document
order.

### Lifecycle

Built fresh on each `fields` message; superseded wholly by the next build. Never
persisted. Cleared with the session (`ext_backend.reset_for_tests`,
`_watch` reset).

### Digest

A stable digest over the ordered list backs FR-027: if it equals the digest of
the last payload sent for this tab, nothing is pushed.

---

## 2. `CompanionState` — what the widget is showing

In-memory in the content script. Not persisted, not sent anywhere.

| field | type | notes |
|-------|------|-------|
| `collapsed` | bool | resting = `true`; survives same-document navigation (R9) |
| `dismissed_for` | str \| null | href the applicant dismissed; reset on navigation |
| `detection` | enum | `none` \| `form` \| `posting` \| `posting+form` |
| `session` | enum | `idle` \| `starting` \| `filling` \| `stopped` \| `done` |
| `posting` | object \| null | `{title, company, description, location, url}` — **the existing `current` object in `discovery.js`**, read directly (R2) |
| `score` | object \| null | `{match_score, band, sponsor_grade, cap_exempt, needs_resume, already_saved}` — today's `score_result` payload, unchanged |
| `counts` | object | `{seen, filled, needs_you, drafts}` — today's `overlay_state.summary`, unchanged |
| `answers` | PageAnswer[] | from the `answers` message |
| `notice` | str \| null | last app-side refusal/error, shown in the card (FR-033) |

### Derived: primary action (FR-007)

| session | detection | label | message sent |
|---------|-----------|-------|--------------|
| `idle` | `posting` or `posting+form` | Apply with Apply Assist | `apply_here` |
| `idle` | `form` | Fill this page | `fill_here` |
| `starting` | any | Starting… (disabled) | — |
| `filling` | any | Stop | `session_control{action:"stop"}` |
| `stopped` / `done` | any | Fill again | `fill_again` |

### Derived: resting pill content (FR-012)

| condition | pill shows |
|-----------|-----------|
| `needs_you > 0` | warning glyph + count |
| `session == "filling"` | `filled`/`seen` |
| `score` present | match score + band colour |
| otherwise | the wordmark alone |

### Light-DOM mirror (FR-017)

`data-je-*` attributes on the single host, carrying forward every attribute the
012/016/017 tests already assert (`jeScore`, `jeBand`, `jeCompany`,
`jeSponsor`, `jeSaved`, `jeCollapsed`, `jeSeen`, `jeFilled`, `jeNeedsYou`,
`jeAnswers`), plus `jeSession` and `jeDetection`.

---

## 3. `FormProbe` — read-only page signal

Returned by the new `jeScanner.probe()`. **Stamps nothing** — no `data-je-idx`,
no `data-je-doc` (R7).

| field | type | notes |
|-------|------|-------|
| `fields` | int | visible qualifying controls, excluding search-like inputs |
| `hasFile` | bool | a visible `input[type=file]` is present |
| `hasEmail` | bool | a visible `input[type=email]` is present |

`detection == "form"` when `fields >= 3`, or `hasFile && fields >= 1`, or
`hasEmail && fields >= 3`.

---

## 4. Message payload changes

All additive; **`PROTOCOL_V` stays `1`**. Full shapes in
[contracts/bridge-protocol-additions.md](contracts/bridge-protocol-additions.md).

| message | direction | change |
|---------|-----------|--------|
| `answers` | app → ext | items gain `je_idx`, `group`, `key`; existing fields unchanged |
| `session_control` | ext → app | **new type**: `{tab_id, action}` where action ∈ `stop` \| `next` |
| `overlay_state` | app → ext | gains `session`, `current_job_id`, `remaining` (optional) |

---

## 5. Entities explicitly NOT introduced

- **No new table.** `ai_drafts`, `answer_bank`, `answer_applications` and
  `user_profile` are untouched.
- **No new stored answer provenance.** A companion-typed answer is saved through
  `answer_bank.save()` with source `user`, exactly as 017 (FR-025).
- **No new capability on the wire.** `session_control` maps onto
  `browser_controller.stop_queue()` / `advance()`, which the app's own routes
  already call.
