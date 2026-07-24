# Research: The Copilot Release (010)

All unknowns resolved 2026-07-23 via three web-research passes (competitor
mechanics; signing; MV3/localhost) + one architecture design pass. No
NEEDS CLARIFICATION remain.

## D1. Extension ↔ app transport

- **Decision**: WebSocket from the MV3 service worker to
  `ws://127.0.0.1:<port>/ws/ext` on the app's existing FastAPI server
  (starlette WebSocket — no new dependency). All localhost traffic goes
  through the service worker; content scripts talk to the SW via runtime
  messaging only.
- **Rationale**: extension origin is a secure context and loopback is
  exempt from mixed-content blocking; Chrome ≥116 resets the SW idle
  timer on WebSocket activity (20s ping keeps it alive — officially
  documented pattern); routing through the SW sidesteps Chrome 142's
  Local Network Access gating of page-context→loopback requests.
- **Alternatives considered**: Chrome Native Messaging (no open port,
  Chrome-verified extension ID — but needs a host exe + registry key,
  1MB message cap, clumsy stdio framing from Python; rejected as the
  primary, noted as future hardening); plain HTTP polling (chattier,
  no server-push for open_tab/fill commands; rejected).

## D2. Port discovery + authentication (pairing)

- **Decision**: the app owns the unpacked extension folder
  (`<data_dir>/extension/`) and stamps `pairing.json` = `{port, secret,
  app_id}` at every launch after binding its dynamic port. The SW reads
  it via `fetch(chrome.runtime.getURL('pairing.json'))` on every connect
  attempt — unpacked extensions re-read packaged files from disk, so no
  reload is needed. First WS frame `hello {secret}`; mismatch → close
  4401. Secret: 32 random bytes, stored in the app DB, rotated only on
  user request.
- **Rationale**: zero pairing UX; no port scanning; any local process
  can hit a localhost port, so the shared secret gates fill instructions
  and profile data (FR-002); the folder is the trust anchor because only
  the app (and the user) write it.
- **Alternatives**: manual pairing code UX (kept only as popup recovery
  path); fixed port (collision-prone; app already uses dynamic ports);
  port-range probing (slow, noisy, unnecessary given pairing.json).

## D3. Filling React/controlled inputs from a content script

- **Decision**: set values via the native prototype setter
  (`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')
  .set.call(el, v)`) then dispatch bubbling `input` + `change` events;
  same pattern for textarea/select. Custom comboboxes (React-Select
  etc.) are reported `needs_manual` — never clicked (constitution).
- **Rationale**: React tracks values through its own descriptor; plain
  `.value=` assignments are invisible to it. This is the standard,
  store-approved technique used by production autofill extensions.
- **Alternatives**: simulated keystrokes (slower, focus-stealing —
  violates the focused-field guard); page-world script injection
  (unnecessary — the native setter works from the isolated world since
  the DOM node is shared).

## D4. Cross-origin iframes (Greenhouse embeds)

- **Decision**: `content_scripts` with `all_frames: true` — each frame
  gets its own scanner/filler instance filling its own document;
  the service worker routes per-frame via `sender.frameId`; the app's
  ledger keys stay `(doc_token, je_idx)` exactly as 009.
- **Rationale**: a parent frame cannot reach a cross-origin child's DOM;
  per-frame instances are the only correct approach and match the 009
  frame-walk semantics one-to-one.

## D5. Scan cadence in the extension

- **Decision**: per-frame MutationObserver (childList+subtree+attributes)
  debounced 500ms, plus a 2s safety poll, plus an immediate re-scan after
  each applied fill batch. Full descriptor sets are sent each scan; the
  app diffs against the Python ledger (idempotent, same as 009 ticks).
- **Rationale**: observers catch SPA re-renders faster than polling
  alone; the safety poll covers observer blind spots (e.g., value
  changes that mutate no observed attribute); resending full sets keeps
  the extension stateless and re-scan-safe.

## D6. Value kinds and secret handling

- **Decision**: fill items carry `kind: text|select|checkbox|file|secret`.
  `secret` values: sent only for a currently-watched tab whose frame's
  registrable domain matches the credential entry; never stored in
  `chrome.storage`; the shared logging helper structurally drops `value`
  for every fill item; `fill_result` echoes `je_idx` + outcome only.
  Files: one-time tokened `GET /api/bridge/file/<token>` → ArrayBuffer →
  `File` + `DataTransfer` → `input.files` + `change`; refusal →
  `needs_manual`.
