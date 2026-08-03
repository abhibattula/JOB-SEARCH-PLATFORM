"""019 (T053): a credential secret exists in exactly one place.

The OS keychain holds it; it travels over localhost to be typed into the
page; and that is all. This suite drives a full credential session through
the real message path and then hunts the planted password everywhere it
could have leaked: the database, extension storage, logs, the fill report,
the on-page answers feed, the doctor snapshot, and the message models' own
repr.

The first test is the important one: it proves the SCANNER works by
planting a leak and requiring it to be caught. A hygiene suite that cannot
fail is worth nothing.
"""
import json
import logging

import pytest

from engine import db
from engine.autofill import browser_controller as bc
from engine.autofill import ext_backend, ext_protocol, page_answers

SECRET = "Zq7-canary-PASSWORD-4419"
EMAIL = "canary@example.com"
DOMAIN = "wd5.myworkdayjobs.com"


def _scan(blob) -> list[str]:
    """Every place the secret appears in an arbitrary structure.

    `default=str` is not enough: several of these structures are keyed by
    tuples (the ledger, the in-flight map), which json refuses outright. A
    hygiene scanner that raises on the very structures most likely to hold
    a leaked secret would be worse than useless, so fall back to repr.
    """
    if isinstance(blob, str):
        text = blob
    else:
        try:
            text = json.dumps(blob, default=str)
        except TypeError:
            text = repr(blob)
    return [SECRET] if SECRET in text else []


@pytest.fixture
def sent():
    messages: list[dict] = []
    ext_backend.register(messages.append, lambda code: None, "1.0.0")
    yield messages
    ext_backend.reset_for_tests()


@pytest.fixture
def credential_session(tmp_db, monkeypatch, sent, caplog):
    """A real login-wall fill: vault → decision → fill message → result."""
    from engine import credentials, matcher

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
    monkeypatch.setattr(bc, "_dispatch", lambda *a, **k: None)
    monkeypatch.setattr(credentials, "get",
                        lambda domain: {"email": EMAIL, "password": SECRET})
    db.save_profile(first_name="Abhinav", email="abhi@example.com")
    db.upsert_job({"title": "SWE", "company": "Co",
                   "url": f"https://{DOMAIN}/en-US/careers/job/1",
                   "source": "manual", "description": "d",
                   "posted_date": None})
    with db._conn() as conn:
        job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    bc.start_queue([job_id])
    with bc._lock:
        bc._state.backend = "extension"

    ext_backend.open_job(job_id, f"https://{DOMAIN}/en-US/careers/job/1")
    req_id = next(m["req_id"] for m in reversed(sent)
                  if m["type"] == "open_tab")
    ext_backend.handle_message(ext_protocol.TabOpened(req_id=req_id,
                                                      tab_id=40))
    caplog.set_level(logging.DEBUG)

    def field(**over):
        base = {"je_idx": "1", "doc": "wall", "tag": "input", "type": "text",
                "name": "email", "id": "email", "label_text": "Email Address",
                "autocomplete": "username", "form_context": "login",
                "visible": True}
        base.update(over)
        return ext_protocol.Descriptor(**base)

    ext_backend.handle_message(ext_protocol.Fields(
        tab_id=40, frame_id=0, url=f"https://{DOMAIN}/en-US/login",
        doc="wall",
        descriptors=[field(),
                     field(je_idx="2", type="password", name="password",
                           id="password", label_text="Password",
                           autocomplete="current-password")]))
    ext_backend.handle_message(ext_protocol.FillResult(
        tab_id=40, frame_id=0,
        items=[{"je_idx": "1", "outcome": "filled"},
               {"je_idx": "2", "outcome": "filled"}]))
    return {"job_id": job_id, "sent": sent, "caplog": caplog}


class TestTheScannerActuallyWorks:
    """A hygiene suite that cannot fail proves nothing."""

    def test_a_planted_leak_is_caught(self):
        assert _scan({"anything": f"prefix {SECRET} suffix"}) == [SECRET]
        assert _scan(f"a log line containing {SECRET}") == [SECRET]

    def test_clean_material_passes(self):
        assert _scan({"password": "•••", "email": EMAIL}) == []


class TestTheSecretStaysInTheVault:
    def test_it_is_filled_into_the_page_and_nowhere_else(
            self, credential_session):
        """It MUST reach the page — that is the point — but only there."""
        fills = [m for m in credential_session["sent"] if m["type"] == "fill"]
        secret_items = [i for m in fills for i in m["items"]
                        if i.get("kind") == "secret"]
        assert secret_items, "the password never reached the page at all"
        assert secret_items[0]["value"] == SECRET

    def test_it_never_reaches_the_answers_feed(self, credential_session):
        answers = [m for m in credential_session["sent"]
                   if m["type"] == "answers"]
        assert not _scan(answers), "the secret is in the on-page feed"

    def test_it_never_reaches_the_overlay_state(self, credential_session):
        overlays = [m for m in credential_session["sent"]
                    if m["type"] == "overlay_state"]
        assert not _scan(overlays)

    def test_it_never_reaches_the_fill_report(self, credential_session):
        with bc._lock:
            reports = bc._state.fill_reports.get(
                credential_session["job_id"], [])
        assert reports, "no fill was recorded at all"
        assert not _scan(reports), "the secret is in the fill report"
        assert any(e.get("value_preview") == "•••" for e in reports), (
            "a password's preview must be masked, not merely absent")

    def test_it_never_reaches_the_logs(self, credential_session):
        assert not _scan(credential_session["caplog"].text)

    def test_it_never_reaches_the_database(self, credential_session):
        with db._conn() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
                assert not _scan([dict(r) for r in rows]), (
                    f"the secret is in the {table} table")

    def test_it_never_reaches_the_doctor(self, credential_session):
        assert not _scan(ext_backend.counters())
        assert not _scan(ext_backend.status())
        assert not _scan(ext_backend.progression_clicks())

    def test_it_never_reaches_the_page_answer_index(self, credential_session):
        assert not _scan(ext_backend._page_entries)
        built = page_answers.build(
            list(ext_backend._page_entries.get(
                credential_session["job_id"], {}).values()))
        assert not _scan(built)


