# Contract: HTTP API changes (010)

All existing endpoints keep their shapes. Additions/changes only.

## Bridge

| Endpoint | Method | Contract |
|---|---|---|
| `/api/bridge/info` | GET | `{app_id, app_version, protocol_v}` — unauthenticated identity probe used by the SW before sending the secret |
| `/api/bridge/file/<token>` | GET | one-time resume-file fetch for a pending `file` FillItem; token single-use, expires 60s; 404 after use/expiry |
| `/ws/ext` | WS | see bridge-protocol.md |

## Autofill

| Endpoint | Change |
|---|---|
| `GET /api/autofill/status` | payload adds `backend: "extension"\|"playwright"\|null` and `extension: {connected, version, last_seen}`; everything else unchanged |
| `POST /api/autofill/start` (existing start_queue route) | unchanged shape; backend chosen server-side (AUTOFILL_BACKEND setting honored) |
| `GET /api/autofill/drafts` | NEW — list ai_drafts for the active session/job `[{id, question, draft_text, status, job_id}]` |
| `POST /api/autofill/drafts/{id}` | NEW — body `{action: "confirm"\|"discard", text?}`; confirm (optionally edited text) → answers row (provenance `confirmed`) + re-fill instruction if the field is still empty/draft-valued |
| `POST /api/autofill/adhoc/link` | NEW — body `{tab_session, job_id?}`; link an ad-hoc fill session to an existing job or create one (user-confirmed from UI) |

## Tracker / next actions

| Endpoint | Change |
|---|---|
| `GET /api/next-actions` | NEW — `[{kind: "draft_review"\|"follow_up"\|"import_ready"\|"submission_confirm", job_id?, label, href}]` (derived; nothing stored) |
| `POST /api/jobs/{id}/follow-up` | NEW — body `{follow_up_at?, notes?}` (either optional; null clears) |
| `POST /api/jobs/{id}/submission-confirm` | NEW — body `{confirmed: bool}`; true → status applied + auto-save final draft texts (provenance `auto_saved`); false → dismiss the next-action, nothing changes |

## Pages

| Route | Change |
|---|---|
| `/` | home dashboard (top matches, stage stats, next actions) — replaces feed-first home; feed remains at `/feed` |
| `/companion` | NEW — guided install walkthrough (copyable extension path, step visuals, live connection check) |
| existing pages | restyled under the token layer; no route changes |

## Compatibility guarantees

- `queue_snapshot`/fill-report shapes are unchanged (new outcome string
  `ai_draft` may appear in reports; existing consumers render unknown
  outcomes as plain text — verified in tests).
- All 009 endpoints (practice, import, activity) unchanged (FR-024).
