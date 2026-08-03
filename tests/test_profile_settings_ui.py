"""022 Phase 4 — Profile and Settings become navigable and legible.

Profile was ~50 fields in one unbroken scroll. Its five sections declared a
two-column grid via `.grid-2`, which was defined in no stylesheet, so every
one of them rendered as a single stacked column. `.hint` was used 18 times and
also undefined, so the guidance under each field read exactly like the field
label above it.

Settings had the same problem in miniature: `<label class="switch">` around a
checkbox, with no `.switch` rule anywhere, so the escort control was a bare
browser checkbox that looked like nothing in particular.

The applicant asked for these two pages to be "more interactive and clear".
Clear is the repair above. Interactive is the section index and the
completeness readout — an empty profile field is not cosmetic, it is a field
Apply Assist will have to leave for the applicant on a real employer form, so
the page now says how many of those are left.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "web" / "static" / "styles.css"
TEMPLATES = ROOT / "web" / "templates"


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


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


class TestTheLayoutThatNeverRendered:
    def test_grid_2_actually_lays_out_two_columns(self):
        """FR-010 — it was a plain <div> for five sections and ~50 fields."""
        block = re.search(r"\.grid-2\s*\{([^}]*)\}", _css())
        assert block, ".grid-2 is used five times and defined nowhere"
        body = block.group(1)
        assert "grid" in body or "flex" in body
        assert "columns" in body or "flex" in body

    def test_grid_2_collapses_on_a_narrow_window(self):
        """FR-010 — two columns of form fields on a phone is unusable."""
        css = _css()
        assert re.search(r"@media[^{]*max-width[^{]*\{[^}]*\.grid-2", css,
                         re.S), ".grid-2 must collapse to one column"

    def test_hints_are_distinguishable_from_labels(self):
        """FR-011 — 18 uses, no definition, so a hint read as a label."""
        block = re.search(r"\.hint\s*\{([^}]*)\}", _css())
        assert block, ".hint is used 18 times and defined nowhere"
        body = block.group(1)
        assert "font-size" in body or "color" in body

    def test_the_escort_control_is_a_real_switch(self):
        """FR-012."""
        assert re.search(r"\.switch\s*\{", _css()), ".switch is not defined"
        assert re.search(r"\.switch[^{]*(?:input|::before|::after)[^{]*\{",
                         _css()), (
            "a .switch rule that never styles the control itself is not a "
            "switch, it is a container around a browser checkbox")


class TestSectionIndex:
    """FR-023 — both pages are longer than a viewport."""

    @pytest.mark.parametrize("path", ["/profile", "/settings"])
    def test_the_page_has_a_section_index(self, client, path):
        body = client.get(path).text
        assert 'class="section-index"' in body, f"{path} has no section index"

    @pytest.mark.parametrize("path", ["/profile", "/settings"])
    def test_every_index_entry_points_at_a_real_section(self, client, path):
        """An index whose links go nowhere is worse than no index."""
        body = client.get(path).text
        index = re.search(r'<nav class="section-index".*?</nav>', body, re.S)
        assert index, f"{path} has no section index"
        targets = re.findall(r'href="#([^"]+)"', index.group(0))
        assert targets, "the section index has no entries"
        for target in targets:
            assert f'id="{target}"' in body, (
                f"index links to #{target}, which exists on no element")

    @pytest.mark.parametrize("path", ["/profile", "/settings"])
    def test_every_section_is_in_the_index(self, client, path):
        """A section missing from the index is unreachable by it."""
        body = client.get(path).text
        index = re.search(r'<nav class="section-index".*?</nav>', body,
                          re.S).group(0)
        listed = set(re.findall(r'href="#([^"]+)"', index))
        present = set(re.findall(r'<section[^>]+id="([^"]+)"', body))
        missing = present - listed
        assert not missing, f"sections absent from the index: {sorted(missing)}"


class TestCompleteness:
    """The interactive part, and it is not decoration: an empty profile field
    is a field Apply Assist leaves for the applicant on a real form."""

    def test_the_page_reports_how_much_is_filled(self, client):
        body = client.get("/profile").text
        assert "data-complete" in body, (
            "Profile should say how much of it is filled — that number is "
            "how much Apply Assist will have to leave for you")

    def test_each_section_reports_its_own_count(self, client):
        body = client.get("/profile").text
        sections = re.findall(r'<section[^>]+data-complete[^>]*>', body)
        assert len(sections) >= 4, (
            "a single page-level number does not tell the applicant WHICH "
            "part to go and fill")


class TestNothingWasBroken:
    def test_every_deep_linked_field_anchor_still_exists(self, client):
        """FR-024 — the browser panel links straight to a named field when
        the applicant is missing it. A relayout that drops those anchors
        silently turns "add it to your profile" back into a dead end, which
        is the exact 021 defect."""
        body = client.get("/profile").text
        anchors = set(re.findall(r'id="(field-[a-z0-9_]+)"', body))
        assert anchors, "profile.html declares no field-* anchors at all"

        referenced: set[str] = set()
        for root in (TEMPLATES, ROOT / "extension", ROOT / "engine"):
            for path in root.rglob("*"):
                if path.suffix not in (".html", ".js", ".py"):
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                referenced.update(re.findall(r"#(field-[a-z0-9_]+)", text))
        dangling = referenced - anchors
        assert not dangling, (
            f"these anchors are linked to but no longer exist: "
            f"{sorted(dangling)}")

    def test_the_profile_form_still_posts_everything(self, client):
        """A prettier form that drops a field is a data-loss bug."""
        body = client.get("/profile").text
        for name in ("first_name", "last_name", "email", "phone",
                     "linkedin_url", "authorized_without_sponsorship",
                     "preferred_name", "work_auth_type", "phone_country_code",
                     "security_clearance", "drivers_licence"):
            assert f'name="{name}"' in body, f"{name} fell out of the form"

    def test_settings_still_exposes_every_section(self, client):
        body = client.get("/settings").text
        for heading in ("AI matching", "Saved logins", "Company watchlist",
                        "Updates"):
            assert heading in body, f"{heading} fell out of Settings"
