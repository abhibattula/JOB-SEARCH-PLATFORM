"""010 hotfix guard: the companion's Manifest V3 service worker MUST be able
to wake itself.

v1.0.0 shipped with reconnect/keepalive scheduled purely via setTimeout /
setInterval. Chrome terminates an idle MV3 service worker after ~30s and
destroys its pending timers with it, so once the worker went inactive nothing
could ever run again — the connection dot stayed grey forever and the whole
companion feature was dead. `chrome.alarms` is the ONLY mechanism that wakes a
terminated worker; the permission was declared but never used.

These are static assertions on the shipped extension source: fast,
deterministic, and they fail loudly if the watchdog is ever removed again.
"""
import json
from pathlib import Path

EXT = Path(__file__).resolve().parents[1] / "extension"
BACKGROUND_JS = "\n".join(
    p.read_text(encoding="utf-8") for p in sorted((EXT / "background").glob("*.js"))
)


class TestServiceWorkerCanWakeItself:
    def test_alarms_permission_declared(self):
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        assert "alarms" in manifest["permissions"]

    def test_creates_a_periodic_alarm(self):
        assert "chrome.alarms.create" in BACKGROUND_JS, (
            "no chrome.alarms.create — a terminated service worker can never "
            "wake to reconnect (the v1.0.0 bug)"
        )

    def test_listens_for_the_alarm(self):
        assert "chrome.alarms.onAlarm" in BACKGROUND_JS, (
            "no chrome.alarms.onAlarm listener — Chrome will not wake the "
            "worker without one"
        )

    def test_alarm_period_within_chrome_minimum(self):
        # Chrome clamps alarms to a 30s (0.5 min) floor; anything smaller is
        # silently raised, so state it explicitly.
        assert "periodInMinutes" in BACKGROUND_JS
        assert "0.5" in BACKGROUND_JS

    def test_recovery_does_not_rely_only_on_timers(self):
        """setTimeout/setInterval are fine as in-lifetime optimisations, but
        the alarm must exist alongside them as the guaranteed wake path."""
        uses_timers = "setTimeout(" in BACKGROUND_JS or "setInterval(" in BACKGROUND_JS
        if uses_timers:
            assert "chrome.alarms" in BACKGROUND_JS, (
                "timers are used for recovery with no alarm backstop"
            )


class TestManifestIntegrity:
    def test_every_referenced_file_exists(self):
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        referenced = [manifest["background"]["service_worker"],
                      manifest["action"]["default_popup"]]
        for entry in manifest["content_scripts"]:
            referenced += entry["js"]
        for rel in referenced:
            assert (EXT / rel).exists(), f"manifest references missing file: {rel}"

    def test_content_scripts_run_in_all_frames(self):
        """Cross-origin iframe forms (Greenhouse embeds) only fill when each
        frame gets its own content-script instance."""
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        assert all(cs.get("all_frames") for cs in manifest["content_scripts"])

    def test_filler_only_clicks_through_guard(self):
        """011: the filler MAY now click a field's own widget to set a value,
        but the ONLY raw element.click() is the single guarded one inside
        safeClick(); every other click call must be safeClick(). safeClick
        itself must consult the denylist before clicking."""
        import re as _re

        filler = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        code = "\n".join(line.split("//")[0] for line in filler.splitlines())

        # exactly one raw ".click(" that is not preceded by "safeClick"
        raw_clicks = []
        for m in _re.finditer(r"\.click\s*\(", code):
            preceding = code[max(0, m.start() - 9):m.start()]
            if not preceding.endswith("safeClick"):
                raw_clicks.append(m)
        assert len(raw_clicks) == 1, (
            f"expected exactly one guarded raw .click(); found {len(raw_clicks)}"
        )
        # and it lives inside safeClick, after the denylist check
        sc = _re.search(r"function safeClick\([^)]*\)\s*\{(.*?)\n  \}",
                        code, _re.DOTALL)
        assert sc, "safeClick function not found"
        body = sc.group(1)
        # 019 (T036): the guard call is `isWidgetOperable` — it judges TEXT
        # on the element's own accessible name while still refusing any
        # submit-typed control or wrapper. The invariant this test exists
        # for is unchanged: one raw click, inside safeClick, after a guard
        # verdict.
        assert "isWidgetOperable" in body and ".click(" in body
        assert body.index("isWidgetOperable") < body.index(".click(")

    def test_filler_uses_the_click_guard(self):
        filler = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert "jeClickGuard" in filler and "isWidgetOperable" in filler


class TestDenylistParity:
    """011: the JS denylist must be term-for-term identical to the Python
    source of truth, or a submit could be clickable in one backend only."""

    def test_js_and_python_deny_terms_identical(self):
        from engine.autofill import click_guard as py_guard

        js = (EXT / "content" / "click_guard.js").read_text(encoding="utf-8")
        # extract the DENY_TERMS array literal from the JS
        import re as _re
        block = _re.search(r"DENY_TERMS\s*=\s*\[(.*?)\]", js, _re.DOTALL).group(1)
        js_terms = _re.findall(r'"([^"]+)"', block)
        assert set(js_terms) == set(py_guard.DENY_TERMS), (
            f"denylist drift — JS:{sorted(js_terms)} PY:{sorted(py_guard.DENY_TERMS)}"
        )

    def test_click_guard_js_loaded_before_filler(self):
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        js = manifest["content_scripts"][0]["js"]
        assert js.index("content/click_guard.js") < js.index("content/filler.js")


