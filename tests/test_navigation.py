"""022 US4 — the applicant can always tell where they are.

Fourteen links sat in one wrapping bar with no visible grouping. The four
groups existed in the markup as `aria-label`s only, so sighted use got an
undifferentiated list that became two rows on a laptop — and `.grouplabel`
had been styled since feature 007 while nothing ever rendered it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "web" / "templates" / "base.html"
CSS = ROOT / "web" / "static" / "styles.css"

GROUPS = ("Search", "Pipeline", "Apply", "Setup")


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("REFRESH_SYNC", "1")
    from engine import matcher, pipeline

    monkeypatch.setattr(pipeline, "_source_names", lambda: [])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
    from web.main import create_app

    return TestClient(create_app())


class TestTwoTiers:
    def test_the_four_groups_are_visible_text(self, client):
        """FR-020 — not aria-label only. That was the whole defect."""
        body = client.get("/").text
        nav = re.search(r'<nav class="tabs".*?</nav>', body, re.S)
        assert nav, "the primary tab row is missing"
        for group in GROUPS:
            assert f">{group}<" in nav.group(0), (
                f"{group!r} must render as visible text, not an aria-label")

    def test_the_primary_row_cannot_wrap(self):
        """FR-020 / SC-004 — one line at 1024px and wider. A wrapping
        flex row is exactly what produced two rows on a laptop."""
        css = CSS.read_text(encoding="utf-8")
        block = re.search(r"\.tabs\s*\{([^}]*)\}", css)
        assert block, ".tabs is not defined"
        assert "flex-wrap" not in block.group(1) or \
            "nowrap" in block.group(1), (
            "the primary tab row must not wrap")

    def test_the_second_row_scrolls_instead_of_wrapping(self):
        """FR-021."""
        css = CSS.read_text(encoding="utf-8")
        block = re.search(r"\.views\s*\{([^}]*)\}", css)
        assert block, ".views is not defined"
        assert "overflow-x" in block.group(1), (
            "the view row must scroll horizontally when narrow, not wrap")


class TestCurrentIsMarked:
    @pytest.mark.parametrize("path,group", [
        ("/", "Search"),
        ("/autofill", "Apply"),
        ("/profile", "Setup"),
        ("/analytics", "Pipeline"),
    ])
    def test_the_active_group_is_marked(self, client, path, group):
        """FR-022 — programmatically and visually, both."""
        body = client.get(path).text
        nav = re.search(r'<nav class="tabs".*?</nav>', body, re.S).group(0)
        current = re.findall(r'<a[^>]*aria-current="page"[^>]*>([^<]+)</a>',
                             nav)
        assert current == [group], (
            f"{path} should mark {group!r} current, got {current}")

    def test_the_active_view_is_also_marked(self, client):
        """Both tiers, not just one — otherwise the applicant knows the
        section but not which view inside it."""
        body = client.get("/profile").text
        views = re.search(r'<nav class="views".*?</nav>', body, re.S)
        assert views, "the view row is missing"
        assert 'aria-current="page"' in views.group(0)


class TestNothingWasLost:
    """A tidier nav that quietly drops a page is not tidier.

    Two tiers means the view row shows only the CURRENT group's views — that
    is the design, chosen deliberately, and it is why every destination is two
    clicks (tab, then view) rather than one. So the guarantee to assert is not
    "every link is on every page", which would defeat the point; it is that
    walking the four tabs reaches everything, and that no page is orphaned.
    """

    TAB_ENTRY = {"Search": "/", "Pipeline": "/?status=saved",
                 "Apply": "/autofill", "Setup": "/profile"}

    def test_walking_the_four_tabs_reaches_every_destination(self, client):
        reachable: set[str] = set()
        for entry in self.TAB_ENTRY.values():
            body = client.get(entry).text
            views = re.search(r'<nav class="views".*?</nav>', body, re.S)
            assert views, f"{entry} rendered no view row"
            reachable.update(re.findall(r'href="([^"]+)"', views.group(0)))
            tabs = re.search(r'<nav class="tabs".*?</nav>', body, re.S)
            reachable.update(re.findall(r'href="([^"]+)"', tabs.group(0)))
        for href in ("/", "/analytics", "/autofill", "/companion",
                     "/learned-answers", "/profile", "/settings",
                     "/diagnostics"):
            assert href in reachable, (
                f"{href} is reachable from no tab — it is orphaned")

    def test_every_tab_is_on_every_page(self, client):
        """The tab row itself must never change, or the applicant loses the
        way back out of wherever they are."""
        for entry in self.TAB_ENTRY.values():
            body = client.get(entry).text
            tabs = re.search(r'<nav class="tabs".*?</nav>', body, re.S).group(0)
            for group in GROUPS:
                assert f">{group}<" in tabs, f"{group} missing on {entry}"
