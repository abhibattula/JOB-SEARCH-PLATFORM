import re
import pytest

"""013/014: web-layer presentation helpers + app lifecycle."""
from web.main import _humandate


def test_startup_bootstrap_runs_under_lifespan(monkeypatch, tmp_db):
    """014: the startup work (db init + background bootstrap) must run via the
    lifespan handler (replacing the deprecated @app.on_event('startup'))."""
    from fastapi.testclient import TestClient

    from web import main as webmain

    ran = {}
    monkeypatch.setattr(webmain.db, "init_db",
                        lambda: ran.__setitem__("init", True))
    monkeypatch.setattr(webmain, "_bootstrap_sponsorship", lambda: None)
    from engine import updates
    monkeypatch.setattr(updates, "startup_check", lambda: None)

    app = webmain.create_app()
    with TestClient(app):  # entering the context runs the lifespan startup
        pass
    assert ran.get("init") is True


def test_iso_date_to_human():
    assert _humandate("2026-07-24") == "24 July 2026"


def test_iso_datetime_to_human():
    assert _humandate("2026-07-24T09:15:00") == "24 July 2026"


def test_day_has_no_leading_zero():
    assert _humandate("2026-07-04") == "4 July 2026"


def test_none_and_empty_pass_through():
    assert _humandate(None) == ""
    assert _humandate("") == ""


def test_unparseable_returned_unchanged():
    assert _humandate("sometime") == "sometime"