class TestTheModelsMaskThemselves:
    """Belt and braces: even a careless f-string cannot leak one."""

    def test_credential_save_repr_masks_both_halves(self):
        msg = ext_protocol.CredentialSave(
            tab_id=1, domain=DOMAIN, email=EMAIL, password=SECRET)
        assert not _scan(repr(msg))
        assert not _scan(f"{msg}")
        assert EMAIL not in repr(msg)

    def test_fill_item_repr_masks_a_secret(self):
        item = ext_protocol.FillItem(je_idx="2", kind="secret", value=SECRET)
        assert not _scan(repr(msg := item))
        assert not _scan(f"{msg}")


class TestCredentialSaveDoesNotEcho:
    def test_saving_returns_no_secret_and_logs_none(self, tmp_db, sent,
                                                    monkeypatch, caplog):
        from engine import credentials

        monkeypatch.setattr(credentials, "save", lambda d, e, p: None)
        caplog.set_level(logging.DEBUG)
        ext_backend.handle_message(ext_protocol.CredentialSave(
            tab_id=40, domain=DOMAIN, email=EMAIL, password=SECRET))
        assert not _scan(sent), "the ack carried the secret back"
        assert not _scan(caplog.text)
        assert EMAIL not in json.dumps(sent), (
            "the identifier is credential material too")


class TestThePageReportCarriesNoSecret:
    """021 (FR-002): a new surface, so a new hunt.

    A page report is meant to be attached to a bug report unmodified. That is
    only safe if it is provably free of what the applicant typed — including
    the password that was in the very field being described.
    """

    def test_the_report_never_carries_the_secret(self, credential_session,
                                                 tmp_path, monkeypatch):
        from engine import paths

        monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
        ext_backend.handle_message(ext_protocol.PageReport(
            tab_id=40, frame_id=0, url=f"https://{DOMAIN}/en-US/login"))

        written = list((tmp_path / "reports").glob("page-*.json"))
        assert written, "no report was written — this test proves nothing"
        assert _scan(written[0].read_text(encoding="utf-8")) == []

    def test_the_report_still_describes_the_credential_fields(
            self, credential_session, tmp_path, monkeypatch):
        """The paired half. Without it, the test above passes against a
        report that describes nothing at all."""
        from engine import paths

        monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
        ext_backend.handle_message(ext_protocol.PageReport(
            tab_id=40, frame_id=0, url=f"https://{DOMAIN}/en-US/login"))

        report = json.loads(
            list((tmp_path / "reports").glob("page-*.json"))[0]
            .read_text(encoding="utf-8"))
        types = [f["type"] for f in report["fields"]]
        assert "password" in types, "the password FIELD must still be visible"
        password_field = next(f for f in report["fields"]
                              if f["type"] == "password")
        assert password_field["label_text"] == "Password"
        # It was empty when scanned — that is WHY it was filled. `has_value`
        # reports the scan, not the fill, and reporting otherwise would send
        # a reader hunting for a value that was never on the page.
        assert password_field["has_value"] is False
        assert password_field["decision"] == "fill"
        assert password_field["tag_classified"] == "login_password"

    def test_the_saved_notice_carries_no_secret(self, credential_session,
                                                tmp_path, monkeypatch):
        """Scoped to the report's own message. The secret legitimately
        travels in the `fill` message — that is how it reaches the field —
        and `test_it_is_filled_into_the_page_and_nowhere_else` above is what
        guards that path."""
        from engine import paths

        monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
        ext_backend.handle_message(ext_protocol.PageReport(
            tab_id=40, frame_id=0, url=f"https://{DOMAIN}/en-US/login"))
        notices = [m for m in credential_session["sent"]
                   if m["type"] == "page_report_saved"]
        assert notices, "the applicant must hear back"
        assert _scan(notices) == []

    def test_writing_a_report_logs_no_secret(self, credential_session,
                                             tmp_path, monkeypatch):
        from engine import paths

        monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
        ext_backend.handle_message(ext_protocol.PageReport(
            tab_id=40, frame_id=0, url=f"https://{DOMAIN}/en-US/login"))
        assert _scan(credential_session["caplog"].text) == []

    def test_the_in_memory_shape_index_is_dropped_with_the_session(
            self, credential_session, tmp_path, monkeypatch):
        """The report is built from `_page_shape`, which holds raw descriptors
        — values and all. It must not outlive the session that made it."""
        ext_backend.reset_for_tests()
        assert ext_backend._page_shape == {}