class TestDiscoveryBadge012:
    """012: the discovery content script is bundled, wired, and — critically —
    READ-ONLY on the page (it only renders its own shadow badge)."""

    DISCOVERY = (EXT / "content" / "discovery.js")

    def test_discovery_script_exists_and_is_registered(self):
        assert self.DISCOVERY.exists()
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        all_js = [j for cs in manifest["content_scripts"] for j in cs["js"]]
        assert "content/discovery.js" in all_js

    def test_manifest_version_tracks_app_version(self):
        """015 (R13): the repo manifest tracks the app release (the staged
        copy is additionally rewritten at stamp time) — a pinned literal here
        is exactly the stale-assert class the 013 ship lesson warns about."""
        from engine import APP_VERSION

        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["version"] == APP_VERSION

    def test_detection_signals_present(self):
        src = self.DISCOVERY.read_text(encoding="utf-8")
        assert 'application/ld+json' in src   # JSON-LD primary
        assert "JobPosting" in src
        assert "linkedin" in src.lower()
        assert "indeed" in src.lower()

    def test_it_renders_through_the_one_companion_widget(self):
        """018 (D1): discovery kept every bit of its detection and scoring
        logic but no longer owns a host — the shadow root moved to panel.js,
        so the match score and the fill progress share ONE card instead of
        two disconnected widgets in two corners."""
        src = self.DISCOVERY.read_text(encoding="utf-8")
        assert "window.jePanel" in src
        assert "attachShadow" not in src, "discovery must not own a host"
        panel = (EXT / "content" / "panel.js").read_text(encoding="utf-8")
        assert "attachShadow" in panel
        assert "je-companion-host" in panel

    def test_is_read_only_on_the_page(self):
        """The discovery script must never click/type-into/submit a PAGE
        element. It appends its own host and reads metadata only. Assert no
        page-mutating primitives are used at all (its own badge is built via
        innerHTML on a detached shadow root, and appendChild of its OWN host)."""
        code = "\n".join(
            line.split("//")[0]
            for line in self.DISCOVERY.read_text(encoding="utf-8").splitlines()
        )
        # no clicking page elements
        assert ".click(" not in code, "discovery must not click anything"
        # no submitting
        assert ".submit(" not in code and "requestSubmit" not in code
        # no writing values into page inputs / dispatching input/change events
        assert ".value =" not in code and ".value=" not in code
        assert "dispatchEvent" not in code
        # 018: discovery inserts nothing at all now — rendering is the
        # panel's job, and the panel only ever appends its own host.
        assert ".appendChild(" not in code, (
            "discovery must not insert anything into the page")

    def test_top_frame_guard(self):
        src = self.DISCOVERY.read_text(encoding="utf-8")
        assert "window !== window.top" in src or "window.top" in src

    def test_host_permissions_unchanged_no_new_reach(self):
        """FR-012/SC-007/FR-015: discovery adds no off-machine reach and no new
        permission — page metadata goes only to the local bridge."""
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["host_permissions"] == ["http://127.0.0.1/*"]
        assert set(manifest["permissions"]) == {"storage", "tabs", "alarms"}


class TestPopupDiagnostics015:
    """015 (T013/FR-011): the popup never presents a dead control — every
    disconnected state is recorded by the socket layer, survives worker
    restarts via storage.session, and maps to a plain-language reason with a
    retry. Static assertions on the shipped source (same style as above)."""

    def _socket(self):
        return (EXT / "background" / "socket.js").read_text(encoding="utf-8")

    def _sw(self):
        return (EXT / "background" / "service-worker.js").read_text(encoding="utf-8")

    def _popup(self):
        return (EXT / "popup" / "popup.js").read_text(encoding="utf-8")

    def test_socket_records_every_attempt_stage(self):
        src = self._socket()
        assert "lastAttempt" in src
        for stage in ("no-pairing", "identity-failed", "ws-error",
                      "closed", "connected"):
            assert f'"{stage}"' in src, f"missing recorded stage {stage}"
        assert "chrome.storage.session" in src  # survives worker restarts

    def test_session_record_never_contains_the_secret(self):
        """The session-storage record carries stage/port/code/at ONLY —
        the pairing secret must never be persisted anywhere (010 rule
        extended to diagnostics)."""
        src = self._socket()
        for line in src.splitlines():
            if "storage.session.set" in line:
                assert "secret" not in line

    def test_service_worker_reports_last_attempt_and_handles_connect(self):
        sw = self._sw()
        assert "lastAttempt" in sw  # status? reply includes it
        assert "connect!" in sw     # popup-triggered immediate retry

    def test_popup_maps_close_codes_to_plain_language(self):
        pj = self._popup()
        assert "4401" in pj and "4426" in pj
        assert "reload" in pj          # 4426 → reload the extension
        assert "stale" in pj           # 4401 → stale pairing guidance
        assert "Connect now" in (EXT / "popup" / "popup.html").read_text(
            encoding="utf-8")

    def test_popup_fill_button_explains_instead_of_noop(self):
        pj = self._popup()
        assert "Can't fill" in pj or "Can&#39;t fill" in pj


class TestTabFollowingAssets016:
    """016 (T008): the service worker follows child tabs and persists the
    watched set across MV3 restarts."""

    def test_tabs_listen_for_child_tabs_and_report_them(self):
        js = (EXT / "background" / "tabs.js").read_text(encoding="utf-8")
        assert "tabs.onCreated" in js
        assert "openerTabId" in js
        assert '"child_tab"' in js

    def test_watched_set_persisted_to_session_storage(self):
        tabs_js = (EXT / "background" / "tabs.js").read_text(encoding="utf-8")
        assert "storage.session" in tabs_js and "watchedTabs" in tabs_js
        sw = (EXT / "background" / "service-worker.js").read_text(encoding="utf-8")
        assert "restoreWatched" in sw


class TestDecongestionAndErrors016:
    """016 (T009/T010): discovery scores once per page state; companion
    errors and scan failures are surfaced, never silently dropped."""

    def test_discovery_scores_once_per_page_state(self):
        js = (EXT / "content" / "discovery.js").read_text(encoding="utf-8")
        assert "scoredFor" in js, (
            "no per-href score cache — the 1.5 s score flood head-of-line "
            "blocks the fill path (RC1 evidence)")

    def test_service_worker_surfaces_error_messages(self):
        sw = (EXT / "background" / "service-worker.js").read_text(
            encoding="utf-8")
        assert 'case "error"' in sw
        assert "lastError" in sw

    def test_popup_renders_last_error_and_never_blind_closes(self):
        js = (EXT / "popup" / "popup.js").read_text(encoding="utf-8")
        assert "lastError" in js
        assert "window.close" not in js, (
            "the popup must stay open to show the fill outcome — closing "
            "instantly is how the busy error vanished (RC4)")

    def test_content_script_reports_scan_errors(self):
        js = (EXT / "content" / "main.js").read_text(encoding="utf-8")
        assert '"scan_error"' in js


