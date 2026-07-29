# Contract: Bridge protocol additions (feature 018)

**PROTOCOL_V remains `1`.** Every change below is additive with a default, per
the rule at `engine/autofill/ext_protocol.py:68-72`. Older companions ignore
unknown message types (`default: break` in
`extension/background/service-worker.js`) and unknown fields
(`ConfigDict(extra="ignore")`), so a version bump — which would hard-reject them
with close code 4426 — is not needed.

---

## 1. `answers` — app → extension (EXTENDED)

Sent when the assembled answer set for the watched tab **changes**. Unchanged
sets are not sent at all (FR-027).

```json
{
  "v": 1,
  "type": "answers",
  "tab_id": 42,
  "job_id": 17,
  "truncated": false,
  "items": [
    {
      "key": "label:are-you-authorized-to-work",
      "je_idx": "12",
      "question": "Are you authorized to work in the United States?",
      "answer": "Yes",
      "group": "profile",
      "state": "filled",
      "reason": null,
      "askable": false
    },
    {
      "key": "label:when-does-your-authorization-expire",
      "je_idx": "13",
      "question": "When does your work authorization expire?",
      "answer": "",
      "group": "needs_you",
      "state": "needs_you",
      "reason": "profile_fact_missing",
      "askable": true
    }
  ]
}
```

### Fields added in 018

| field | type | default | meaning |
|-------|------|---------|---------|
| `key` | string | `""` | stable reconciliation key (`field_core.key`) |
| `je_idx` | string | `""` | the field this answer belongs to; enables Insert and Show me |
| `group` | string | `"profile"` | `needs_you` \| `draft` \| `profile` |

`question`, `answer`, `state`, `reason`, `askable` are unchanged from 017.

### Rules

- `items` MUST include every field the app made a fill/skip decision about for
  this job — not only questions the AI drafter touched (FR-019).
- An empty `je_idx` is legal (a merged group whose member vanished); the
  companion then renders Copy only, never a broken Insert.
- `truncated: true` means the list was clipped to fit the message budget; the
  companion says the app holds the complete list (FR-029).
- Answer text is data, never markup. The companion renders it as text (FR-028).
- Secrets are never present: fields decided as `decision.secret` are excluded
  from the feed entirely (FR-037).

---

## 2. `session_control` — extension → app (NEW)

```json
{ "v": 1, "type": "session_control", "seq": 0, "tab_id": 42, "action": "stop" }
```

| field | type | required | values |
|-------|------|----------|--------|
| `action` | string | yes | `stop` \| `next` |

### Semantics

| action | app behaviour |
|--------|---------------|
| `stop` | `browser_controller.stop_queue()` — identical to `POST /api/autofill/stop` |
| `next` | `browser_controller.advance()` — identical to `POST /api/autofill/next` |

### Rules

- Ignored unless `tab_id` matches the currently watched tab — the same guard
  `_handle_fill_again` and `_handle_answer_question` already apply.
- Confers **no new capability**: both actions are already reachable from the
  app's own Apply Assist page. This only removes the tab switch.
- An unknown `action` is a protocol reject (counted), not a crash.
- Never triggers a submit, login, or navigation of the applicant's page.

### Backward compatibility

An **older app** with a newer companion: `session_control` is not in
`_INBOUND`, so it is rejected and counted by the existing protocol-reject path;
the companion surfaces the refusal (FR-010) and the applicant uses the app.
Nothing crashes.

A **newer app** with an older companion: the companion simply never sends it.

---

## 3. `overlay_state` — app → extension (EXTENDED)

Three optional fields, so the companion can show session context without
polling the app (FR-032).

```json
{
  "v": 1, "type": "overlay_state", "tab_id": 42,
  "summary": {
    "seen": 22, "filled": 14, "needs_you": 3, "drafts": 2,
    "needs_you_idx": ["13", "19", "27"],
    "attention": ["When does your work authorization expire?"],
    "message": "you click the actual apply/submit",

    "session": "filling",
    "current_job_id": 17,
    "remaining": 2
  }
}
```

| field | type | default | meaning |
|-------|------|---------|---------|
| `session` | string | `"filling"` | `idle` \| `starting` \| `filling` \| `stopped` \| `done` |
| `current_job_id` | int \| null | `null` | the job being filled; `null` for ad-hoc |
| `remaining` | int | `0` | jobs left in the queue after this one |

---

## 4. `error` — app → extension (ROUTING CHANGE ONLY)

The message is unchanged. Today the service worker stores it for the popup
only (`service-worker.js:56-61`); 018 also forwards it to the watched tab's top
frame so the refusal appears in the companion (FR-033). No schema change.

---

## 5. `rescan` — app → extension (UNCHANGED)

Behaviour as shipped in 017. Listed only to state that 018 does not change it.

---

## 6. Invariants this contract does not relax

- `PROTOCOL_V == 1`.
- The applicant performs every submit, login and wizard step. No message in this
  protocol causes one.
- The pairing secret never appears in any message, log, report or diagnostic.
- Message size stays within `MAX_MESSAGE_BYTES`; `answers` clips and sets
  `truncated`.
- The companion mutates no page element except a field the applicant explicitly
  chose via Insert.
