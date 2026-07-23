# Feature 010 "The Copilot Release" (v1.0.0): Chrome Extension Fill Engine + AI Question Answering + Full UI Overhaul

## Context

v0.9.0 proved the live fill engine works on real postings (Greenhouse/Lever/
Ashby fills verified live), but it drives a **separate Playwright-controlled
Edge window** — a clean-profile browser where the user is logged into
nothing, bot-detection is riskier, and the experience feels bolted-on. The
user's ask, after using v0.9.0: build a **Chrome extension** connected to
the app so filling happens in *their* Chrome (their logged-in sessions),
add **AI answering for open-ended application questions**, improve the
Apply Assist UI and the whole app's look, and reach feature parity with
Sprout / Scale.jobs / JobRight / Simplify — as a free, one-stop tool.
One release (user chose mega-release over staging): **v1.0.0**.

### Competitive research takeaways (2026-07-23, three research passes)

| Product | Mechanism | Pricing | What we take |
|---|---|---|---|
| Simplify | Extension autofill, 100+ ATSs, never auto-submits; profile = answer bank; AI essay answers (paid) | Autofill free; + $39.99/mo | The model to beat: our whole "+" tier (AI answers, tailored resumes, cover letters) is free & local |
| JobRight | Extension autofill + paid cloud "AI Agent" that submits; match scores; H1B filter | ~2 free credits/day; $39.99/mo | Match-score-forward home UI; we already have sponsorship intel (007) |
| Sprout | Cloud-side auto-apply, no review of AI content | $19.99–79.99/mo | Anti-goal: no unreviewable AI submissions |
| Scale.jobs | Human VAs submit for you | $199–1,099 credits | Anti-goal: nothing human/cloud; proof-style per-app reporting is nice (we keep honest fill reports) |

Common complaints we must avoid: filling wrong/templated AI answers,
breaking on Workday's later steps, opaque "what did it actually submit",
ghost jobs at high scores. Our angles: $0 forever, local/private AI,
never auto-submit, honest per-field reports, sponsorship intelligence.

### User-locked decisions (AskUserQuestion, 2026-07-23)

- **Extension becomes the primary** fill path (user's real Chrome, logged-in
  sessions). Playwright engine stays as fallback when extension not connected.
