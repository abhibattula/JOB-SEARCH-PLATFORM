"""T008/T019-T021: source parsers against recorded fixtures + polite HTTP base."""
import json
from pathlib import Path

import pytest

from engine.ingest import base

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestPoliteHttp:
    def test_enforces_per_domain_gap(self, monkeypatch):
        sleeps = []
        clock = {"now": 1000.0}

        def fake_monotonic():
            return clock["now"]

        def fake_sleep(seconds):
            sleeps.append(seconds)
            clock["now"] += seconds

        monkeypatch.setattr(base.time, "monotonic", fake_monotonic)
        monkeypatch.setattr(base.time, "sleep", fake_sleep)
        base._LAST_REQUEST.clear()

        base._respect_rate_limit("boards-api.greenhouse.io")
        clock["now"] += 0.2  # 200ms later, same domain -> must wait ~0.8s
        base._respect_rate_limit("boards-api.greenhouse.io")
        base._respect_rate_limit("api.lever.co")  # other domain -> no wait

        assert len(sleeps) == 1
        assert sleeps[0] == pytest.approx(0.8, abs=0.05)

    def test_strip_html_unescapes_and_flattens(self):
        html = "&lt;p&gt;Build &amp;amp; ship&lt;/p&gt;"
        assert base.strip_html(html) == "Build & ship"
        assert base.strip_html("<div>Hello<br>world</div>") == "Hello world"