class TestGroupingAssets016:
    """016 (T011): both serializers carry the radio-grouping pass and the
    required flag — changed in lockstep (the E2E parity test proves the
    behavior; these fail fast on a missing half)."""

    def test_scanner_js_groups_radios(self):
        js = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        for token in ("radio_group", "members", "required", "legend"):
            assert token in js, f"scanner.js missing {token!r}"

    def test_watcher_serializer_groups_radios(self):
        from engine.autofill import watcher

        for token in ("radio_group", "members", "required", "legend"):
            assert token in watcher.SERIALIZE_JS, \
                f"watcher SERIALIZE_JS missing {token!r}"


class TestIdleBackoff020:
    """020 US5 (FR-020/FR-021): the companion gets cheap on pages that are
    not applications.

    MEASURED first, per research R6 and the 019 lesson — scanner.probe()
    walks the whole DOM for shadow roots and forces layout per candidate:
    2.8 ms at 4k elements, 16.9 ms at 20k, 52 ms at 60k. A 52 ms main-thread
    block every 1.5 s is visible jank on exactly the heavy pages an applicant
    browses. (The original research claim that this ran in EVERY frame was
    wrong — discovery.js is top-frame only; see the corrected R6.)

    The behavioural half — a form appearing after backoff is still found —
    is proven in the browser suite, not here.
    """

    def test_the_poll_backs_off_when_nothing_is_found(self):
        js = (EXT / "content" / "discovery.js").read_text(encoding="utf-8")
        assert "IDLE_POLL_MS" in js
        assert "IDLE_AFTER_TICKS" in js
        assert "quietTicks" in js

    def test_the_slow_poll_is_actually_slower(self):
        import re

        js = (EXT / "content" / "discovery.js").read_text(encoding="utf-8")
        fast = int(re.search(r"const POLL_MS = (\d+)", js).group(1))
        idle = int(re.search(r"const IDLE_POLL_MS = (\d+)", js).group(1))
        assert idle > fast, (fast, idle)
        # SC-008 wants at least a halving of idle cost; the interval is the
        # whole mechanism, so it has to at least double.
        assert idle >= fast * 2

    def test_a_dom_mutation_wakes_it_back_up(self):
        """The backoff is only safe because something cheap notices change.
        Without this a form appearing on a quiet page waits up to the slow
        interval — and on an SPA, potentially forever."""
        js = (EXT / "content" / "discovery.js").read_text(encoding="utf-8")
        assert "MutationObserver" in js
        assert "wake()" in js

    def test_the_waker_is_childlist_only(self):
        """An attribute/characterData observer on a busy page costs more than
        the poll it is protecting."""
        js = (EXT / "content" / "discovery.js").read_text(encoding="utf-8")
        observe = js[js.index("waker.observe"):js.index("waker.observe") + 200]
        assert "childList: true" in observe
        assert "attributes" not in observe
        assert "characterData" not in observe

    def test_navigation_resets_to_full_speed(self):
        js = (EXT / "content" / "discovery.js").read_text(encoding="utf-8")
        nav = js[js.index("SPA nav"):js.index("SPA nav") + 700]
        assert "wake()" in nav

    def test_finding_anything_resets_to_full_speed(self):
        """A page that HAS a posting or a form must never poll slowly."""
        js = (EXT / "content" / "discovery.js").read_text(encoding="utf-8")
        assert "wake();  // something is here" in js


class TestRichTextAssets020:
    """020 US4 (FR-016..FR-019): rich-text editors become real fields.

    Before this, a repository-wide search for "contenteditable" across
    engine/ and extension/ returned NOTHING. A rich-text cover letter — the
    highest-value field on most applications — was not unfilled, it was
    unseen: not counted, not flagged, no reason given.

    Both halves of the selector must move together. The DOM behaviour is
    proven by the browser suite; these fail fast on a missing half.
    """

    RICHTEXT_TOKENS = ("contenteditable", "role=textbox")

    def test_the_canonical_selector_covers_rich_text(self):
        from engine.autofill import fields

        for token in self.RICHTEXT_TOKENS:
            assert token in fields.FIELD_QUERY_SELECTOR, token

    def test_scanner_selector_covers_rich_text(self):
        js = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        for token in self.RICHTEXT_TOKENS:
            assert token in js, f"scanner.js missing {token!r}"

    def test_both_serializers_speak_richtext(self):
        """Parity: scanner.js and watcher.SERIALIZE_JS must produce the same
        descriptor for the same page. Drift here is what broke the whole
        Playwright serializer in 019."""
        from engine.autofill import watcher

        js = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        for token in ("richtext", "innerText"):
            assert token in js, f"scanner.js missing {token!r}"
            assert token in watcher.SERIALIZE_JS, \
                f"watcher SERIALIZE_JS missing {token!r}"

    def test_readonly_editors_are_excluded_by_both(self):
        """contenteditable=false / aria-readonly is display, not input."""
        from engine.autofill import watcher

        js = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        for token in ("aria-readonly",):
            assert token in js, f"scanner.js missing {token!r}"
            assert token in watcher.SERIALIZE_JS, \
                f"watcher SERIALIZE_JS missing {token!r}"

    def test_both_label_strippers_remove_rich_text_editors(self):
        """The 019 <select> bug, in a new element — caught by macOS CI.

        A wrapping label's innerText includes the control's OWN rendered
        text. With a rich-text editor inside one, the question read
        "Why do you want to work here? Tell us why..." and no stored answer
        could ever match it, so the field was silently skipped. Both
        serializers must strip editors exactly as they strip inputs.
        """
        from engine.autofill import watcher

        js = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        for source, fn, name in (
                (js, "function stripControls", "scanner.js"),
                (watcher.SERIALIZE_JS, "function jeStripControls",
                 "watcher SERIALIZE_JS")):
            start = source.index(fn)   # the DEFINITION, not a call site
            block = source[start:start + 1200]
            assert "contenteditable" in block, (
                f"{name} strips inputs but not rich-text editors")
            assert "role=textbox" in block, name

    def test_filler_has_a_rich_text_write_branch(self):
        js = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert 'kind === "richtext"' in js
        # a silent DOM write is discarded by React/ProseMirror/Quill on the
        # next render — only a real input event makes the value stick
        assert "InputEvent" in js or "insertText" in js
        assert "input" in js

    def test_filler_still_has_exactly_one_raw_click(self):
        """The 016 pin. The rich-text branch types; it must not add a click,
        and it must not be an excuse to loosen this."""
        js = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert js.count(".click(") == 1, (
            "filler.js must keep exactly one raw .click( site")


