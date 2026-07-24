# Contract: Discovery bridge messages

Extends the feature-010 companion protocol (`engine/autofill/ext_protocol.py` is
authoritative; `extension/background/*` mirrors names). All envelopes carry
`{"v": 1, "type", "seq"}`; the 1 MB size bound and strict validation apply.
Discovery adds **two inbound** and **two outbound** message types. They are
handled by `ext_backend` **without reading or mutating the fill session state**
(`_watch`, `_inflight`, `_frame_seen`, `bc._state`).

## Inbound (content script → app)

### `score_request`
```json
{ "v":1, "type":"score_request", "seq":0,
  "tab_id":123, "url":"https://…/jobs/view/456",
  "title":"New Grad Software Engineer",
  "company":"Aurora Semiconductors",
  "description":"…job description text…" }
```
- `tab_id` is stamped by `relayFromContent`; the content script omits it.
- `description` is truncated defensively by the handler before scoring/logging.
- Empty `title` AND `description` → handler returns a neutral result (no error).

### `save_job`
```json
{ "v":1, "type":"save_job", "seq":0,
  "tab_id":123, "url":"https://…/jobs/view/456",
  "title":"New Grad Software Engineer",
  "company":"Aurora Semiconductors",
  "description":"…", "location":"Austin, TX" }
```
- `location` optional (default `""`).

## Outbound (app → content script, routed to top frame via `toContent(tab_id,…,0)`)

### `score_result`
```json
{ "v":1, "type":"score_result", "seq":N, "tab_id":123,
  "match_score":72, "band":"good",
  "matching_skills":["python","verilog"], "missing_skills":["uvm"],
  "sponsor_grade":"B", "cap_exempt":false, "approvals":215,
  "has_sponsor_data":true, "needs_resume":false, "already_saved":false }
```
- `match_score` null + `needs_resume` true when no resume/profile is saved.
- `sponsor_grade` null + `has_sponsor_data` false → badge shows "H-1B: unknown".
- `already_saved` true → badge opens in the "Already saved" state.

### `save_result`
```json
{ "v":1, "type":"save_result", "seq":N, "tab_id":123,
  "status":"inserted", "job_id":789, "already":false }
```
- `status` ∈ {inserted, updated, skipped} (from `db.upsert_job`).
- `already` true when the posting already existed (repeat save; no duplicate).

## Guarantees (asserted by test)

- **Independence**: a `score_request`/`save_job` handled with **no active watch
  session** still produces a correct `score_result`/`save_result`, and leaves
  `ext_backend._watch` untouched. Conversely, discovery messages never appear in
  a fill report or change `bc._state.activity`.
- **Read-only page**: the content script that produces these messages performs no
  page `.click()`/input/submit (static assert + real-browser inspection).
- **Local-only**: these messages traverse only the authenticated loopback
  `/ws/ext` socket; no external network call is made on discovery's behalf.
- **No new secret**: discovery reuses the existing pairing secret; it adds no
  auth surface.
