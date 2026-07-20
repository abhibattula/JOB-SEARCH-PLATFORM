# Phase 0 Research: Apply Assist

## 1. Local LLM: runtime and model choice

**Decision**: `llama-cpp-python` (in-process binding, `Llama.create_chat_completion`)
running `Qwen2.5-1.5B-Instruct`, GGUF, Q4_K_M quantization (~1.0-1.1GB).

**Rationale**: Apache 2.0 licensed — confirmed redistributable/bundleable
with no attribution/acceptable-use conditions to manage. In-process binding
avoids a second localhost port, a subprocess to supervise, and any
interaction with `desktop.py`'s existing single-process port-discovery
mechanism (`port.txt`). 1.5B parameters at Q4_K_M is small enough to run
acceptably on typical CPU-only consumer hardware for short-form structured
tasks (score justification, drafted Q&A answers, tailored bullets) — not a
general chat assistant, so the smaller model's ceiling is adequate.

**Alternatives considered**:
- Any Llama-family model — rejected: Meta's community license carries
  redistribution/attribution/acceptable-use-policy conditions incompatible
  with a friction-free bundled installer.
- Qwen2.5-3B-Instruct — rejected: unlike the 1.5B/7B/14B/32B sizes, the 3B
  checkpoint ships under the non-commercial "Qwen-Research" license, not
  Apache 2.0.
- Phi-3.5-mini (MIT) — viable license-wise, kept as a documented fallback,
  but its useful Q4_K_M quantization is ~2.2-2.4GB, over 2x the footprint of
  Qwen2.5-1.5B for comparable short-form quality — worse fit for the
  installer-size constraint.
- A local HTTP-server-mode runtime (e.g. Ollama as a sidecar) — rejected for
  this phase: the user explicitly chose "bundle a model" over "optional
  Ollama backend" during design; would also add a second process/port to
  manage.

## 2. Integrating the local tier into existing scoring

**Decision**: `matcher._chat` becomes a tier dispatcher. The current
implementation is renamed `_chat_cloud`; a new `_chat_local` delegates to
`engine/local_llm.py::chat()`; `_chat` tries cloud → local → raises (existing
callers already treat a raised/failed `_chat` as "leave unscored," so
`tailor.py` and scoring call sites need zero changes). A new
`matcher.scoring_tier() -> "cloud"|"local"|"basic"` drives
`pipeline.py::_score_new_jobs`'s three-way branch, tagging
`match_json.method` accordingly.

**Rationale**: Reuses the exact seam this codebase already established for
the cloud/basic split in feature 004 (`engine/basic_match.py`) rather than
inventing a parallel path. `db.jobs_needing_score`'s existing basic→cloud
upgrade-path SQL extends naturally to a three-tier upgrade
(basic→local→cloud) with no schema change.

**Alternatives considered**: A separate `local_matcher.py` mirroring
`basic_match.py`'s shape end-to-end (own scoring function, not routed
through `_chat`) — rejected: would duplicate `tailor.py`'s prompt/schema
logic for tailoring and answer-drafting, which also need the local tier.

## 3. Packaging the local LLM (native-dependency risk)

**Decision**: `llama-cpp-python` loads its compiled llama.cpp core via
`ctypes` at a path relative to the installed package — the same
invisible-to-static-analysis shape as `tls_client` (the v0.4.0 incident,
`specs/004-get-hired/patch-0.4.1.md`). Mitigate identically: add
`"llama_cpp"` to `hiddenimports`, bundle its native lib via
`collect_dynamic_libs("llama_cpp")` with a build-time assertion the lib was
actually found, and add the model `.gguf` as a `datas` entry with its own
size-sanity assertion. A new `packaging/fetch_model.py` build step downloads
the pinned Hugging Face revision, verifies a hardcoded SHA256, and writes to
a gitignored `models/` directory before `pyinstaller` runs (CI and any local
installer build).