class TestFillerUpgrades016:
    """016 (T013, R8): real radio branch, normalized select matching,
    widened combobox harvest — behavior is DOM-verified in the E2E; these
    fail fast if a half is missing."""

    def test_filler_has_a_real_radio_branch(self):
        js = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert 'kind === "radio"' in js
        assert "radioGroupMembers" in js
        assert "checked = true" in js

    def test_select_matching_is_normalized_not_strict(self):
        js = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert "normText(o.text)" in js, (
            "selectByLabel must match normalized option text — strict "
            "equality broke canonicalized answers (RC2)")

    def test_combobox_harvest_widened_beyond_role_option(self):
        js = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert "[role=listbox] li" in js
        assert "select__option" in js


class TestApplyOpener016:
    """016 (T015, constitution v1.1.4): the apply-opener is a SEPARATE
    allowlisted one-shot step — the fill path's click guard still denies
    "apply" and is untouched."""

    def test_opener_module_exists_with_bounds(self):
        js = (EXT / "content" / "opener.js").read_text(encoding="utf-8")
        assert "OPENERS" in js
        # 019 (T038): the one-shot key became (doc token + control
        # fingerprint). `attemptedFor = href` dead-locked the opener on an
        # SPA wizard that keeps its address, and re-armed it on every
        # in-page navigation elsewhere. Same guarantee, correct key.
        assert "stepKey" in js and "attempted" in js
        assert 'type === "submit"' in js     # never a submit control
        assert "hasFillableForm" in js       # only when no form is open

    def test_opener_registered_before_main(self):
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        scripts = manifest["content_scripts"][0]["js"]
        assert "content/opener.js" in scripts
        assert scripts.index("content/opener.js") < scripts.index("content/main.js")

    def test_click_guard_still_denies_apply(self):
        js = (EXT / "content" / "click_guard.js").read_text(encoding="utf-8")
        assert '"apply"' in js  # the FILL path's denylist is unchanged

    def test_opener_selectors_mirror_adapters_registry(self):
        from engine.autofill import adapters

        js = (EXT / "content" / "opener.js").read_text(encoding="utf-8")
        assert adapters.APPLY_OPENERS, "registry must not be empty"
        for ats, selector in adapters.APPLY_OPENERS.items():
            # Compare SELECTOR PARTS: a long allowlist is wrapped across
            # string-concatenation lines in the JS, and a whole-string match
            # would fail on formatting rather than on drift.
            for part in [s.strip() for s in selector.split(",")]:
                assert part in js, (
                    f"opener.js missing {ats} selector {part}")

    def test_main_wires_opener_for_queue_watches_only(self):
        main = (EXT / "content" / "main.js").read_text(encoding="utf-8")
        assert "jeOpener" in main
        assert "adhoc" in main  # popup fill-here never auto-opens


class TestPanelAndHighlights016:
    """016 (T016/T017, D2/D3): the on-page panel gains needs-attention
    reporting and Fill again; drafted/needs-you fields carry a visible
    highlight cleared by the user's own edit."""

    def test_panel_has_fill_again_and_surfaces_what_needs_you(self):
        """018: these live in panel.js now — overlay.js was folded into the
        one merged companion.

        016 sent an `attention` list of up to five bare field LABELS. That is
        gone: the needs-you GROUP carries the same fields with their full
        question, the reason in plain language, and a box to answer them, so
        a list of labels beside it would be strictly redundant."""
        js = (EXT / "content" / "panel.js").read_text(encoding="utf-8")
        assert "Fill again" in js
        assert "needs_you" in js
        assert "Needs you" in js
        assert "onFillAgain" in js
        assert "notice" in js

    def test_filler_annotates_flags_and_clears_on_edit(self):
        js = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert "jeFlag" in js
        assert "outline" in js
        assert "annotateNeedsYou" in js
        assert "removeEventListener" in js  # cleared by the user's edit

    def test_main_wires_fill_again_and_needs_you(self):
        js = (EXT / "content" / "main.js").read_text(encoding="utf-8")
        assert '"fill_again"' in js
        assert "needs_you_idx" in js


class TestResumeTransport017:
    """017-T053 (C9, FR-029/FR-030): the resume is fetched through the
    service worker and verified before it is attached.

    The content script used to fetch the app's RELATIVE url directly, so it
    resolved against the job board. Greenhouse answers unknown paths with its
    SPA's HTML and status 200 — meaning a File named resume.pdf containing an
    HTML page was attached and reported as filled.
    """

    def test_the_content_script_no_longer_fetches_the_file_itself(self):
        source = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        attach = source[source.index("async function attachFile"):]
        attach = attach[:attach.index("\n  }")]
        assert "fetch(" not in attach, \
            "attachFile must go through the service worker, not fetch directly"
        assert "_je_file" in attach

    def test_the_service_worker_resolves_against_loopback(self):
        source = (EXT / "background" / "service-worker.js").read_text(
            encoding="utf-8")
        assert "_je_file" in source
        assert 'http://127.0.0.1:' in source
        assert "readPairing" in source

    def test_the_bytes_are_verified_before_attaching(self):
        source = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert "looksLikeExpectedDocument" in source
        # "%PDF" magic bytes — an HTML error body fails this check
        for byte in ("0x25", "0x50", "0x44", "0x46"):
            assert byte in source, byte

    def test_the_dead_filename_attribute_lookup_is_gone(self):
        source = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert "data-je-filename" not in source, \
            "nothing ever wrote this attribute; the name now arrives on the item"

    def test_the_real_filename_is_used(self):
        source = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert "item.filename" in source


class TestRescanHandled017:
    """017-T062 (C12, FR-037): `rescan` was a dead protocol slot.

    The app has sent it from three call sites since 016 — draft-ready pushes,
    the panel's Fill again, and POST /api/autofill/rescan — and nothing ever
    handled it, so every one of them waited on the 2-second safety poll.
    """

    def test_the_service_worker_handles_it(self):
        source = (EXT / "background" / "service-worker.js").read_text(
            encoding="utf-8")
        assert 'case "rescan":' in source

    def test_the_content_script_handles_it(self):
        source = (EXT / "content" / "main.js").read_text(encoding="utf-8")
        assert 'case "rescan":' in source

    def test_it_only_rescans_and_touches_no_state(self):
        source = (EXT / "content" / "main.js").read_text(encoding="utf-8")
        body = source[source.index('case "rescan":'):]
        body = body[:body.index("break;")]
        assert "scan()" in body
        for forbidden in ("teardown", "adhoc =", "startWatch"):
            assert forbidden not in body, forbidden