- **AI answers: draft → fill → flag for review** (visible "AI draft — review
  before submitting" marking; user always clicks submit). Visa/sponsorship/EEO
  stays confirm-gated (constitution).
- **One mega-release** v1.0.0 (not staged).
- **UI overhaul: all four surfaces** — Apply Assist flow, dashboard/home
  redesign, tracker board polish, overall visual identity.
- **Extension distributed unpacked** (developer mode, $0; no Web Store).
- **Code signing: SKIPPED** for now (free SignPath would show "SignPath
  Foundation" not "ABHINAV B"; real name needs Azure ~$9.99/mo — deferred;
  keep $0). Installer keeps current behavior; document SmartScreen click-through.

## Architecture

### WS-A: Chrome extension (MV3) — the thin DOM arm

Principle: **the app stays the brain, the extension is hands**. All
classification (fields.py/adapters.py), value resolution (profile, answer
bank, credential vault), AI drafting, queue state, and tracking remain in
Python. The extension serializes DOM fields → sends descriptors to the app
→ receives fill instructions → fills → reports outcomes. Zero logic
duplication in JS.

- Transport: **WebSocket to 127.0.0.1** from the MV3 service worker
  (Chrome ≥116 keeps SW alive on WS activity; ~25s ping). Content scripts
  never touch localhost directly (Chrome 142 Local Network Access).
- `all_frames: true` content scripts fill cross-origin Greenhouse iframes;
  React controlled inputs via native value setter + bubbling `input` event.
- Fill invariants preserved verbatim: never click, non-empty sacred,
  focused-field guard, passwords fill-and-forget (never persisted/logged
  extension-side), per-(doc,idx) handled ledger semantics.
- Slide-in progress panel on the page (closed shadow DOM, top frame only):
  live fill counts aggregated across frames, per-field outcome chips,
  AI-draft flags, "you click submit" reminder. Zero buttons that touch the
  page; `filler.js` contains no `.click()` call (engine invariant mirrored).
  Extension badge + app UI both show Connected/Disconnected.

#### WS-A detail (from the architecture design pass)

**Pairing & port discovery — the app owns the extension folder.** The app
materializes/updates `<data_dir>/extension/` (user loads it unpacked once);
at every launch, after binding its dynamic port, the app stamps
`extension/pairing.json` = `{port, secret, app_id}`. Unpacked extensions
re-read packaged files from disk on every `fetch(chrome.runtime.getURL(...))`
— so the service worker picks up new port/secret each connect with no
reload and no pairing UX. Auth: 32-byte secret in first WS frame
(`hello`); wrong secret → close 4401. Reconnect: 1s→30s backoff +
`chrome.alarms` watchdog + 20s ping keepalive (`minimum_chrome_version:
116`). Recovery-only manual code entry in the popup.

**Protocol** (versioned JSON envelope over `ws://127.0.0.1:<port>/ws/ext`):
ext→app `hello / fields {tab, frame, doc, descriptors} / fill_result /
page_event / pong`; app→ext `hello_ok / open_tab / close_tab / watch_start /
watch_stop / fill {items:[{je_idx, kind: text|select|checkbox|file|secret,
value, option_label?, file_url?}]} / ping`. Descriptor shape is
byte-identical to `SERIALIZE_JS` output so `fields.py`/`adapters.py`
classify unchanged. Stamps (`data-je-idx`, doc token) stored as DOM
attributes so they survive content-script reloads. Ticking: per-frame
MutationObserver (500ms debounce) + 2s safety poll + post-fill re-scan;
the handled ledger stays in Python exactly as today.

**Secrets fill-and-forget:** keyring → Python → loopback WS → SW → content
script → DOM, `kind:"secret"`; sent only for a watched tab whose frame
domain matches the credential; never in `chrome.storage`, never logged
(logging helper drops values), never echoed in `fill_result`, masked
`•••` in reports as today. File uploads: one-time tokened
`GET /api/bridge/file/<token>` → ArrayBuffer → `DataTransfer` →
`input.files` + change event; failures report `needs_manual`.

**One facade, two backends:** `browser_controller.py` queue state machine,
value resolution, pending slot, and report shapes stay byte-compatible for
the web UI. Extract transport-agnostic per-descriptor decision logic from
`watcher._process_field` into `engine/autofill/field_core.py` (single
source of fill rules for both backends). New
`engine/autofill/ext_backend.py` (session + command translation; send-
callable injected by the web layer — engine never imports web),
`engine/autofill/ext_protocol.py` (pydantic schemas),
`web/routes_bridge.py` (`WebSocket /ws/ext` + `GET /api/bridge/info`),
`scripts/stamp_extension.py` called from `desktop.py` after port bind.
`start_queue()` picks the backend: extension iff paired socket live
(heartbeat <10s), else Playwright; sticky per queue; setting
`AUTOFILL_BACKEND=auto|extension|playwright`. Disconnect mid-queue →
existing `interrupted` semantics; Resume offers "wait for Chrome" or
explicit switch (never silent mid-job backend swap). Status payload gains
`extension: {connected, version, last_seen}` + `backend`.

**Extension layout** (repo `extension/`, mirrored to data dir):
`manifest.json` (MV3; storage/tabs/alarms; host_permissions
`http://127.0.0.1/*`; content_scripts `<all_urls>` `all_frames:true`),
`background/{service-worker,socket,protocol,tabs,badge}.js`,
`content/{main,scanner,filler,overlay}.js|css`, `popup/`.

**MV3 risks:** SW eviction → stateless SW, durable state in Python, DOM
stamps + ledger make re-scans idempotent; extension reload mid-queue →
orphan scripts detect port invalidation and remove overlay; multiple
profiles → single active socket, newer hello supersedes (4409);
descriptor drift → protocol version gate in hello, app refuses mismatched
major and prompts extension reload.

### WS-B: AI question answering (draft → fill → flag)

- New `engine/qa.py` (name TBD): given a field's question text + job context
  (title/company/description) + grounding data (resume text, sections,
  profile, existing answer-bank answers), generate an answer via the
  existing tier system (offline-first PREFER_LOCAL_LLM, cloud fall-through) —
  reusing `matcher._chat` patterns and grammar-constrained local JSON.
- Fill flow: unmatched free-text fields (currently `no_match`) become
  `ai_draft` candidates → answer generated → filled → flagged in the
  progress panel and the fill report as "AI draft — review before submit".
- Confirmed/edited drafts saved to the answer bank (existing pending-answer
  flow generalizes); next time it's a bank hit, not an AI call.
- Sensitive-question gate unchanged: work-auth/visa/EEO questions are never
  AI-answered; they use the existing confirm-before-use flow.
- Practice page gains a free-text question to exercise the whole loop.

### WS-C: UI overhaul (all four surfaces; use frontend-design skill)

1. **Apply Assist flow**: extension-era screen — connection status card,
   queue with per-job live activity (reuse 009 activity feed), AI-draft
   review list, mode indicator (extension/fallback window).
2. **Dashboard/home**: top matches with score visuals, application stats,
   next-actions (follow-ups due, drafts to review), what's-new.
3. **Tracker board**: kanban polish — extension-detected submissions
   auto-advance status (detect form POST/URL change heuristics, still
   user-confirmable), notes, follow-up nudges.
4. **Visual identity**: typography/color/spacing pass across all templates
   (single CSS variables source, light/dark), professional non-templated look.

### WS-D: packaging + docs

- Installer bundles `extension/` folder + a "Connect your Chrome" first-run
  guide page (chrome://extensions → Developer mode → Load unpacked → path
  shown, copyable). No signing changes. Docs: README, USER_MANUAL,
  USER_GUIDE, quickstart livegate updated for extension path.

## Constitution guardrails (unchanged, enforced in tests)

Never click apply/submit/login · never auto-submit · $0 · engine/ never
imports web/ · visa/EEO confirm-gated, never AI-answered · passwords never
in SQLite, masked at record time, never persisted extension-side.

## Verification

- Unit: `ext_protocol` pydantic round-trips + malformed/oversized rejection;
  `field_core` rules shared across both backends; `ext_backend` transitions
  with a fake sender; secret-redaction assertions (no secret in reports/
  logs/snapshots); qa grounding/prompt bounds.
- **Extension integration layer**: Playwright `launch_persistent_context`
  with `--load-extension` loads the REAL extension (test-stamped
  pairing.json) against the real app on an ephemeral port, driving the
  existing fixture ATS pages (delayed render, iframe host, brackets,
  apply-reveal, typing race) + new fixtures: `react_controlled.html`
  (native-setter proof), `react_select_dropdown.html` (needs_manual, never
  click), `file_upload_input.html` (DataTransfer), free-text-question page
  for AI drafts; plus SW-kill mid-queue + reconnect; `-m browser` marked.
- Offline gate extended: AI answer generation on the real local model.
- Frozen smoke: extension assets present in build; bridge endpoint answers.
- Live gate: scripted (real Greenhouse/Lever/Ashby fills via extension in
  headed Chrome) + manual checklist (logged-in Workday flow, AI draft
  review UX).
- Full pytest ×2 + browser suite green before ship; ship ritual per memory
  (merge → mirror → tag v1.0.0 → verify BOTH installers).

## Process

Feature branch `010-copilot-release` → design doc committed → speckit chain
(specify → clarify → plan → checklist → tasks → analyze) → hybrid
speckit+superpowers TDD implementation → docs → frozen smoke → live gate →
ship v1.0.0.

## Non-goals

Auto-submit/cloud-apply (constitutional) · humans-in-the-loop · mobile app ·
Web Store publishing · code signing · paid anything.
