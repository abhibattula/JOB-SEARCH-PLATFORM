# Feature 015 — "The Pairing Release" (v1.5.0): Apply Assist companion rebuild + AI runtime hardening

**Date:** 2026-07-25 · **Status:** approved (Approach A; decisions D1–D3 locked by user)
**Driver:** Apply Assist has never completed a real end-to-end fill on the user's
machine in any version, and on 2026-07-25 00:47 the installed app hard-crashed.

## 1. Evidence (root-cause investigation, 2026-07-25)

All verified on the user's machine — not hypotheses:

1. **Hard crash:** Windows Error Reporting APPCRASH — `JobEngine.exe`, faulting
   module `_internal\llama_cpp\lib\ggml-cpu.dll`, exception `0xc0000005`
   (access violation), 2026-07-25 00:47:05. A native fault in the bundled LLM
   runtime; unhandled by design (no Python frame can catch it).
2. **Enabling defect:** local inference is unserialized. `local_llm.chat()` and
   `semantic.embed()` hold no lock during inference (locks guard loading only);
   drafting, answer suggestions, refresh scoring, tailoring, and profile import
   can run the same non-thread-safe `Llama` instance from different threads.
3. **Chronic freezes:** `browser_controller._value_for_tag` calls
   `answer_bank.suggest()` — minutes of CPU inference — **while holding
   `bc._lock`** (browser_controller.py:393). The 3s status poll needs the same
   lock → UI/app appears dead. Present since the 005 era; this is why every
   version "felt crashed".
4. **Pairing has never succeeded:** no unpacked companion exists in Edge or any
   of 24 Chrome profiles (browser Preferences scanned). app.log shows
   `could not stamp companion extension` — `stamp_extension.py:44` imports
   `ext_protocol` → pydantic → `ModuleNotFoundError: pydantic_core._pydantic_core`
   in the frozen app (mid-upgrade file replacement). Stamp failure is silent in
   the UI; the popup's "Fill this page" no-ops when unconnected; the queue
   starts in the assistant window without saying so.
5. **Browser truth vs intent:** Windows `UserChoice` ProgId is `MSEdgeHTM` for
   http+https (Edge IS the OS default); Chrome appears only in the legacy
   `StartMenuInternet` key. The app reports/obeys the OS truthfully but offers
   no preference override and no mismatch surfacing — and the Playwright
   assistant window is a separate, signed-out profile (alienating even when it
   works).
6. **Session-path bugs:** `POST /api/autofill/answers/confirm` 500s with
   `sqlite3.IntegrityError: FOREIGN KEY` for practice (-1) / ad-hoc (-2)
   sentinel job ids (routes_autofill.py:189 — the drafts route guards this,
   confirm does not). Updater: an empty (0-byte) download reaches SHA-256
   verification (`got e3b0c442…` = hash of empty), then cleanup `unlink` dies
   on `WinError 32`; `updates/` hoards 4 full installers (~6 GB). Extension
   manifest version stuck at 1.2.0.

**Why every version failed:** the human pairing path (install → stamp → connect
→ verify) has zero test coverage and zero observability — the 27 real-browser
tests pair programmatically, proving the fill core works *when paired*. Every
failure mode around it is silent, and the freeze defect poisoned even the
assistant-window fallback.

## 2. Verdict

Rebuild the **pairing/connection/diagnostics layer** and harden the **AI
runtime**; **keep the proven fill core** (field_core, scanner/filler, adapters,
click guards — validated end-to-end by the real-browser suite). A from-scratch
rewrite of the fill engine would discard the only proven subsystem and re-risk
011's ATS coverage.

## 3. Locked decisions

- **D1 (AI isolation):** serialize ALL local inference behind a single owner
  now (locks + one worker thread); run a time-boxed **subprocess-isolation
  spike** (multiprocessing, stdlib) with explicit go/no-go — GO ships child-
  process inference in 015 (an AI crash can never close the app); NO-GO ships
  the serialized owner and records findings. The release is never blocked on
  the spike.