class TestPanelIsTheReviewSurface017:
    """017-T064 (FR-034/FR-035/FR-036/FR-045): the panel shows the answers.

    Before this it showed a COUNT — "N AI draft(s) — review in the app" — so
    an answer that was drafted but not filled could not be read without
    leaving the tab. The report was exactly that: "i am unable to see the
    drafted responses".
    """

    def panel(self):
        # 018: the review surface moved into the merged companion widget.
        return (EXT / "content" / "panel.js").read_text(encoding="utf-8")

    def test_the_shadow_root_is_open_so_the_e2e_can_assert_it(self):
        assert 'attachShadow({ mode: "open" })' in self.panel()

    def test_it_renders_answers_with_copy_and_insert(self):
        source = self.panel()
        assert "setAnswers" in source
        assert "clipboard.writeText" in source
        assert "Insert" in source

    def test_it_offers_an_input_for_questions_we_refused(self):
        source = self.panel()
        assert "askable" in source
        assert "onAnswer" in source

    def test_it_still_keeps_the_016_guarantees(self):
        source = self.panel()
        for required in ("Fill again", "onFillAgain", "note", "attention"):
            assert required in source or required == "attention", required
        # 019 (T070): the promise changed with the product. The escort
        # presses Apply, Sign in and Continue now; the FINAL Submit is
        # still, always, the applicant's — that is what the footer must
        # say, and it must never disappear.
        assert "You press the final Submit" in source

    def test_it_never_clicks_anything_on_the_page(self):
        """The panel's own buttons use addEventListener; it must not invoke
        .click() on any element."""
        source = self.panel()
        assert ".click(" not in source

    def test_answer_text_is_never_injected_as_html(self):
        """Answers come from a model and from form labels — they go in as
        textContent, never innerHTML.

        018: the panel does use innerHTML exactly once, to stamp out its own
        static shell (a literal in this file, no interpolated data). Every
        renderer that touches question or answer text must be clear of it, so
        this asserts against the rendering half specifically AND caps the
        total number of innerHTML uses at that one shell."""
        source = self.panel()
        body = source[source.index("function setAnswers"):]
        assert ".innerHTML" not in body
        assert source.count(".innerHTML") == 1, (
            "the only innerHTML in the panel may be its own static shell")

    def test_the_content_script_relays_the_capture_and_the_feed(self):
        source = (EXT / "content" / "main.js").read_text(encoding="utf-8")
        assert 'case "answers":' in source
        assert "answer_question" in source

    def test_the_service_worker_routes_answers_to_the_top_frame(self):
        source = (EXT / "background" / "service-worker.js").read_text(
            encoding="utf-8")
        assert 'case "answers":' in source


class TestBadgeLauncher017:
    """017-T070 (D4, FR-038/FR-039): the badge that already shows a match
    score becomes the launcher — one floating widget, not two.

    018 WARNING — do not add interaction assertions here. Every test in this
    class is a string-presence check on a source file, and the whole set of
    them passed for the entire life of v1.7.0 while the button they describe
    was DEAD: `onApply` read `current.posting`, a key detection never sets, so
    it returned before sending anything. Proof that a control WORKS lives in
    `tests/integration/test_companion_widget.py`, where it is clicked in a real
    browser. What survives here is only what source inspection genuinely
    proves: that a page-mutating primitive is ABSENT.
    """

    def badge(self):
        return (EXT / "content" / "discovery.js").read_text(encoding="utf-8")

    # RETIRED in 018 — `test_it_offers_apply_with_apply_assist` asserted
    #
    #     assert "Apply with Apply Assist" in self.badge()
    #     assert "apply_here" in self.badge()
    #
    # By the end of 018 the label had moved into panel.js and the only
    # occurrence of that phrase left in discovery.js was inside a COMMENT
    # explaining the bug. The assertion still passed. That is the whole
    # failure mode in one line: it was measuring the presence of a string,
    # never the existence of a working control.
    #
    # Replaced by TestPrimaryActionWorks in
    # tests/integration/test_companion_widget.py, which clicks the button in
    # a real browser and asserts the app started a session.

    def test_it_opens_the_existing_panel_rather_than_a_second_widget(self):
        """018: one widget at last — discovery renders through window.jePanel
        instead of owning a badge alongside the fill panel."""
        source = self.badge()
        assert "window.jePanel" in source

    def test_it_still_mutates_nothing_on_the_page(self):
        """The 012 read-only guarantee is unchanged: the badge sends
        messages and renders its own shadow DOM, and that is all."""
        source = self.badge()
        assert ".click(" not in source
        assert ".submit(" not in source
        assert "dispatchEvent" not in source


class TestPinnedToViewport018:
    """018 (R1): both widgets rendered at the BOTTOM of the document, not in
    the corner of the viewport, from v1.0.0 through v1.7.0.

    `host.style.cssText = "position:fixed;…;all:initial;"` — `all` is a
    shorthand for EVERY CSS property, declared last, so it reset `position`
    to `static`, `inset` to `auto` and `display` to `inline`. Appended as the
    last child of <body>, a static host renders at the end of the document
    flow. On the 5000px test fixture the badge measured y=5181.

    The real proof is the computed-style assertion in the browser suite. This
    guards the ORDERING that caused it, which source inspection can see and a
    future editor could silently reintroduce.
    """

    WIDGETS = ("panel.js",)

    def test_there_is_exactly_one_widget_module(self):
        """018 (D1): overlay.js was folded into panel.js. Two modules meant
        two hosts, two shadow roots and no shared state — the badge could not
        see the fill progress and the panel could not see the match score."""
        assert not (EXT / "content" / "overlay.js").exists(), (
            "overlay.js is back — the companion must stay a single widget")
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        js = [j for cs in manifest["content_scripts"] for j in cs["js"]]
        assert "content/panel.js" in js
        assert "content/overlay.js" not in js
        # panel.js must load before the scripts that drive it
        assert js.index("content/panel.js") < js.index("content/discovery.js")
        assert js.index("content/panel.js") < js.index("content/main.js")

    def _source(self, name):
        return (EXT / "content" / name).read_text(encoding="utf-8")

    def test_all_initial_is_never_declared_after_position(self):
        for name in self.WIDGETS:
            src = self._source(name)
            for line in src.splitlines():
                code = line.split("//")[0]
                if "all:initial" not in code.replace(" ", ""):
                    continue
                flat = code.replace(" ", "")
                assert "position:fixed" not in flat, (
                    f"{name}: `all:initial` shares a declaration block with "
                    "`position:fixed` — as a shorthand for every property it "
                    "resets whichever of them comes first. Reset first, then "
                    "position.")

    def test_positioning_is_important(self):
        """A plain inline declaration sits in the author-NORMAL cascade layer
        and loses to a page rule like `div { position: static !important }`.
        Only an inline !important declaration wins."""
        for name in self.WIDGETS:
            src = self._source(name)
            assert '"position", "fixed", "important"' in src, (
                f"{name}: position must be set with !important")
            assert '"z-index"' in src and '"important"' in src


