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
        return (EXT / "content" / "overlay.js").read_text(encoding="utf-8")

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
        assert "You click apply / submit" in source

    def test_it_never_clicks_anything_on_the_page(self):
        """The panel's own buttons use addEventListener; it must not invoke
        .click() on any element."""
        source = self.panel()
        assert ".click(" not in source

    def test_answer_text_is_never_injected_as_html(self):
        """Answers come from a model and from form labels — they go in as
        textContent, never innerHTML."""
        source = self.panel()
        body = source[source.index("function renderRow"):]
        assert ".innerHTML" not in body

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

    def test_it_offers_apply_with_apply_assist(self):
        assert "Apply with Apply Assist" in self.badge()
        assert "apply_here" in self.badge()

    def test_it_opens_the_existing_panel_rather_than_a_second_widget(self):
        source = self.badge()
        assert "window.jeOverlay" in source

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

    WIDGETS = ("discovery.js", "overlay.js")

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