**CI feasibility**: `llama-cpp-python` has no default PyPI prebuilt wheel;
install via the maintainer's CPU-wheel index
(`--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`),
which covers Windows/macOS for the CPython versions this project uses. Both
GitHub-hosted runners carry a working compiler toolchain as a from-source
fallback if that index ever lacks the exact pinned version. Add an early CI
canary (`python -c "import llama_cpp"`) immediately after install so a
broken install fails loud, not as a later "0 results" the way tls_client did.

**Smoke-test extension**: add a diagnostic route
(`GET /api/diagnostics/local-llm-selftest`) that performs a real
`local_llm.chat(...)` call; `packaging/smoke_test.py` asserts HTTP 200 and a
non-empty reply — an actual inference call, not a "process didn't crash"
check — and the fatal-log-pattern list gains llama.cpp-specific failure
substrings.

## 4. Browser automation: engine and delivery

**Decision**: Playwright, not Selenium — built-in auto-waiting/locator API
(less flaky than Selenium's manual `WebDriverWait` patterns), one package
handles browser download, no chromedriver-version-matching maintenance tax.
Launch via `launch_persistent_context(user_data_dir=..., headless=False)` —
always headed, one stable dedicated profile (per the clarify-session
decision: isolated from the user's regular browser, not the user's default
profile). Install only Chromium, not all engines.

**Browser binary distribution**: download on first use of Apply Assist
(`sys.executable -m playwright install chromium`, ~150-280MB), not bundled
in the base installer. Rationale: Apply Assist is opt-in, unlike the local
LLM (used by the core scoring feature nearly every user touches) — this
keeps the *unconditional* installer-size hit to the model alone rather than
model+browser. `PLAYWRIGHT_BROWSERS_PATH` is set to
`paths.data_dir() / "browsers"` (never inside the read-only frozen bundle)
before any Playwright call, following the existing `paths.py` convention.

**Packaging risk**: Playwright's own PyInstaller hook is documented as
unreliable on recent PyInstaller for macOS — don't rely on it. Explicitly
add `collect_data_files("playwright")` to `datas` (its runtime driver
bootstrap files are package data loaded relative to `__file__`, the same
shape as tls_client and llama_cpp above), `"playwright.sync_api"` in
`hiddenimports`, and a build-time assertion the driver file is present. Give
this its own `smoke_test.py` extension (launch Chromium, navigate to
`about:blank`, assert success) so a dropped driver fails loudly.

**Alternatives considered**: Selenium — rejected due to the
chromedriver-version-pairing maintenance burden this project doesn't
currently have and doesn't want to take on. Bundling Chromium in the base
installer — rejected per the installer-size reasoning above.

## 5. Module boundary for browser automation

**Decision**: `engine/autofill/browser_controller.py` owns the Playwright
lifecycle on its own dedicated background thread; FastAPI request threads
never touch Playwright objects directly, only enqueue commands via
`queue.Queue` — mirroring `engine/db.py`'s existing rule that background and
request threads never implicitly share one stateful connection. Exposes
`start_queue(job_ids)`, `current_job()`, `advance()` (user-driven, per the
clarify-session decision — not automatic completion detection),
`stop_queue()`. `web/routes_autofill.py` stays thin, mirroring
`web/routes_api.py`'s role exactly.

## 6. Field detection

**Decision**: `engine/autofill/fields.py` is a pure heuristic classifier
over serialized plain-dict field descriptors (`{tag, type, name, id,
label_text, placeholder, aria_label, autocomplete}`) — never live Playwright
handles — so it's fully unit-testable with literal fixture dicts, no real
browser needed in tests, matching `engine/filters.py`'s classifier style.
`browser_controller.py` is the only module that serializes real DOM fields
(via a JS `querySelectorAll` + attribute-extraction eval) and hands the
result to `fields.classify()`. Legally-sensitive tags — `work_authorization`, `sponsorship_requirement`,
and `eeo_disclosure` (disability/veteran/demographic self-identification
questions, the kind commonly present for compliance/EEO purposes; per
spec.md FR-012 this category is open/extensible, not fixed to two items) —
are matched before generic yes/no catch-alls, to avoid a sponsorship or
EEO-style question being misfiled as a generic boolean. `login_email`/`login_password` require corroborating
context (password `type`, nearby login-page markers) so a saved credential
is never routed into an unrelated field.

**Graceful fallback**: if a page returns few/no confidently-classified
fields, or fails to load (this explicitly includes Workday, which already
blocked this project's job ingestion via Cloudflare in feature 001), the
queue does not fail hard — it opens the tab for manual completion and
advances to the next job (per spec FR-009). No Workday-specific code path
this phase; the same generic classifier runs for every domain.

## 7. Answer bank and per-application record

**Decision**: `answer_bank` table (question_normalized unique, question_raw,
answer, category, source, confirmed_at, updated_at) added to `db.py`'s
existing `CREATE TABLE IF NOT EXISTS` schema block — the same idiom already
used for `companies`/`settings`/`refresh_runs`. Normalize-then-compare like
`db.normalize_company`, plus a `rapidfuzz` fuzzy layer (already a pinned
dependency) for near-duplicate phrasings across ATSes. Per the clarify
session, a second table `application_answers` (job_id, question_raw,
answer_bank_id, answered_at) records exactly which confirmed answer was used
on which specific application, independent of the answer bank's single
current-answer-per-question record.

`engine/autofill/answer_bank.py`: `lookup()` (exact-normalized then fuzzy),
`save()` (only ever called after explicit user confirmation — enforced in
code, not just UI), `suggest()` (reuses the `matcher._chat` tier dispatcher
from research item 2: cloud → local → conservative placeholder). Drafts are
constrained to the user's stored profile facts (new `user_profile` columns:
`authorized_without_sponsorship`, `visa_status`).

## 8. Credential vault

**Decision**: `keyring` fits, but does not reliably auto-detect its backend
inside a frozen PyInstaller app (raises `RuntimeError: No recommended
backend was available`) because its normal entry-point-scanning discovery
path doesn't work under frozen imports. Two load-bearing fixes: (1)
`jobengine.spec` hiddenimports, mirroring the existing conditional
`plyer.platforms.*` pattern —
`keyring.backends.Windows`/`keyring.backends.macOS`; (2)
`engine/credentials.py` explicitly calls `keyring.set_keyring(...)` at
import time, branching on `sys.platform`, rather than relying on
auto-selection.

`engine/credentials.py` API: `save(domain, email, password)`,
`get(domain)`, `delete(domain)`. The password goes to the OS vault only
(`keyring.set_password(domain, email, password)`); a tiny "which email is
saved for which domain" companion record lives in the existing `settings`
table (`cred_email:{domain}`), reusing its established small-KV role rather
than a new table. The password itself never touches SQLite. Settings UI is
write-only, reusing the `settings.py::mask_key` masking idiom for the
displayed email hint — matching how real password managers behave (FR-017).

## Risks flagged (accepted, not blocking)

- **Installer size**: bundling the ~1GB model (+ llama-cpp-python's native
  lib) is an explicit, accepted consequence of "bundle a model" over
  "optional Ollama backend." Expect the installer to grow roughly an order
  of magnitude versus v0.4.2. Chromium is deferred to first-use specifically
  to avoid compounding this.
- **CI feasibility**: two new native-dependency categories (llama-cpp-python,
  Playwright's driver) each carry the exact risk class that caused the
  v0.4.0 tls_client incident; each gets its own build-time assertion and its
  own `smoke_test.py` inference/launch-exercising extension so this can't
  regress silently. A ~1GB model download in CI on every tagged release
  adds real time/flakiness surface — mitigate with a pinned revision +
  checksum + `actions/cache`.
- **ToS/anti-bot exposure**: even with a human performing the final submit
  and login click, headed browser automation navigating and filling ATS
  pages may still run against some sites' Terms of Service independent of
  who clicks submit. Mitigate via a one-time in-app disclaimer before first
  Apply Assist use (documentation workstream), not a technical guarantee —
  this is inherent to the "app-driven automation" choice itself, already
  accepted in the approved design.