class TestReadOnlyFormProbe018:
    """018 (R7, FR-005): the companion appears on a bare ATS application page.

    The signal must NOT be `serialize()`. That function stamps — `stamp()`
    writes data-je-idx onto every field and `docToken()` writes data-je-doc
    onto <html> — so using it merely to decide whether to render a widget
    would mutate every page the applicant browses, before they asked for
    anything. That would break the read-only guarantee the discovery path has
    held since 012.
    """

    def scanner(self):
        return (EXT / "content" / "scanner.js").read_text(encoding="utf-8")

    def test_probe_is_exported(self):
        src = self.scanner()
        assert "function probe(" in src
        assert "looksLikeApplicationForm" in src
        assert "probe," in src or "probe }" in src or "probe, " in src

    def test_probe_stamps_nothing(self):
        """The body of probe() must not call the two mutating helpers."""
        src = self.scanner()
        start = src.index("function probe(")
        body = src[start:src.index("\n  }", start)]
        assert "stamp(" not in body, "probe() must not stamp the page"
        assert "docToken(" not in body, "probe() must not write a doc token"
        assert "describe(" not in body, "probe() must not build descriptors"

    def test_credential_forms_are_excluded(self):
        """A login form is not an application, and we never fill credentials.
        Excluding the password field alone is not enough — `username` would
        survive and, with an ordinary newsletter box, reach the threshold."""
        src = self.scanner()
        assert "inCredentialForm" in src
        assert "input[type=password]" in src


class TestSessionControlAssets018:
    """018 US4 (FR-030/FR-032/FR-035): the applicant never has to switch to
    the app mid-application."""

    def test_the_panel_offers_stop_and_next(self):
        panel = (EXT / "content" / "panel.js").read_text(encoding="utf-8")
        assert '"stop"' in panel
        assert 'id="next"' in panel

    def test_discovery_sends_session_control(self):
        src = (EXT / "content" / "discovery.js").read_text(encoding="utf-8")
        assert "session_control" in src

    def test_keyboard_commands_are_declared_and_handled(self):
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        commands = manifest.get("commands") or {}
        assert "toggle-companion" in commands
        assert "fill-this-page" in commands
        for name, spec in commands.items():
            assert spec.get("description"), f"{name} has no description"
        sw = (EXT / "background" / "service-worker.js").read_text(
            encoding="utf-8")
        assert "chrome.commands.onCommand" in sw
        content = (EXT / "content" / "discovery.js").read_text(encoding="utf-8")
        assert "toggle_companion" in content
        assert "fill_this_page" in content

    def test_commands_need_no_new_permission(self):
        """`commands` is not a permission — the companion's reach is
        unchanged, which is the whole point of the 012 guarantee."""
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        assert set(manifest["permissions"]) == {"storage", "tabs", "alarms"}
        assert manifest["host_permissions"] == ["http://127.0.0.1/*"]

    def test_app_errors_reach_the_page(self):
        sw = (EXT / "background" / "service-worker.js").read_text(
            encoding="utf-8")
        assert "app_error" in sw
        content = (EXT / "content" / "discovery.js").read_text(encoding="utf-8")
        assert "app_error" in content


class TestVersionSkewAssets019:
    """019 (T006): wiring pins for the version-skew surfaces. Structure only —
    behavior is proven in a real browser by TestVersionSkew019."""

    def _read(self, rel):
        return (EXT / rel).read_text(encoding="utf-8")

    def test_socket_compares_app_version_and_persists(self):
        sock = self._read("background/socket.js")
        assert "app_version" in sock
        assert "getManifest().version" in sock.replace(" ", "")
        assert "mismatch" in sock

    def test_popup_renders_the_reload_instruction(self):
        popup = self._read("popup/popup.js")
        assert "mismatch" in popup
        assert "reload" in popup.lower()

    def test_page_notice_copy_reaches_main(self):
        main = self._read("content/main.js")
        assert "version_state" in main
        assert "reload the companion" in main.lower()

    def test_companion_page_has_the_amber_branch(self):
        html = (EXT.parent / "web" / "templates" / "companion.html"
                ).read_text(encoding="utf-8")
        assert "version_ok" in html
        assert "reload" in html.lower()


class TestSharedRulesParity019:
    """019: three implementations of two rules — keep them in step."""

    def test_placeholder_rule_exists_in_all_three(self):
        scanner = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        filler = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        watcher = (EXT.parent / "engine" / "autofill" / "watcher.py"
                   ).read_text(encoding="utf-8")
        assert "isPlaceholderValue" in scanner
        assert "isPlaceholderValue" in filler
        assert "jeIsPlaceholder" in watcher

    def test_placeholder_tokens_match_the_python_rule(self):
        """The token list is the rule. If Python learns a new placeholder
        word and the serializers do not, that dropdown silently goes back to
        being permanently skipped."""
        import re as _re

        from engine.autofill import field_core

        py = field_core._PLACEHOLDER_VALUE.pattern
        tokens = set(_re.findall(r"[a-z/]{3,}", py)) - {"please"}
        for source in ((EXT / "content" / "scanner.js"),
                       (EXT.parent / "engine" / "autofill" / "watcher.py")):
            text = source.read_text(encoding="utf-8")
            for token in tokens:
                assert token in text, (
                    f"{source.name} is missing placeholder token {token!r}")

    def test_widget_guard_exists_in_both_halves(self):
        js = (EXT / "content" / "click_guard.js").read_text(encoding="utf-8")
        assert "isWidgetOperable" in js
        from engine.autofill import click_guard

        assert hasattr(click_guard, "is_widget_operable")

    def test_shadow_traversal_is_used_by_every_lookup(self):
        """FR-008: a form inside an open shadow root must be scanned, probed
        AND its options found — one missed call site is a silent blind spot."""
        scanner = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        filler = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert "deepQueryAll" in scanner and "shadowRoot" in scanner
        assert "deepQueryAll" in filler
        # serialize/probe/elementByIdx must not fall back to a flat query
        for fn in ("function serialize", "function probe",
                   "function elementByIdx"):
            start = scanner.index(fn)
            body = scanner[start:start + 400]
            assert "document.querySelectorAll" not in body, (
                f"{fn} still uses a flat query — shadow roots stay invisible")


