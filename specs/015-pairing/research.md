# Research & Decisions — Feature 015 (The Pairing Release)

All decisions are grounded in the 2026-07-25 root-cause investigation
(evidence recorded in `docs/superpowers/specs/2026-07-25-feature-015-design.md`
§1): the WER APPCRASH in `ggml-cpu.dll` (0xc0000005), the `app.log` stamp
failure (`pydantic_core` missing in the frozen build), the empty browser
Preferences scan (companion never actually loaded), the registry ground truth
(`UserChoice=MSEdgeHTM` while the user intends Chrome), and the code reading
(`local_llm.chat`/`semantic.embed` unlocked during inference;
`answer_bank.suggest` called under `bc._lock`).

---

## R1. Inference serialization: single-owner worker, not just locks

**Decision**: New `engine/inference.py`: ONE daemon worker thread + a bounded
`queue.Queue` (maxsize 32) owns every local-model call. Public API
`run_chat(messages, json_mode=False, timeout_s=None)` and
`run_embed(text, timeout_s=None)` submit a request and block on a
`concurrent.futures.Future` up to the time budget. `local_llm.chat()` and
`semantic.embed()` become thin wrappers that submit — every existing call site
gets serialization without edits. Model **loading** also moves onto the worker
(first use), so load and generate can never overlap. Defaults: chat 180 s,
embed 30 s (`JOBS_AI_TIMEOUT_CHAT`/`JOBS_AI_TIMEOUT_EMBED` override). A full
queue or exceeded budget raises `RuntimeError` — the exact failure class every
caller already tolerates (`matcher._chat` falls through/raises to callers that
fail soft; `semantic.embed` catches and returns None; `qa.draft` catches and
returns None). Instrumentation: an internal in-flight counter asserts
single-flight; a test hook exposes the max observed concurrency.

**Rationale**: A bare lock inside `chat()`/`embed()` would fix the race but
(a) lets minute-long inferences stack up unbounded caller threads (the anyio
threadpool has ~40 threads — the freeze would just move), (b) gives no
timeout point, and (c) leaves no seam for R2's subprocess. A single owner
gives serialization by construction, one place to bound/observe, and an API
boundary the subprocess spike can slot behind unchanged.

**Alternatives considered**: per-model `threading.Lock` around inference
(rejected: unbounded blocking, no seam); asyncio-based queue (rejected: all
callers are sync engine threads); llama-cpp's own server binary (rejected:
new packaged process surface, heavier than needed, complicates $0 bundling).

## R2. Subprocess isolation spike (D1) — design + GO/NO-GO

**Decision**: Time-boxed spike behind the R1 API: a `multiprocessing`
(explicit `spawn`) child hosts BOTH models and serves requests over a
`multiprocessing.connection.Pipe`; the parent's inference worker forwards
submits when `JOBS_AI_SUBPROCESS=1`. Parent supervises: child death →
current request fails cleanly, child restarts lazily, doctor/diagnostics note
"AI runtime restarted". `desktop.py` and `cli.py` gain
`multiprocessing.freeze_support()` as the first main-guard line. **GO** iff
the frozen Windows smoke AND the mac CI job pass with subprocess mode ON —
then it ships enabled by default; **NO-GO** → default stays off, findings
recorded here, release proceeds (worker-thread mode is the supported state).

**Rationale**: only process isolation makes a native AV non-fatal; but
PyInstaller × multiprocessing is exactly the kind of packaging risk that has
bitten this project before (tls_client DLL, jobspy DLL, pydantic_core), so it
must not gate the release.

**Alternatives considered**: SEH/ctypes trapping of access violations
(rejected: not portable, UB after AV); always-on subprocess without a spike
(rejected: packaging risk unbounded); leaving crash risk after serialization
(accepted as NO-GO floor: with the race gone, single-threaded llama AVs are
rare — and the unclean-exit banner in R9 at least makes them visible).

