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