class TestAdvancerAssets019:
    """019: the second click module. It follows the opener's shape — its own
    allowlist mirrored from the engine, its own single guarded click site —
    so filler.js's one-click pin stays exactly as it was."""

    ADVANCER = EXT / "content" / "advancer.js"

    def test_it_exists_and_loads_in_the_right_order(self):
        assert self.ADVANCER.exists()
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        js = manifest["content_scripts"][0]["js"]
        assert "content/advancer.js" in js
        assert js.index("content/advancer.js") < js.index("content/main.js")
        assert js.index("content/click_guard.js") < js.index("content/advancer.js")
        assert js.index("content/scanner.js") < js.index("content/advancer.js")

    def test_exactly_one_raw_click(self):
        """The same guarantee filler.js carries: ONE click site, reachable
        only after every refusal has been checked."""
        import re as _re

        code = "\n".join(line.split("//")[0]
                          for line in self.ADVANCER.read_text(
                              encoding="utf-8").splitlines())
        clicks = _re.findall(r"\.click\s*\(", code)
        assert len(clicks) == 1, f"expected one raw click; found {len(clicks)}"

    def test_every_refusal_precedes_the_click(self):
        code = self.ADVANCER.read_text(encoding="utf-8")
        click_at = code.index(".click(")
        for guard in ("isProgressionSafe", "finalClass", "captchaPresent",
                      "NO_CLICK_HOSTS", "done.has"):
            assert guard in code, f"advancer.js lost its {guard} refusal"
            assert code.index(guard) < click_at, (
                f"{guard} must be checked BEFORE the click")

    def test_allowlist_mirrors_the_engine_registry(self):
        from engine.autofill import adapters

        js = self.ADVANCER.read_text(encoding="utf-8")
        assert adapters.ADVANCE_ALLOWLIST, "registry must not be empty"
        for ats, selector in adapters.ADVANCE_ALLOWLIST.items():
            for part in [s.strip() for s in selector.split(",")]:
                assert part in js, f"advancer.js missing {ats} selector {part}"

    def test_final_terms_parity(self):
        """A term the app refuses and the page permits is a submitted
        application. The two lists must be identical."""
        import re as _re

        from engine.autofill import click_guard as py_guard

        js = (EXT / "content" / "click_guard.js").read_text(encoding="utf-8")
        block = _re.search(r"FINAL_TERMS = \[(.*?)\];", js, _re.DOTALL).group(1)
        js_terms = _re.findall(r'"([^"]+)"', block)
        assert set(js_terms) == set(py_guard.FINAL_TERMS), (
            f"final-class drift — JS:{sorted(js_terms)} "
            f"PY:{sorted(py_guard.FINAL_TERMS)}")

    def test_the_panel_still_never_clicks_the_page(self):
        """018's guarantee, unchanged: the widget renders and delegates."""
        panel = (EXT / "content" / "panel.js").read_text(encoding="utf-8")
        code = "\n".join(line.split("//")[0] for line in panel.splitlines())
        assert ".click(" not in code

    def test_the_scanner_still_never_clicks_the_page(self):
        scanner = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        code = "\n".join(line.split("//")[0] for line in scanner.splitlines())
        assert ".click(" not in code


class TestSectionContextParity:
    """021 (FR-008, contracts/section_context.md).

    Section context is what makes de-duplicating by question SAFE — two
    "Start date" fields in two employment blocks are two real questions, and
    collapsing them would be worse than the flood it fixes. So both
    serializers have to resolve it the same way, or the escort path and the
    companion path silently disagree about which employer a date belongs to.

    Token presence alone is NOT this feature's coverage: the real behaviour
    is asserted against a live DOM in
    tests/integration/test_extension_fixture_pages.py. These are the cheap
    drift alarms that run on every commit.
    """

    def test_both_serializers_resolve_a_section(self):
        from engine.autofill import watcher

        js = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        for source, name in ((js, "scanner.js"),
                             (watcher.SERIALIZE_JS, "watcher SERIALIZE_JS")):
            for token in ("section_label", "section_index",
                          "role=group", "role=region",
                          'data-automation-id$="Section"'):
                assert token in source, f"{name} missing {token!r}"

    def test_neither_serializer_stamps_the_section_onto_the_dom(self):
        """A stamped index would drift on exactly the React remounts that
        made the v2.0.0 panel unreadable. It must be recomputed per scan."""
        from engine.autofill import watcher

        js = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        for source, name in ((js, "scanner.js"),
                             (watcher.SERIALIZE_JS, "watcher SERIALIZE_JS")):
            for forbidden in ("dataset.jeSection", "data-je-section",
                              "setAttribute('data-je-section'",
                              'setAttribute("data-je-section"'):
                assert forbidden not in source, (
                    f"{name} persists the section index — it must not")

    def test_both_section_namers_strip_controls(self):
        """A section container that also renders a control's own text would
        otherwise be named after the applicant's answer. That is the
        019/020 label bug, in a third place — pinned before it happens."""
        from engine.autofill import watcher

        js = (EXT / "content" / "scanner.js").read_text(encoding="utf-8")
        for source, fn, name in (
                (js, "function sectionNameOf", "scanner.js"),
                (watcher.SERIALIZE_JS, "function jeSectionNameOf",
                 "watcher SERIALIZE_JS")):
            start = source.index(fn)   # the DEFINITION, not a call site
            block = source[start:start + 900]
            assert "tripControls(" in block, (
                f"{name} names a section with raw text instead of "
                f"stripControls()")


