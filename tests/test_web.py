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


def test_pending_panel_has_drafting_state():
    """015 (FR-003): the pending panel renders a live 'drafting…' state while
    the background suggestion generates (never a silent empty draft)."""
    import pathlib

    html = pathlib.Path("web/templates/partials/autofill_status.html").read_text(
        encoding="utf-8")
    assert "pending.drafting" in html
    assert "drafting a suggestion" in html


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