- **D2 (fallback UX):** when the companion isn't connected at queue start,
  **proceed + loud notice** — the queue runs in the assistant window with a
  prominent, persistent "Companion not connected — filling in an assistant
  window (not signed in). Connect your browser →" state. Never blocks.
- **D3 (browser preference):** new `PREFERRED_BROWSER` setting, values
  `chrome | msedge | auto`, **default `chrome`**. A live companion always wins
  regardless of preference. OS-default vs preference mismatch is always
  surfaced with a one-click jump to Windows default-apps settings.

## 4. Workstreams

### WS-R — Reliability floor (fix the crashers first)

- **`engine/inference.py` (NEW):** one daemon owner thread + command queue owns
  every local-model call. API: `run_chat(messages, json_mode, timeout_s)` /
  `run_embed(text, timeout_s)`. `local_llm.chat` and `semantic.embed` become
  thin wrappers routing through it — all existing call sites get serialization
  for free. Reentrancy assertion + a test hook exposing max observed
  concurrency. Timeouts raise; callers already fail soft.
- **Never infer under `bc._lock`:** park the pending question immediately
  (`drafted_answer=None`, "drafting…" state), generate via the owner queue,
  update the pending slot on completion (brief lock). Status polls stay fast.
- **Subprocess spike (D1):** child process hosts both models behind the same
  owner API; parent supervises/restarts; PyInstaller `freeze_support` +
  spawn. GO criteria: frozen smoke passes on Windows AND the mac CI job.
- **`confirm_answer` FK guard:** record the application-answer snapshot only
  for real job ids (>0), mirroring the drafts route.
- **Updater hardening:** reject empty/short downloads before hashing; retry
  unlink then defer cleanup to next launch; prune `updates/` to the newest
  installer after a successful verify.
- **Unclean-exit detection:** `running.marker` written at start, removed on
  clean exit; present at startup → one-time "the app closed unexpectedly last
  time" banner linking the Doctor (catches native crashes that leave no
  Python crash.marker).
- **Manifest version sync:** `stamp()` rewrites the staged manifest's
  `version` to `APP_VERSION` so the companion reports its true pairing
  generation.

### WS-P — Pairing rebuilt (the heart)

- **De-risk stamping:** move `PROTOCOL_V`/`APP_ID` to a dependency-free
  `engine/autofill/bridge_const.py` (ext_protocol re-exports). `stamp()`
  imports stdlib + `db.get_bridge_secret` + bridge_const ONLY (static
  AST-import guard test). Order of operations: attempt file copy, ALWAYS
  attempt pairing.json write, then **read back and verify** (parse, port,
  secret). Stamp outcome `{ok, error, at, port}` is recorded and **surfaced as
  a UI banner** on the autofill + companion pages when failed.
- **`/api/companion/doctor` (NEW, web layer):** one JSON snapshot of the whole
  chain — stamp status; pairing file present/fresh-this-launch/port/protocol;
  current port; companion connected/version/browser (from hello UA)/heartbeat
  age; bridge close-code counters (4401/4426 + last time); OS default browser;
  preference. Powers the wizard, the Doctor section in diagnostics, and tests.