class TestTheProtocolStaysAdditive:
    """021: PROTOCOL_V stays 1. Both directions, because the 020 bug was a
    Literal that rejected an ENTIRE fields message over one unknown value —
    the scan was perfect, the tab opened, and nothing filled."""

    def _fields(self, descriptor):
        import json

        from engine.autofill import ext_protocol

        return ext_protocol.parse_inbound(json.dumps({
            "v": ext_protocol.PROTOCOL_V,
            "type": "fields", "tab_id": 1, "frame_id": 0, "doc": "d",
            "url": "https://boards.greenhouse.io/x/jobs/1",
            "descriptors": [descriptor],
        }))

    def test_protocol_version_is_still_one(self):
        from engine.autofill import bridge_const

        assert bridge_const.PROTOCOL_V == 1, (
            "021 is additive; bumping this breaks every installed companion")

    def test_an_older_companion_omitting_the_section_still_validates(self):
        msg = self._fields({"je_idx": "1", "doc": "d", "tag": "input"})
        assert msg.descriptors[0].section_label == ""
        assert msg.descriptors[0].section_index == 0

    def test_a_newer_companion_sending_unknown_keys_is_not_rejected(self):
        """A newer companion talking to an older app must not take the whole
        page down. `extra="ignore"` is the guarantee — pinned here so nobody
        tightens it to "forbid" without meeting this test."""
        msg = self._fields({
            "je_idx": "1", "doc": "d", "tag": "input",
            "section_label": "Work Experience", "section_index": 2,
            "some_future_key": {"nested": [1, 2, 3]},
        })
        assert msg.descriptors[0].section_label == "Work Experience"
        assert msg.descriptors[0].section_index == 2

    def test_the_section_survives_into_the_watcher_dict(self):
        """field_core reads descriptors through as_watcher_dict(); a field
        dropped there is a field the history layer can never index."""
        msg = self._fields({
            "je_idx": "1", "doc": "d", "tag": "input",
            "section_label": "Education", "section_index": 1,
        })
        raw = msg.descriptors[0].as_watcher_dict()
        assert raw["section_label"] == "Education"
        assert raw["section_index"] == 1


class TestThePanelCanBeMoved:
    """021 US5 (FR-027..FR-030). The panel sat on top of the very controls
    being filled and could not be moved.

    Real drag behaviour is asserted in the browser suite; these are the
    static guards that run on every commit — and the most important one is
    that every placement declaration stays `!important`."""

    def _panel(self):
        return (EXT / "content" / "panel.js").read_text(encoding="utf-8")

    def test_every_placement_declaration_stays_important(self):
        """The v1.0.0-to-v1.7.0 bug, documented in panel.js itself: a plain
        inline declaration LOSES to a page rule like
        `div { position: static !important }`. A drag implementation that
        wrote style.left normally would resurrect it."""
        js = self._panel()
        start = js.index("function applyPos")
        block = js[start:start + 400]
        assert '"important"' in block, (
            "applyPos writes placement without !important — a hostile page "
            "stylesheet will win")

    def test_it_never_writes_a_bare_left_or_top(self):
        """Offsets from right/bottom keep the existing `inset` idiom and
        survive a window resize. Page coordinates would scroll away."""
        js = self._panel()
        for forbidden in ("style.left =", "style.top =",
                          'setProperty("left"', 'setProperty("top"'):
            assert forbidden not in js, forbidden

    def test_the_position_is_persisted_outside_the_page(self):
        """localStorage is per-origin, so the panel would forget its place on
        every new employer's domain."""
        js = self._panel()
        assert "chrome.storage.local" in js
        assert "localStorage" not in js

    def test_a_restored_position_is_clamped(self):
        js = self._panel()
        assert "function clampPos" in js
        start = js.index("function restorePos")
        assert "clampPos" in js[start:start + 500], (
            "a position saved on a big monitor would strand the panel "
            "off-screen on a laptop")

    def test_a_resize_reclamps(self):
        js = self._panel()
        assert "function onViewportResize" in js
        assert '"resize", onViewportResize' in js

    def test_dragging_ignores_the_header_buttons(self):
        """Collapse and Dismiss live in the drag handle."""
        js = self._panel()
        start = js.index("function startDrag")
        block = js[start:start + 500]
        assert 'closest("button")' in block

    def test_there_is_a_way_back_to_the_corner(self):
        js = self._panel()
        assert "function resetPos" in js
        assert 'id="resetpos"' in js


class TestTheApplicantsTypingIsNeverDisturbed:
    """021 — the regression the browser suite caught twice.

    v1.8.0's guarantee is that a row the applicant is typing into is never
    rebuilt. `patchRow` was guarded, but PLACEMENT was not: reconcile called
    `appendChild` on every pass and relied on its reordering side-effect, and
    re-inserting a node BLURS any focused element inside it.

    Until 021 the digest's send-nothing-if-unchanged rule hid that — the
    payload simply never changed, so reconcile never ran twice with the same
    rows. The moment the payload gained new fields, focus started being stolen.
    """

    def _panel(self):
        return (EXT / "content" / "panel.js").read_text(encoding="utf-8")

    def test_placement_only_moves_a_node_that_is_out_of_position(self):
        js = self._panel()
        start = js.index("function placeAt")
        block = js[start:start + 400]
        assert "parent.children[index] === node" in block, (
            "placeAt moves unconditionally — re-inserting a node blurs a "
            "focused element inside it")
        assert "return;" in block

    def test_placement_refuses_to_move_a_focused_row(self):
        js = self._panel()
        start = js.index("function placeAt")
        block = js[start:start + 400]
        assert "holdsFocus(node)" in block, (
            "placeAt reorders under the applicant's fingers")

    def test_reconcile_no_longer_blind_appends_rows(self):
        js = self._panel()
        start = js.index("function reconcile")
        block = js[start:start + 1800]
        assert "placeAt(" in block
        assert "body.appendChild(row.wrap)" not in block, (
            "reconcile still re-appends every row on every pass")

    def test_a_section_header_is_only_written_when_it_changes(self):
        js = self._panel()
        start = js.index("function sectionBody")
        block = js[start:start + 900]
        assert "sec.head.textContent !== sectionTitle(item)" in block

    def test_the_focus_guard_on_patching_is_still_there(self):
        """The v1.8.0 half, which must not be lost while fixing the other."""
        js = self._panel()
        assert "if (!holdsFocus(row.wrap)) { patchRow(row, item); }" in js