- **Rationale**: preserves the constitution's password rules end-to-end
  with the smallest possible secret surface; DataTransfer is the only
  scriptable file-attach path available to content scripts.

## D7. Backend selection and fallback

- **Decision**: `browser_controller` gains `_state.backend`
  (`extension|playwright`) chosen at `start_queue()` — extension iff a
  paired socket has a <10s-old heartbeat; overridable via
  `AUTOFILL_BACKEND=auto|extension|playwright` (default auto). Sticky
  per queue. Mid-queue disconnect → existing `interrupted` semantics;
  Resume offers reconnect-wait or explicit switch. Status payload gains
  `backend` + `extension {connected, version, last_seen}`.
- **Rationale**: never a silent mid-job backend swap (different browser
  sessions have different state); reuses the 007/009 interrupted flow
  the UI already renders.

## D8. AI drafting (qa)

- **Decision**: new `engine/qa.py`; prompt = question text + job
  title/company/description excerpt + structured grounding (resume
  sections, profile facts, nearest saved answers); output constrained to
  concise 60–120 words (shorter for small maxlength), grammar-constrained
  JSON on the local tier; explicit refusal token when grounding is thin →
  field left untouched, `needs_manual`. AI-eligible tags are an
  allowlist (free-text question tags only); work-auth/visa/EEO tags are
  structurally excluded. Tier: existing scoring_tier()/_chat fall-through
  (offline-first default).
- **Rationale**: allowlist (not blocklist) makes the sensitive-question
  exclusion fail-closed (FR-014/SC-005); refusal-over-fabrication
  directly addresses the top competitor complaint (wrong/templated
  answers) and FR-011's no-invented-facts rule.

## D9. Answer-bank provenance + auto-save on submission

- **Decision**: answers gain provenance
  (`user | ai_draft | confirmed | auto_saved`) and a draft lifecycle;
  saved-answer matching always runs before qa. On detected submission
  (content script observes `submit` events + confirmation URL/DOM
  heuristics → `page_event`), the app raises a user-confirmable
  next-action; confirming marks the application applied AND saves final
  on-page texts of any AI-drafted fields as `auto_saved` answers
  (clarify Q2), editable in Profile.
- **Rationale**: submission is the user's real acceptance signal;
  auto-save grows the bank with zero extra clicks while staying
  user-confirmable (never silent — FR-020).

## D10. UI overhaul approach

- **Decision**: one design-token layer (CSS custom properties for type
  scale, color roles, spacing, radii; light/dark via existing theme
  mechanism) applied across all templates; surface rework order: home
  dashboard → Apply Assist screen → tracker board → global sweep.
  frontend-design skill governs the identity pass at implementation.
- **Rationale**: tokens-first prevents per-page drift and keeps the
  identity consistent (SC-007); htmx + Jinja stack unchanged (no SPA
  rewrite — YAGNI).

## D11. Distribution + signing (researched, user-decided)

- **Decision**: unpacked developer-mode extension bundled in the
  installers, stamped into the data dir; in-app guided walkthrough page.
  No Web Store ($5 fee declined), no code signing (SignPath free would
  show "SignPath Foundation" as publisher; real "ABHINAV B" needs Azure
  Trusted Signing ~$9.99/mo — both declined for now; documented in the
  install guide).
- **Rationale**: strict $0; the dev-mode nag is accepted by the user;
  the app-owns-the-folder pairing depends on unpacked distribution
  anyway (a store build would switch pairing to the recovery-code path —
  future option, not now).

## D12. Extension test harness

- **Decision**: pytest + Playwright `launch_persistent_context` with
  `--disable-extensions-except/--load-extension` loading a temp copy of
  `extension/` with a test-stamped pairing.json, against the real app on
  an ephemeral port, driving the existing fixture ATS pages + four new
  fixtures (react_controlled, react_select_dropdown, file_upload_input,
  essay_question). SW kill/reconnect covered via context service-worker
  handles. Marked `-m browser`, run explicitly in CI like the 009 suite.
- **Rationale**: tests the REAL extension end-to-end at $0, reusing the
  proven 009 fixture/echo-mirror pattern and CI wiring.