**SPIKE OUTCOME (2026-07-25, T007/T024):** the isolation WORKS —
`tests/test_inference.py::TestSubprocessSpike` proves (stub-level, spawn
children, ~2.7 s) that with `JOBS_AI_SUBPROCESS=1` the child serves requests,
a killed child fails at most the in-flight request cleanly and the supervisor
restarts it, and a HUNG inference is terminated on the caller's budget (a
capability thread mode cannot have). `freeze_support()` is wired into both
frozen entrypoints. **Decision: available-but-default-OFF for v1.5.0** — the
env flips it on; the default flip waits for a release whose full battery and
frozen gates run WITH the mode on across both OSes (the mac side of the GO
criteria only gets exercised by the release CI at tag time, which is too late
to flip a default responsibly in the same release). The serialized owner is
the supported v1.5.0 state; flipping the default is a candidate for 015's
follow-up.

## R3. Pending suggestions must not generate under `bc._lock`

**Decision**: `browser_controller._value_for_tag` parks the pending question
IMMEDIATELY (`drafted_answer=None`, `drafting=True`, plus a nonce) and
returns; the suggestion is generated via the R1 owner on a background path;
its completion callback re-acquires `_lock`, verifies the nonce still matches
the parked pending, and fills in `drafted_answer`/`drafting=False`. The
Apply Assist pending panel renders "drafting a suggestion…" while
`drafting` is true; the confirm flow already tolerates an empty draft.

**Rationale**: the freeze is the lock-held inference — the 3 s status poll
(`queue_snapshot`) blocks behind a minutes-long `answer_bank.suggest`. Parking
first keeps every status/read path lock-cheap, and the nonce prevents a stale
draft landing on a different question (job advanced/stopped meanwhile).

**Alternatives considered**: dropping suggestions entirely (rejected: real
value); generating before parking without the lock (rejected: still delays the
pause surfacing by minutes); a second lock just for pending (rejected: still
serializes status behind inference at the seam).

## R4. Stamping must be import-minimal, verified, and observable

**Decision**: New `engine/autofill/bridge_const.py` holds `PROTOCOL_V = 1` and
`APP_ID = "jobengine"` with stdlib-only imports; `ext_protocol.py` imports the
constants FROM it (single source, no drift). `scripts/stamp_extension.py`
imports ONLY: `__future__`, `argparse`, `json`, `shutil`, `sys`, `pathlib`,
`engine.paths`, `engine.db` (sqlite/stdlib), `engine.autofill.bridge_const` —
enforced by an AST import-allowlist test. New stamp order: (1) attempt file
copy — a copy failure with an already-populated destination is recorded but
does NOT abort; (2) ALWAYS write `pairing.json`; (3) read it back and verify
port/secret/protocol; (4) write `stamp_status.json`
`{ok, error, at, port, app_version}` in the data dir. `desktop.py` keeps its
try/except but a failure now lands in `stamp_status.json` either way (the
except path writes it too), and the web layer surfaces it (R5/banner).

**Rationale**: the shipped failure was `stamp → ext_protocol → pydantic →
pydantic_core ImportError` — pairing died for an import the stamp never
needed. Read-back + status file turn every future stamp failure from
log-only into UI-visible and smoke-gatable (R12).

**Alternatives considered**: lazy-importing pydantic inside ext_protocol
(rejected: stamp still coupled to the heaviest optional import in the app);
catching and continuing without a status record (rejected: that IS the
current silent failure).

## R5. One doctor endpoint, close-code counters, browser identity

