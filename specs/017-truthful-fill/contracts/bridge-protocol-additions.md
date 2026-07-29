# Contract: Bridge protocol additions (feature 017)

**PROTOCOL_V remains `1`.** Every change below is additive with a default, per
the rule documented at `engine/autofill/ext_protocol.py:68-72`. Older
companions ignore unknown message types (`default: break` in
`extension/background/service-worker.js`) and unknown fields
(`ConfigDict(extra="ignore")`), so a version bump — which would hard-reject
them with close code 4426 — is not needed.

---

## 1. `answers` — app → extension (NEW)

Sent whenever the answer set for the watched job changes, alongside the
existing `overlay_state`.

```json
{
  "v": 1, "type": "answers", "seq": 42,
  "tab_id": 17,
  "job_id": 6532,
  "items": [
    {
      "je_idx": "23",
      "question": "What is your GPA?",
      "answer": "3.2",
      "state": "filled",
      "reason": null,
      "askable": false
    },
    {
      "je_idx": "31",
      "question": "Have you ever applied to a full time or internship position with Akuna in the past?",
      "answer": "",
      "state": "refused",
      "reason": "never_generated",
      "askable": true
    }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `tab_id` | int | yes | |
| `job_id` | int | yes | `-2` for an ad-hoc session |
| `items[].je_idx` | str | no | absent when the answer is not bound to a visible field |
| `items[].question` | str | yes | as the form asks it |
| `items[].answer` | str | yes | **full text**, not the 120-char activity preview; `""` when refused |
| `items[].state` | enum | yes | `filled` \| `drafted` \| `needs_you` \| `refused` |
| `items[].reason` | str \| null | no | drafter reason vocabulary |
| `items[].askable` | bool | yes | panel offers a capture input when true (D7) |

**Invariants**

- `answer` MUST NOT contain a password or any credential; credential tags never
  enter the answer feed.
- `state = "filled"` implies the value was written to `je_idx` this session.
- `askable = true` implies `state ∈ {needs_you, refused}`.
- The message MUST stay under `MAX_MESSAGE_BYTES` (1 MB); items are truncated
  oldest-first if necessary and truncation is reported in `overlay_state`.

---

## 2. `rescan` — app → extension (EXISTING, currently unhandled)

Already emitted from three call sites and silently dropped. This feature
implements the receiving half; the wire shape is unchanged.

```json
{ "v": 1, "type": "rescan", "seq": 43, "reason": "draft_ready" }
```

`reason` ∈ `draft_ready` | `fill_again` | `user_rescan`.

**Behaviour**: the service worker forwards it to the watched tab; the content
script performs one immediate scan. It MUST NOT reset any drafter state — the
app owns retry policy (R1).

---

## 3. `answer_question` — extension → app (NEW)

Sent when the applicant types an answer into the panel for a question the
system declined to answer (D7, FR-045).

```json
{
  "v": 1, "type": "answer_question", "seq": 12,
  "tab_id": 17,
  "je_idx": "31",
  "question": "Have you ever applied to a full time or internship position with Akuna in the past?",
  "answer": "No"
}
```

**Behaviour**

1. Saved to the answer bank with `source = 'user'` (FR-046) — never `'ai'`, so
   a later purge of fabricated answers leaves it intact.
2. The drafter record for that question is cleared, so the field is re-decided.
3. A `fill` is dispatched for `je_idx` using the normal shape rules — a value
   that does not fit the control is reported, not forced.

**Invariants**: `answer` is stored verbatim as the applicant typed it; the app
MUST NOT rewrite, expand or "improve" it.

---

## 4. `apply_here` — extension → app (NEW)

Sent by the floating badge's "Apply with Apply Assist" button (FR-038).

```json
{
  "v": 1, "type": "apply_here", "seq": 8,
  "tab_id": 17,
  "url": "https://job-boards.greenhouse.io/akuna/jobs/6532",
  "title": "Software Engineer (Entry-Level) - C++",
  "company": "Akuna Capital",
  "description": "…"
}
```

**Behaviour**: upsert the posting (the same path as `save_job`), then start a
watched session on **that tab** with the resulting real `job_id` — i.e. a
non-ad-hoc watch, so the apply-opener is armed.

**Invariants**: it starts a fill session and nothing else. It MUST NOT click
any page control, and the badge itself continues to mutate nothing.

---

## 5. `FillItem` — additive fields

```python
class FillItem(_Strict):
    je_idx: str
    kind: Literal["text", "select", "checkbox", "file", "secret",
                  "combobox", "typeahead", "radio"]   # UNCHANGED
    value: str = ""
    option_label: str | None = None
    file_url: str | None = None
    filename: str | None = None    # NEW — the real upload name (FR-031)
    mime: str | None = None        # NEW — expected type, used for verification
    flag: Literal["ai_draft", "needs_you"] | None = None
```

`kind` gains **no** new value. A merged checkbox group emits one existing
`kind:"checkbox"` item per selected member, addressed by that member's
`je_idx`, so no version gate is required and an older companion cannot
mis-fill.

`filename`/`mime` are ignored by an older companion, which keeps today's
hardcoded name — a cosmetic regression, not a wrong-file one, because the
transport change (§6) ships in the same companion version.

---

## 6. File transport (replaces the content-script fetch)

**Extension-internal**, not a bridge message — content script → service worker
via `chrome.runtime.sendMessage`.

```
content →  { _je_file: true, path: "/api/bridge/file/<token>" }
  SW   →  fetch("http://127.0.0.1:" + port + path)        // host permission
  SW   →  { ok: true, name, mime, size, bytes }           // bytes: base64
        | { ok: false, error: "http_404" | "not_a_document" | "no_pairing" }
```

**Why**: the app emits a relative `file_url`; a content-script fetch resolves it
against the job board, and Greenhouse answers unknown paths with its SPA HTML
and status 200 — producing a `File` named `resume.pdf` containing HTML. An
absolute URL fails differently (MV3 content-script fetches carry the page
origin and the app sets no CORS headers). The service worker holds
`host_permissions: ["http://127.0.0.1/*"]` and `main.js:22` already forbids
content scripts from reaching loopback directly.

**Verification, before the file is attached** (FR-030):

- first bytes are `%PDF` when `mime` is `application/pdf`;
- length > 0 and within tolerance of the app-declared size;
- otherwise **nothing is attached** and the field reports `needs_manual`.

The single-use 60 s file token (`ext_backend.issue_file_token`) is unchanged
and remains the endpoint's whole auth.

---

## 7. `Descriptor` — additive

| Field | Change |
|---|---|
| `type` | new value `"checkbox_group"` |
| `members` | reused for checkbox groups |
| `options` | populated from member labels for merged groups |
| `widget` | inherited by inputs nested inside a choice widget |

Older *app* versions receiving these ignore them (`extra="ignore"`); older
*serializers* simply omit them and the defaults keep their payloads valid.

---

## 8. Compatibility matrix

| App | Companion | Result |
|---|---|---|
| 1.7.0 | 1.7.0 | all features |
| 1.7.0 | 1.6.0 | `answers`/`rescan`/`apply_here` ignored; panel shows 1.6 behaviour; **resume attach still uses the broken content-script fetch** — the doctor already surfaces the version mismatch and the user is told to reload the companion |
| 1.6.0 | 1.7.0 | new inbound types rejected by `parse_inbound`; no crash |

The existing exact-version gate (`ext_backend.py:443-455`) is unchanged and
still governs `kind:"radio"`.