def test_no_iso_date_slicing_in_display_templates():
    """014 (FR-013): no user-facing template may display a raw ISO date via the
    `[:10]` slice — all display dates go through `| humandate`. (HTML
    input[type=date] values legitimately stay ISO and are exempt.)"""
    import pathlib

    tdir = pathlib.Path("web/templates")
    offenders = []
    for f in tdir.rglob("*.html"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "[:10]" in line and 'type="date"' not in line:
                offenders.append(f"{f.name}:{i}")
    assert not offenders, f"raw [:10] date slice (use | humandate): {offenders}"


def test_command_palette_present_and_accessible():
    """014 (US3): the palette ships, is referenced, and is an ARIA dialog with
    a Ctrl/Cmd-K shortcut + Escape handling."""
    import pathlib

    js = pathlib.Path("web/static/palette.js").read_text(encoding="utf-8")
    assert 'role", "dialog"' in js or 'role="dialog"' in js
    assert "aria-modal" in js and "Escape" in js
    assert 'metaKey' in js and '"k"' in js  # Ctrl/Cmd-K
    base = pathlib.Path("web/templates/base.html").read_text(encoding="utf-8")
    assert "palette.js" in base


def test_banners_render_server_side_not_load_injected():
    """014 (CLS fix regression guard): the top banners must NOT re-introduce the
    hx-trigger=load injection that caused the measured CLS 0.27."""
    import pathlib

    base = pathlib.Path("web/templates/base.html").read_text(encoding="utf-8")
    assert 'hx-get="/partials/update-banner"' not in base
    assert 'hx-get="/partials/whats-new"' not in base
    assert "pending_update()" in base and "unseen_whats_new()" in base


def test_autofill_job_checkbox_has_accessible_label():
    """014 (T019 a11y regression guard): the per-job Apply Assist checkbox must
    carry an accessible name (aria-label) — Lighthouse flagged it as an
    unlabeled form control (a11y 93) when the queue is non-empty."""
    import pathlib

    html = pathlib.Path("web/templates/autofill.html").read_text(encoding="utf-8")
    for line in html.splitlines():
        if "autofill-job-check" in line and "<input" in line:
            assert "aria-label" in line, "autofill checkbox needs an aria-label"


def test_prose_links_have_non_color_cue():
    """014 (T019 a11y regression guard): inline links inside prose must not rely
    on color alone (WCAG 1.4.1) — Lighthouse flagged the profile link inside a
    `.muted` paragraph (a11y 96). A `p a` underline rule restores the cue."""
    import pathlib

    css = pathlib.Path("web/static/styles.css").read_text(encoding="utf-8")
    assert "p a" in css and "text-decoration: underline" in css


def test_unclean_exit_banner_shows_once_and_dismisses(tmp_db):
    """015 (FR-005): an abnormal previous end surfaces as a one-time
    dismissible banner linking Diagnostics; dismissing clears the record."""
    from fastapi.testclient import TestClient

    from engine import settings
    from web.main import create_app

    c = TestClient(create_app())
    assert "closed unexpectedly" not in c.get("/").text

    settings.set("UNCLEAN_EXIT_AT", "2026-07-25T00:47:05")
    home = c.get("/").text
    assert "closed unexpectedly" in home
    assert "/diagnostics" in home

    assert c.post("/api/unclean-exit/dismiss").status_code == 200
    assert settings.get("UNCLEAN_EXIT_AT") in (None, "")
    assert "closed unexpectedly" not in c.get("/").text


def test_activity_log_replaces_the_blocking_pending_panel():
    """016 (FR-019): the status partial shows a PASSIVE activity log
    (drafting / drafted / needs-you) — the blocking review box is gone;
    corrections happen on the page and the bank is curated from the
    profile."""
    import pathlib

    html = pathlib.Path("web/templates/partials/autofill_status.html").read_text(
        encoding="utf-8")
    assert "current.pending" not in html
    assert "current.activity" in html
    assert "needs you" in html
    assert "answer bank" in html


def test_stamp_failure_banner_on_autofill_and_companion(tmp_db):
    """015 (FR-008): a pairing-preparation failure is NEVER log-only — it
    banners on the Apply Assist and connect pages the same session, and
    clears once a later stamp succeeds."""
    import json as json_mod

    from fastapi.testclient import TestClient

    from engine import paths
    from web.main import create_app

    c = TestClient(create_app())
    assert "pairing needs attention" not in c.get("/autofill").text

    paths.data_dir().mkdir(parents=True, exist_ok=True)
    (paths.data_dir() / "stamp_status.json").write_text(json_mod.dumps({
        "ok": False, "error": "ImportError: pydantic_core missing",
        "at": "2026-07-25T00:41:00", "port": 8000,
        "app_version": None, "copy_warning": None,
    }), encoding="utf-8")
    page = c.get("/autofill").text
    assert "pairing needs attention" in page
    assert "pydantic_core missing" in page
    assert "pairing needs attention" in c.get("/companion").text

    (paths.data_dir() / "stamp_status.json").write_text(json_mod.dumps({
        "ok": True, "error": None, "at": "2026-07-25T00:45:00", "port": 8000,
        "app_version": "1.5.0", "copy_warning": None,
    }), encoding="utf-8")
    assert "pairing needs attention" not in c.get("/autofill").text


def test_static_assets_cached_and_versioned(tmp_db):
    """014 (FR-010 perf): static assets carry a long cache lifetime and are
    referenced with a ?v=<version> buster so upgrades still invalidate."""
    from fastapi.testclient import TestClient

    from engine import APP_VERSION
    from web.main import create_app

    c = TestClient(create_app())
    css = c.get("/static/styles.css")
    assert css.status_code == 200
    assert "max-age" in css.headers.get("cache-control", "").lower()
    home = c.get("/").text
    assert f"styles.css?v={APP_VERSION}" in home


def test_fill_path_banner_states_both_paths():
    """015 (D2/FR-013): the status partial names the active path — the
    signed-out assistant window carries a warning + connect link; the
    companion path names the browser and companion version."""
    import pathlib

    html = pathlib.Path("web/templates/partials/autofill_status.html").read_text(
        encoding="utf-8")
    assert "not signed in" in html
    assert 'href="/companion"' in html
    assert "companion v" in html


def test_companion_wizard_verifies_live_per_step(tmp_db):
    """015 (FR-010): the connect page is a live wizard driven by the doctor —
    per-step verification hooks + troubleshooting mapped to observed reject
    kinds (stale pairing vs old companion) must be present."""
    import pathlib

    html = pathlib.Path("web/templates/companion.html").read_text(encoding="utf-8")
    assert "/api/companion/doctor" in html
    assert html.count("data-step=") >= 3
    assert "stale pairing" in html
    assert "reload" in html  # 4426 → reload-the-extension guidance


def test_diagnostics_page_has_companion_doctor_section(tmp_db):
    """015 (FR-014): the human-readable doctor lives on the Diagnostics page
    — the whole chain in one place, not just a JSON endpoint."""
    from fastapi.testclient import TestClient

    from web.main import create_app

    page = TestClient(create_app()).get("/diagnostics").text
    assert "Companion &amp; pairing" in page or "Companion & pairing" in page
    assert "Pairing prepared" in page
    assert "OS default browser" in page


def test_browser_mismatch_line_with_fix_action(tmp_db, monkeypatch):
    """015 (FR-019): OS-default vs preference mismatch is shown with the
    one-click OS-settings action; Auto can never mismatch."""
    import sys

    from fastapi.testclient import TestClient

    from engine import settings
    from engine.autofill import default_browser
    from web.main import create_app

    monkeypatch.setattr(default_browser, "default_channel_order",
                        lambda read_progid=None: ("msedge", "chrome"))
    c = TestClient(create_app())
    page = c.get("/autofill").text  # preference defaults to chrome → mismatch
    assert "Windows default" in page
    if sys.platform == "win32":  # FR-019: the one-click fix is Windows-only
        assert "default-apps" in page
    assert "Windows default" in c.get("/companion").text

    settings.set("PREFERRED_BROWSER", "auto")
    assert "Windows default" not in c.get("/autofill").text


def test_os_default_apps_route(tmp_db, monkeypatch):
    """015 (FR-019): the fix action opens ms-settings on Windows, 409 elsewhere."""
    import sys as sys_mod

    from fastapi.testclient import TestClient

    from web.main import create_app

    c = TestClient(create_app())
    if sys_mod.platform == "win32":
        import os as os_mod

        opened = []
        monkeypatch.setattr(os_mod, "startfile", lambda uri: opened.append(uri))
        assert c.post("/api/os/default-apps").status_code == 200
        assert opened == ["ms-settings:defaultapps"]
    else:
        assert c.post("/api/os/default-apps").status_code == 409


def test_preferred_browser_setting_roundtrip(tmp_db):
    """015 (FR-016): the setting shows in /api/settings, saves via the
    settings form, and rejects unknown values."""
    from fastapi.testclient import TestClient

    from engine import settings
    from web.main import create_app

    c = TestClient(create_app())
    assert c.get("/api/settings").json()["preferred_browser"] == "chrome"
    c.post("/api/settings", data={"preferred_browser": "msedge"})
    assert settings.get("PREFERRED_BROWSER") == "msedge"
    c.post("/api/settings", data={"preferred_browser": "lynx"})
    assert settings.get("PREFERRED_BROWSER") == "msedge"  # unknown ignored


def test_app_js_notes_open_substitution():
    """015 (FR-017): the opened_with substitution is surfaced via the toast
    pattern — never a silent different-browser open."""
    import pathlib

    js = pathlib.Path("web/static/app.js").read_text(encoding="utf-8")
    assert "opened_with" in js


def test_practice_form_covers_choice_controls(tmp_db):
    """016 (T014): the practice fixture exercises everything US2 ships —
    radio group with a legend question, maxlength field, EEO question, and
    a submit-click log so the E2E can assert ZERO automated submit clicks."""
    from fastapi.testclient import TestClient

    from web.main import create_app

    page = TestClient(create_app()).get("/practice/apply").text
    assert "Will you now or in the future require sponsorship?" in page
    assert 'type="radio"' in page and "<legend" in page
    assert 'maxlength="10"' in page
    assert "eeo_gender" in page
    assert "/practice/submit-log" in page


def test_practice_posting_fixture_with_apply_opener(tmp_db):
    """016 (T014): a Greenhouse-shaped posting whose form is hidden until
    the Apply control is clicked; ?newtab=1 opens the form in a child tab
    (the watch-transfer E2E case)."""
    from fastapi.testclient import TestClient

    from web.main import create_app

    client = TestClient(create_app())
    page = client.get("/practice/posting").text
    assert 'id="apply_button"' in page
    assert 'id="application"' in page and "hidden" in page
    newtab = client.get("/practice/posting?newtab=1").text
    assert 'target="_blank"' in newtab

    assert client.post("/practice/submit-log").status_code == 200
    assert client.get("/practice/submit-log").json()["clicks"] == 1


def test_tailor_button_sets_honest_expectations():
    """016 (T021/FR-022): the tailor buttons show a can-take-minutes
    in-progress state and render the failure reason (never a dead app)."""
    import pathlib

    html = pathlib.Path("web/templates/job_detail.html").read_text(
        encoding="utf-8")
    assert html.count("can take a few minutes") >= 2  # first-run + regenerate
    assert 'role="alert"' in html


def test_tailor_selftest_endpoint_reports_verdict(tmp_db, monkeypatch):
    """016 (T023): the tailor selftest returns a verdict (never a 500) and
    names the isolation mode — the frozen smoke gates on it."""
    from fastapi.testclient import TestClient

    from engine import tailor
    from web.main import create_app

    monkeypatch.setattr(tailor, "tailor_for_job",
                        lambda *a, **k: None)  # completed, unparsed
    body = TestClient(create_app()).get(
        "/api/diagnostics/tailor-selftest").json()
    assert body["completed"] is True
    assert body["parsed"] is False
    assert isinstance(body["isolated"], bool)


class TestPracticeFixture017:
    """017-T001/T002: the practice application reproduces the shapes that
    failed on the live Akuna form, and reports enough for the E2E to prove
    each defect is dead."""

    @pytest.fixture()
    def client(self, tmp_db):
        from fastapi.testclient import TestClient

        from web.main import create_app

        return TestClient(create_app())

    def test_it_carries_every_reported_shape(self, client):
        body = client.get("/practice/apply").text
        for marker in (
            'id="their_name"',            # "please list THEIR name"
            'id="phonetic_name"',         # "pronounced phonetically"
            'id="work_auth_expiry"',      # free text asking WHEN it expires
            'id="gender_select"',         # worded Man/Woman, not Male/Female
            'id="country"',               # left blank on the live run
            'name="pronouns"',            # checkbox group sharing one question
            'class="select__control"',    # React-select wrapper
            'class="select__input"',      # its nested search input
        ):
            assert marker in body, marker

    def test_the_acknowledgement_is_the_binding_one(self, client):
        body = client.get("/practice/apply").text
        assert "will not be considered for other Tech" in body
        assert "acknowledge that this role is my top" in body

    def test_the_beacon_reports_what_the_e2e_must_assert(self, client):
        body = client.get("/practice/apply").text
        for key in ("resume_filename", "resume_size", "their_name",
                    "phonetic_name", "work_auth_expiry", "country",
                    "gender_value", "ack_typed", "pronouns_checked"):
            assert key in body, key

    def test_the_submit_control_is_still_only_practice(self, client):
        body = client.get("/practice/apply").text
        assert "only practice" in body
        assert "/practice/submit-log" in body


class TestJobDetailStartsInPlace018:
    """018 (FR-034): starting Apply Assist from a job used to redirect to
    /autofill, which threw the applicant out of the job they were reading and
    into the app — then they had to switch to the browser anyway, where the
    filling actually happens."""

    def _page(self, tmp_db):
        from fastapi.testclient import TestClient

        from engine import db
        from web.main import create_app

        db.upsert_job({
            "title": "Verification Engineer", "company": "Aurora",
            "url": "https://boards.greenhouse.io/aurora/jobs/1",
            "source": "greenhouse", "location": "Austin, TX",
            "is_remote": False, "description": "d", "posted_date": None,
        })
        with db._conn() as conn:
            job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
        return TestClient(create_app()).get(f"/jobs/{job_id}").text

    def test_it_does_not_navigate_to_the_apply_assist_page(self, tmp_db):
        """A LINK to Apply Assist is fine and stays in the nav — what must be
        gone is the automatic redirect after a successful start."""
        html = self._page(tmp_db)
        for redirect in ("window.location.href = \"/autofill\"",
                         "window.location.href='/autofill'",
                         "location.href = \"/autofill\"",
                         "location.replace(\"/autofill\")"):
            assert redirect not in html, f"still redirects: {redirect}"

    def test_it_reports_status_in_place(self, tmp_db):
        html = self._page(tmp_db)
        assert 'id="assist-status"' in html
        assert "/api/autofill/apply/" in html
        assert "Switch to your browser" in html


class TestFeedScoreKind020:
    """020 (FR-003, guarantee P1): the feed must show whether a score is a
    quick keyword match or a full AI assessment.

    This rendering existed before 020 (partials/feed_table.html) but had no
    test. It becomes load-bearing here: after this release MOST scores are
    keyword-derived, so presenting one the way an AI judgement is presented
    would be a quiet overclaim — and it is the reason ranking everything with
    the keyword matcher is acceptable at all.
    """

    @staticmethod
    def _seed_one(url, title, score, method):
        import json

        from engine import db

        db.upsert_job({
            "title": title, "company": f"Co {title}", "url": url,
            "source": "greenhouse", "location": "Remote", "is_remote": True,
            "description": "python c++", "posted_date": "2026-07-30",
        })
        with db._conn() as conn:
            conn.execute("UPDATE jobs SET is_entry_level = 1,"
                         " sponsorship = 'UNKNOWN', delisted = 0"
                         " WHERE url = ?", (url,))
            row = conn.execute("SELECT id FROM jobs WHERE url = ?",
                               (url,)).fetchone()
        db.set_match(row["id"], score,
                     json.dumps({"match_score": score, "reasoning": "r",
                                 "method": method}))
        return row["id"]

    @staticmethod
    def _score_cells(html: str) -> list[str]:
        """The rendered contents of every score cell, in order.

        022: the cell became `.score-cell` holding the provenance stamp. The
        `~`/`•` prefix these tests were written against is gone, replaced by
        a ring style plus a readable phrase — a stronger version of the same
        guarantee. The assertions below are re-pointed at the new mechanism;
        every guarantee they made is still made.
        """
        import re

        return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()
                for cell in
                re.findall(r'<td class="score-cell"[^>]*>(.*?)</td>', html,
                           re.S)]

    def test_quick_and_ai_scores_are_visually_distinguishable(self, tmp_db):
        from fastapi.testclient import TestClient

        from web.main import create_app

        self._seed_one("https://x.example/quick", "Engineer Quick", 61.0,
                       "basic")
        self._seed_one("https://x.example/assessed", "Engineer Assessed", 61.0,
                       "local")

        html = TestClient(create_app()).get("/?window=all").text
        cells = self._score_cells(html)

        assert len(cells) == 2, cells
        # identical numbers, so any difference must come from the tier marker
        assert cells[0] != cells[1], cells
        assert {"61 keyword match", "61 scored on this computer"}             == set(cells), cells
        # and the difference is not colour alone (022 FR-016)
        assert "stamp--pencil" in html and "stamp--ink" in html

    def test_the_marker_explains_itself_on_hover(self, tmp_db):
        """A bare glyph is not an explanation — the cell has to say what it
        means, or the distinction is decorative."""
        from fastapi.testclient import TestClient

        from web.main import create_app

        self._seed_one("https://x.example/quick", "Engineer Quick", 61.0,
                       "basic")
        html = TestClient(create_app()).get("/?window=all").text

        cell = re.search(r'<td class="score-cell".*?</td>', html,
                         re.S).group(0)
        assert "title=" in cell
        assert "keyword" in cell.lower()

    def test_an_unscored_job_shows_a_dash_not_a_zero(self, tmp_db):
        """Pre-020 behaviour that must survive: after this release an eligible
        job should never be unscored, but an INELIGIBLE one still can be, and
        it must not read as a score of 0."""
        from fastapi.testclient import TestClient

        from engine import db
        from web.main import create_app

        db.upsert_job({
            "title": "Engineer Unscored", "company": "Co",
            "url": "https://x.example/none", "source": "greenhouse",
            "location": "Remote", "is_remote": True, "description": "d",
            "posted_date": "2026-07-30",
        })
        with db._conn() as conn:
            conn.execute("UPDATE jobs SET is_entry_level = 1,"
                         " sponsorship = 'UNKNOWN', delisted = 0")

        html = TestClient(create_app()).get("/?window=all").text
        cells = self._score_cells(html)
        assert cells, "the job did not reach the feed at all"
        assert "—" in cells[0], cells


def test_startup_does_not_start_an_assessment_pass_020(monkeypatch, tmp_db):
    """020: the assessment pass is started by the REFRESH, never by startup.

    A startup trigger was tried and removed. It made the frozen app fail
    desktop.py's `wait_until_ready` — the packaged smoke reproduced it three
    times and passed three times with the pass suppressed. Startup is the one
    moment the app cannot afford extra contention, and nothing is lost: the
    feed posts /api/refresh on every load, so the next refresh outside the
    cooldown starts a pass.

    Pinned so it does not get "helpfully" re-added.
    """
    from fastapi.testclient import TestClient

    from engine import upgrade
    from web import main as webmain

    started = []
    monkeypatch.setattr(upgrade, "start",
                        lambda reason="refresh": started.append(reason))
    monkeypatch.setattr(webmain, "_bootstrap_sponsorship", lambda: None)
    from engine import updates
    monkeypatch.setattr(updates, "startup_check", lambda: None)

    with TestClient(webmain.create_app()):
        pass

    assert started == [], f"startup started an assessment pass: {started}"