**Decision**: `GET /api/companion/doctor` (web layer, composes engine seams)
returns: `stamp` (from `stamp_status.json`), `pairing` (`present`, `port`,
`protocol_v`, `fresh` = file mtime ≥ this process's start time), `port`
(`current` from `port.txt`, `match`), `companion` (`connected`, `version`,
`browser`, `last_seen_age_s`), `rejects` (`auth` count, `protocol` count,
last kind/age — incremented via a new `ext_backend.record_reject(kind)`
called where routes_bridge closes 4401/4426), and `browser`
(`os_default_channel`, `preference`, `mismatch`). The Hello message gains an
OPTIONAL `browser` field ("chrome" | "edge" | "") detected in the extension
via the user-agent (`Edg/` marker) — additive, `PROTOCOL_V` stays 1, old
companions remain valid.

**Rationale**: every silent failure found in the investigation becomes one
readable snapshot; the wizard, the autofill banner, the frozen smoke, and the
E2E test all consume the same truth. Counters distinguish "nothing is
knocking" (wrong folder/not installed) from "knocking but rejected"
(stale secret vs version mismatch) — previously indistinguishable.

**Alternatives considered**: scattering fields across existing endpoints
(rejected: the chain is only diagnosable as a whole); bumping PROTOCOL_V for
the browser field (rejected: needless breaking change — optional field with a
default is enough).

## R6. Preferred browser: resolution + launching

**Decision**: settings key `PREFERRED_BROWSER` ∈ {`chrome`, `msedge`, `auto`},
default `chrome` (D3), editable in Settings.
`default_browser.effective_channel_order()` returns the preference first
(`auto` → the existing OS-default-first order), then the remaining automatable
channels — `browser_controller._channel_order()` switches to it. Link opening
moves to `default_browser.open_url(url)`: preference ≠ auto → resolve the
browser exe via Windows App Paths registry
(`...\CurrentVersion\App Paths\chrome.exe|msedge.exe`, HKLM/HKCU) and
`subprocess.Popen([exe, url])`; missing exe or any error → `os.startfile`
fallback (macOS: `open -a` best-effort, then `open`). `/api/open` calls it and
reports `opened_with` so the UI can note substitutions. Companion-wins rule
(FR-018) is untouched — it's upstream in `_choose_backend`.

**Rationale**: the OS default is genuinely Edge on the evidence machine, and
the user's intent is Chrome — intent must be expressible without fighting the
OS (`os.startfile` can only ever follow `UserChoice`). App Paths is the
canonical, install-location-independent way to find browser exes.

**Alternatives considered**: writing `UserChoice` ourselves (rejected:
protected by hash on Win10+, hostile, fragile); telling the user to fix
Windows and keeping `os.startfile` only (rejected: Windows resets defaults;
the mismatch line + deep link still encourage the OS-level fix — R7).

## R7. Fill-path disclosure + mismatch surfacing (D2/FR-012/013/019)

**Decision**: `queue_snapshot()`/`/api/autofill/status` gain the companion's
`browser`; `autofill_status.html` renders a persistent path banner:
companion → "Filling in your Chrome (companion v1.5.0)"; assistant window →
warning-styled "Assistant window — Edge (not signed in). Connect your browser
→" (shown from queue start, not only after launch). The mismatch line
("Windows default: Edge · Preference: Chrome") renders on the autofill and
connect pages when they differ; on Windows a button POSTs
`/api/os/default-apps` → `os.startfile("ms-settings:defaultapps")`.
`/api/autofill/queue`'s response adds the chosen `backend` (additive).

**Rationale**: D2 chose "proceed + loud notice"; the banner is the loud
notice, and it doubles as the truthful path indicator (FR-013) in the happy
case. A deep link beats prose instructions for actually fixing the OS
default.

**Alternatives considered**: modal confirm on fallback (rejected by D2);
auto-selecting the assistant channel to match the companion's browser
(out of scope — companion connected means assistant window isn't used).

## R8. Popup diagnostics: no dead controls

**Decision**: `socket.js` records `lastAttempt = {stage, port, code?, at}` at
every transition (`no-pairing`, `identity-failed`, `ws-error`,
`closed:<code>`, `connected`), mirrored to `chrome.storage.session` so the
popup can read it even right after a worker wake. `service-worker.js`
`status?` reply includes it; a new `connect!` message triggers an immediate
`connect()`. `popup.js` maps states to plain language (4401 → "the app
rejected the pairing — restart the app, then Retry; if it persists, re-load
the folder shown in the app", 4426 → "companion is older than the app —
click ↻ reload on the extensions page") and always offers Retry; clicking
"Fill this page" while disconnected shows the reason inline instead of
closing silently.

**Rationale**: the investigation's most user-hostile moment was a popup whose
button did nothing. Every disconnected state already exists in socket.js —
they just aren't recorded or shown.

**Alternatives considered**: full options page (rejected: popup suffices);
logging to console only (rejected: that's the status quo).

## R9. Unclean-exit detection

**Decision**: tiny `engine/lifecycle.py`: `mark_running()` writes
`running.marker` at startup, `clear_running()` removes it on clean shutdown
(both webview and Ctrl+C paths in `desktop.py`); `was_unclean()` reports a
leftover marker. On detection the app stores `UNCLEAN_EXIT_AT` (settings) and
`base.html` shows a one-time dismissible banner (server-side inline, the 014
CLS-safe pattern) linking diagnostics; dismissing clears the key.

**Rationale**: a native AV leaves no Python traceback and no crash.marker —
the app currently just vanishes. The marker file is the cheapest honest
signal and gives the R2 spike its user-visible story.

**Alternatives considered**: parsing WER via `Get-WinEvent` at startup
(rejected: slow, permission-y, Windows-only); watchdog process (rejected:
overkill).

## R10. `confirm_answer` sentinel guard

**Decision**: record the per-application snapshot only when
`current["job_id"] > 0` — exactly the guard `list_drafts` already uses two
routes below. The answer-bank save (reusable answer) still always happens;
`resolve_pending` still runs. Regression test: confirm during a
practice/ad-hoc session → 200, bank row created, no `application_answers`
row.

**Rationale**: evidenced 500 (`FOREIGN KEY constraint failed` — sentinel ids
-1/-2 have no `jobs` row). Skipping the snapshot for non-tracked sessions
matches the schema's intent; a NULL-job snapshot would record history for
nothing the tracker can show.

**Alternatives considered**: allowing NULL `job_id` in `application_answers`
(rejected: schema migration for no user value).

## R11. Updater hardening

**Decision**: in `updates._run_download`: (1) after download, reject
`size < 10 MB` with "download incomplete (N bytes)" BEFORE hashing (real
installers are ~1.5 GB; the evidenced failure hashed an empty file into a
baffling message); (2) failure cleanup: `unlink` retried 3× (0.5 s apart),
then the path is appended to `updates/cleanup.json` and deleted on a later
launch (`updates.startup_check` head) — a locked file NEVER crashes the
thread; (3) after a successful download+verify (and on startup cleanup),
prune `updates/` to keep at most the newest previous installer besides the
current one (the evidence machine held 4 × 1.5 GB).

**Rationale**: both failure modes are in `app.log`; the hoard is on disk.

**Alternatives considered**: streaming-hash during download (fine but doesn't
fix any evidenced failure; not in scope); deleting all old installers
(rejected: keep one for manual rollback).

## R12. Verification that matches reality

**Decision**: (a) NEW `tests/integration/test_pairing_e2e.py` (browser
marker): fresh `JOBS_DATA_DIR` → real uvicorn on an ephemeral port → REAL
`stamp_extension.stamp(port)` → `launch_persistent_context` with
`--load-extension` of the STAMPED data-dir folder — once with
`channel="msedge"`, once with `channel="chrome"` (skip-if-unavailable, same
pattern as the existing suite) → poll `/api/companion/doctor` until
`companion.connected` with the right `browser` → run one fixture fill through
the full chain. (b) `packaging/smoke_test.py` additions: `pairing.json`
exists with mtime ≥ app launch, its port == `port.txt`, `/api/bridge/info`
OK, doctor `stamp.ok` true. (c) Unit/static: R1 hammer + timeout tests (stub
model), R3 status-responsiveness test (slow stub draft), R4 AST allowlist +
read-back tests, R5 doctor freshness/port logic, R6 order/open_url fallback
tests, R10/R11 regressions.

**Rationale**: the human pairing path was the ONE untested path — and it is
precisely where every version failed. The frozen additions make the shipped
failure class (silent stamp death) un-shippable.

**Alternatives considered**: mocking the stamp in E2E (rejected: the stamp IS
the thing that broke); testing only Edge (rejected: the user's target is
Chrome — SC-004 demands both).

## R13. Companion version tracks the app

**Decision**: `stamp()` rewrites the STAGED `manifest.json`'s `"version"` to
`engine.APP_VERSION` (the repo manifest gets a matching bump at release).
The wizard/status then show a meaningful "companion v1.5.0", and a
version-skew between a loaded companion and the app becomes visible in the
doctor.

**Rationale**: the shipped manifest said 1.2.0 while the app was 1.4.0 —
harmless at protocol level but it makes "which companion is loaded?"
unanswerable during support.

**Alternatives considered**: leaving the manifest static (rejected: free
observability); encoding protocol_v in the manifest version (rejected:
conflates two axes).