- **Connect wizard (companion.html overhaul):** live per-step verification
  driven by the doctor (stamped ✓ → extension knocking/connected ✓ → browser
  name + version ✓), close-code-mapped troubleshooting ("4401: restart app or
  reload the extension; wrong folder?", "4426: reload the extension"), copy-path
  retained, explicit "not connected → fills use the assistant window" framing.
- **Popup diagnostics (extension):** the service worker records the last
  attempt outcome (`no-pairing | identity-failed | ws-error | closed(code) |
  connected`, port, timestamp); the popup renders it in human terms with a
  "Connect now" retry — the Fill button is never a silent dead end: when
  disconnected it explains why instead of no-op.
- **Queue-start transparency (D2):** the autofill page always states the
  active path — "Filling in **your Chrome** (companion)" vs "Filling in an
  **assistant window — Edge (not signed in)**" — with the connect link when
  falling back.

### WS-B — Browser intent (kill the Edge surprise)

- `PREFERRED_BROWSER` setting (default `chrome`, D3) + Settings UI control.
- `default_browser.effective_channel_order()`: preference first (`auto` = OS
  default first), then remaining automatable channels; assistant window and
  `/api/open` both honor it (`/api/open`: launch the preferred browser's exe
  via its App Paths registry entry; fall back to `os.startfile` when absent
  or `auto`).
- Mismatch surfacing everywhere it matters: "Windows default: Edge ·
  Preference: Chrome · Companion: Chrome ✓" + a [Fix Windows default] action
  (`ms-settings:defaultapps`, Windows only).
- Companion-wins rule unchanged and displayed.

### WS-V — Verification that matches reality

- **Concurrency guards:** stub-model hammer (8 threads × chat/embed) asserts
  max observed concurrency == 1; timeout path covered.
- **Freeze regression:** with a slow stub draft in flight, `/api/autofill/
  status` answers fast (bounded) — proves no inference under the facade lock.
- **Human-path E2E (browser suite):** fresh temp data dir → REAL `stamp()` →
  load the stamped dest folder into REAL Edge **and** REAL Chrome
  (`--load-extension`) → real uvicorn → assert doctor shows connected → one
  fixture fill through the full chain.
- **Frozen smoke additions:** pairing.json mtime ≥ process start (stamp ran
  THIS launch), pairing port == port.txt, `/api/bridge/info` OK, doctor
  `stamp.ok` true — this gate would have caught the pydantic_core failure.
- **Static guards:** stamp module import allowlist (AST); stamped manifest
  version == APP_VERSION.
- **Regressions:** confirm_answer with sentinel ids → 200; updater empty
  download → clean surfaced error, no thread crash; installer pruning.
- Full battery ×2 + browser + slow markers + ship ritual (both installers).

## 5. Constitution guardrails

Same stack (Jinja + HTMX + token CSS + vanilla JS; no framework, no Node), $0
(multiprocessing is stdlib; extension stays unpacked), offline-first, engine
never imports web (doctor lives in the web layer over engine seams), Apply
Assist never clicks submit/login (fill core untouched), secrets remain
fill-and-forget. Localhost bridge threat model unchanged from 010 (documented).

## 6. Non-goals

Fill-core/ATS rewrite · store-published extension · code signing · Firefox ·
changing the localhost hello secret model · new job sources.

## 7. Success criteria

1. An induced AI fault cannot close the app (subprocess GO) — or, at minimum,
   an 8-thread inference hammer shows serialized execution (NO-GO floor).
2. Status endpoint stays responsive (bounded latency) while a draft generates.
3. Stamp failure is visibly surfaced within one launch and gated by frozen smoke.
4. Human-path E2E green in BOTH real Edge and real Chrome.
5. The active fill path (companion vs assistant window + channel) is always
   stated on the autofill page.
6. confirm_answer sentinel-id 200; updater failure paths clean; ≤1 retained
   old installer.
7. OS-default vs preference mismatch is visibly surfaced with the one-click fix.

## 8. Process

Branch `015-pairing` → speckit chain (specify → clarify → plan → checklist →
tasks → analyze, fix findings) → hybrid TDD implementation → docs
(USER_MANUAL §19: connect + troubleshooting rewrite; README) → full battery +
frozen smoke → ship v1.5.0 (merge → main, mirror, tag, verify BOTH installers).

## 9. Risks

- PyInstaller × multiprocessing (spike-gated; NO-GO path defined).
- Real-Chrome `--load-extension` variance vs Edge (existing harness precedent;
  full-browser headless per the 010 lesson).
- Port 8000 collisions with dev runs (pairing re-read + doctor visibility +
  smoke port assertion).
- Mid-upgrade launch races corrupting imports (AppMutex limits it; unclean-exit
  banner + Doctor surface the residue; full fix out of scope, noted).
