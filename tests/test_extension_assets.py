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
        assert "isDenylisted" in body and ".click(" in body
        assert body.index("isDenylisted") < body.index(".click(")

    def test_filler_uses_the_click_guard(self):
        filler = (EXT / "content" / "filler.js").read_text(encoding="utf-8")
        assert "jeClickGuard" in filler and "isDenylisted" in filler


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

    def test_uses_shadow_dom(self):
        src = self.DISCOVERY.read_text(encoding="utf-8")
        assert "attachShadow" in src
        assert "je-discovery-badge-host" in src

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
        # the ONLY DOM insertion is our own host (appendChild of `host`)
        import re as _re
        appends = _re.findall(r"\.appendChild\(([^)]*)\)", code)
        assert appends and all("host" in a for a in appends), (
            f"discovery appends something other than its own host: {appends}"
        )

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
        assert "attemptedFor" in js          # one-shot per page state
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
            assert selector in js, f"opener.js missing {ats} selector"

    def test_main_wires_opener_for_queue_watches_only(self):
        main = (EXT / "content" / "main.js").read_text(encoding="utf-8")
        assert "jeOpener" in main
        assert "adhoc" in main  # popup fill-here never auto-opens


class TestPanelAndHighlights016:
    """016 (T016/T017, D2/D3): the on-page panel gains needs-attention
    reporting and Fill again; drafted/needs-you fields carry a visible
    highlight cleared by the user's own edit."""

    def test_overlay_panel_has_fill_again_and_attention(self):
        js = (EXT / "content" / "overlay.js").read_text(encoding="utf-8")
        assert "Fill again" in js
        assert "attention" in js
        assert "onFillAgain" in js
        assert "note" in js

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
