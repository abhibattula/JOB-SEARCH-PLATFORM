"""010 T007: the extension fill backend — command translation, inbound
scan→decision→fill batches, result recording into the shared facade state,
and the secret-handling guarantees. All through a fake sender; no browser,
no sockets."""
import json
import logging

import pytest

from engine import db
from engine.autofill import browser_controller as bc
from engine.autofill import ext_backend, ext_protocol


@pytest.fixture
def sent():
    """Register a fake companion session; capture every outbound message."""
    messages: list[dict] = []
    ext_backend.register(messages.append, lambda code: None, "1.0.0")
    return messages


@pytest.fixture
def queue(tmp_db, monkeypatch, sent):
    """A running one-job queue on the extension backend with the Playwright
    dispatch seam stubbed out."""
    monkeypatch.setattr(bc, "_dispatch", lambda *a, **k: None)
    # dev machines have the real bundled model in models/ — force the basic
    # tier or answer_bank.suggest runs REAL local inference mid-test
    from engine import matcher

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
    db.save_profile(first_name="Abhinav", last_name="Battula",
                    email="abhi@example.com", phone="5125550100")
    db.upsert_job({
        "title": "Verification Engineer", "company": "Figma",
        "url": "https://boards.greenhouse.io/figma/jobs/77",
        "source": "greenhouse", "location": "SF", "is_remote": False,
        "description": "d", "posted_date": None,
    })
    with db._conn() as conn:
        job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    bc.start_queue([job_id])
    with bc._lock:
        bc._state.backend = "extension"
    sent.clear()  # drop any startup traffic; tests assert from here
    return job_id


def descriptor(**overrides):
    d = {
        "je_idx": "1", "doc": "docA", "tag": "input", "type": "text",
        "name": "first_name", "id": "first_name",
        "label_text": "First name", "placeholder": "", "aria_label": "",
        "autocomplete": "", "value": "", "options": [], "maxlength": None,
        "focused": False, "visible": True,
    }
    d.update(overrides)
    return d


def fields_msg(job_url="https://boards.greenhouse.io/figma/jobs/77",
               tab_id=40, frame_id=0, doc="docA", descriptors=()):
    return ext_protocol.Fields(
        tab_id=tab_id, frame_id=frame_id, url=job_url, doc=doc,
        descriptors=[ext_protocol.Descriptor(**d) for d in descriptors],
    )


def open_the_tab(job_id, sent, tab_id=40):
    """Complete the open_tab → tab_opened → watch_start handshake."""
    ext_backend.open_job(job_id, "https://boards.greenhouse.io/figma/jobs/77")
    req_id = next(m["req_id"] for m in reversed(sent)
                  if m["type"] == "open_tab")
    ext_backend.handle_message(ext_protocol.TabOpened(req_id=req_id, tab_id=tab_id))


class TestCommandFlow:
    def test_open_job_sends_open_tab_then_watch_start(self, queue, sent):
        open_the_tab(queue, sent)
        types = [m["type"] for m in sent]
        assert types[0] == "open_tab"
        assert "watch_start" in types
        watch = next(m for m in sent if m["type"] == "watch_start")
        assert watch["tab_id"] == 40 and watch["job_id"] == queue

    def test_close_current_sends_close_tab(self, queue, sent):
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.close_current()
        assert [m["type"] for m in sent] == ["close_tab"]


class TestScanToFill:
    def test_scan_produces_fill_batch_and_overlay(self, queue, sent):
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(),  # first_name, empty -> fill
            descriptor(je_idx="2", name="last_name", id="last_name",
                       label_text="Last name", value="Prefilled"),  # sacred
            descriptor(je_idx="3", name="zz_mystery", id="",
                       label_text="Mystery"),  # no classification -> pending/skip
        ]))
        fill = next(m for m in sent if m["type"] == "fill")
        assert [i["je_idx"] for i in fill["items"]] == ["1"]
        assert fill["items"][0]["value"] == "Abhinav"
        overlay = next(m for m in sent if m["type"] == "overlay_state")
        assert overlay["summary"]["seen"] == 3
        report = bc._state.fill_reports.get(queue) or []
        assert any(e["outcome"] == "skipped_existing" for e in report)

    def test_fill_result_records_and_settles_ledger(self, queue, sent):
        open_the_tab(queue, sent)
        ext_backend.handle_message(fields_msg(descriptors=[descriptor()]))
        ext_backend.handle_message(ext_protocol.FillResult(
            tab_id=40, frame_id=0,
            items=[{"je_idx": "1", "outcome": "filled"}],
        ))
        report = bc._state.fill_reports[queue]
        assert any(e["outcome"] == "filled" and e["value_preview"] == "Abhinav"
                   for e in report)
        assert bc._state.handled[queue][("docA", "1")] == "filled"
        assert bc._state.activity["fields_filled"] == 1

    def test_rescan_while_inflight_never_double_fills(self, queue, sent):
        open_the_tab(queue, sent)
        msg = fields_msg(descriptors=[descriptor()])
        ext_backend.handle_message(msg)
        ext_backend.handle_message(msg)  # re-scan before any fill_result
        fills = [m for m in sent if m["type"] == "fill"]
        assert len(fills) == 1

    def test_retryable_result_allows_next_scan_to_retry(self, queue, sent):
        open_the_tab(queue, sent)
        msg = fields_msg(descriptors=[descriptor()])
        ext_backend.handle_message(msg)
        ext_backend.handle_message(ext_protocol.FillResult(
            tab_id=40, frame_id=0,
            items=[{"je_idx": "1", "outcome": "focused"}],
        ))
        assert ("docA", "1") not in bc._state.handled[queue]
        ext_backend.handle_message(msg)
        assert len([m for m in sent if m["type"] == "fill"]) == 2

    def test_file_fill_travels_as_one_time_token_url(self, queue, sent, tmp_path):
        pdf = tmp_path / "resume.pdf"
        pdf.write_bytes(b"%PDF")
        db.save_profile(resume_file_path=str(pdf))
        open_the_tab(queue, sent)
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(je_idx="9", type="file", name="resume",
                       id="resume", label_text="Resume", visible=False),
        ]))
        fill = next(m for m in sent if m["type"] == "fill")
        item = fill["items"][0]
        assert item["kind"] == "file"
        assert "/api/bridge/file/" in item["file_url"]
        token = item["file_url"].rsplit("/", 1)[-1]
        assert ext_backend.consume_file_token(token) == str(pdf)


class TestSecrets:
    def _saved(self, domain="boards.greenhouse.io"):
        return {"email": "abhi@example.com", "password": "hunter2"}

    def test_secret_sent_only_for_matching_frame_domain(self, queue, sent,
                                                        monkeypatch, caplog):
        from engine import credentials

        monkeypatch.setattr(credentials, "get",
                            lambda domain: self._saved()
                            if domain == "boards.greenhouse.io" else None)
        open_the_tab(queue, sent)
        caplog.set_level(logging.DEBUG)
        pw = descriptor(je_idx="7", type="password", name="password",
                        id="password", label_text="Password",
                        autocomplete="current-password")
        # matching frame domain -> secret item
        ext_backend.handle_message(fields_msg(descriptors=[pw]))
        fill = next(m for m in sent if m["type"] == "fill")
        assert fill["items"][0]["kind"] == "secret"
        assert fill["items"][0]["value"] == "hunter2"
        # mismatched frame domain -> nothing sent for the password
        sent.clear()
        ext_backend.handle_message(fields_msg(
            job_url="https://evil.example.com/login", frame_id=2,
            doc="docEvil", descriptors=[pw]))
        assert not [m for m in sent if m["type"] == "fill"]
        # the secret never reaches logs, reports, or snapshots
        assert "hunter2" not in caplog.text
        assert "hunter2" not in json.dumps(bc.queue_snapshot())

    def test_filled_password_masked_in_report(self, queue, sent, monkeypatch):
        from engine import credentials

        monkeypatch.setattr(credentials, "get", lambda domain: self._saved())
        open_the_tab(queue, sent)
        pw = descriptor(je_idx="7", type="password", name="password",
                        id="password", label_text="Password",
                        autocomplete="current-password")
        ext_backend.handle_message(fields_msg(descriptors=[pw]))
        ext_backend.handle_message(ext_protocol.FillResult(
            tab_id=40, frame_id=0,
            items=[{"je_idx": "7", "outcome": "filled"}],
        ))
        entry = next(e for e in bc._state.fill_reports[queue]
                     if e["outcome"] == "filled")
        assert entry["value_preview"] == "•••"
        assert "hunter2" not in json.dumps(bc._state.fill_reports)


class TestPageEvents:
    def test_tab_closed_marks_interrupted(self, queue, sent):
        open_the_tab(queue, sent)
        ext_backend.handle_message(ext_protocol.PageEvent(
            tab_id=40, kind="tab_closed"))
        assert bc._state.interrupted is True

    def test_other_tabs_events_ignored(self, queue, sent):
        open_the_tab(queue, sent)
        ext_backend.handle_message(ext_protocol.PageEvent(
            tab_id=999, kind="tab_closed"))
        assert bc._state.interrupted is False

    def test_submit_detected_queues_confirmation(self, queue, sent):
        open_the_tab(queue, sent)
        ext_backend.handle_message(ext_protocol.PageEvent(
            tab_id=40, kind="submit_detected",
            url="https://boards.greenhouse.io/figma/confirmation"))
        pending = ext_backend.pending_submissions()
        assert pending and pending[0]["job_id"] == queue

    def test_frame_gone_is_harmless(self, queue, sent):
        open_the_tab(queue, sent)
        ext_backend.handle_message(fields_msg(descriptors=[descriptor()]))
        ext_backend.handle_message(ext_protocol.PageEvent(
            tab_id=40, kind="frame_gone"))
        assert bc._state.interrupted is False


class TestWidgetFills011:
    """011: custom dropdown + typeahead fill items, and the C1 sensitive-
    question-as-combobox safety."""

    def test_custom_combobox_emits_combobox_item(self, queue, sent):
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(je_idx="8", tag="div", type="", name="source",
                       label_text="How did you hear about us?",
                       widget="custom_combobox", options=["LinkedIn", "Friend"]),
        ]))
        # profile has no how_heard answer, so this only fills if the answer
        # bank has it — seed one via the app path is overkill; assert the
        # SHAPE when a value exists by using a field the profile answers:
        # first_name as a (contrived) combobox
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(je_idx="9", tag="div", type="", name="first_name",
                       label_text="First name", widget="custom_combobox",
                       options=["Abhinav", "Other"]),
        ]))
        fill = next(m for m in sent if m["type"] == "fill"
                    and any(i.get("kind") == "combobox" for i in m["items"]))
        item = next(i for i in fill["items"] if i["kind"] == "combobox")
        assert item["option_label"] == "Abhinav"

    def test_typeahead_emits_typeahead_item(self, queue, sent, monkeypatch):
        from engine.autofill import answer_bank
        monkeypatch.setattr(answer_bank, "lookup",
                            lambda q: {"answer": "Austin, TX"})
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(je_idx="7", tag="input", type="text", name="city",
                       id="city", label_text="City", widget="typeahead"),
        ]))
        fill = next(m for m in sent if m["type"] == "fill")
        item = next(i for i in fill["items"] if i["je_idx"] == "7")
        assert item["kind"] == "typeahead" and item["value"] == "Austin, TX"

    def test_c1_sensitive_combobox_no_answer_sends_no_fill(self, queue, sent):
        # a work-auth CUSTOM COMBOBOX with no saved answer must raise the
        # pending confirmation and send NO fill item — never an AI draft,
        # exactly like the native-select sensitive path.
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(je_idx="6", tag="div", type="", name="work_auth",
                       id="work_auth",
                       label_text="Are you legally authorized to work in the US?",
                       widget="custom_combobox", options=["Yes", "No"]),
        ]))
        # no fill item for the sensitive combobox
        for m in sent:
            if m["type"] == "fill":
                assert not any(i["je_idx"] == "6" for i in m["items"])
        # and it is surfaced for confirmation
        assert bc._state.pending is not None
        assert bc._state.pending["category"] == "work_authorization"


class TestAdHocFillHere:
    """010 FR-004a: 'Fill this page' on whatever the user is browsing."""

    @pytest.fixture
    def idle(self, tmp_db, monkeypatch, sent):
        monkeypatch.setattr(bc, "_dispatch", lambda *a, **k: None)
        from engine import matcher

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        db.save_profile(first_name="Abhinav", last_name="Battula",
                        email="abhi@example.com")
        sent.clear()

    def test_fill_here_starts_adhoc_session_and_watches(self, idle, sent):
        ext_backend.handle_message(ext_protocol.FillHere(
            tab_id=55, url="https://jobs.lever.co/acme/123/apply",
            title="Acme — Engineer"))
        assert any(m["type"] == "watch_start" and m["tab_id"] == 55
                   for m in sent)
        assert bc.queue_snapshot()["backend"] == "extension"

    def test_adhoc_fills_and_reports(self, idle, sent):
        ext_backend.handle_message(ext_protocol.FillHere(
            tab_id=55, url="https://jobs.lever.co/acme/123/apply", title="Acme"))
        ext_backend.handle_message(ext_protocol.Fields(
            tab_id=55, frame_id=0, url="https://jobs.lever.co/acme/123/apply",
            doc="adhoc1",
            descriptors=[ext_protocol.Descriptor(**descriptor())]))
        fill = next(m for m in sent if m["type"] == "fill")
        assert fill["items"][0]["value"] == "Abhinav"

    def test_fill_here_refused_while_queue_filling(self, queue, sent):
        # a queued job is active; an ad-hoc request must be refused
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(ext_protocol.FillHere(
            tab_id=77, url="https://x.example/other", title="Other"))
        assert any(m["type"] == "error" for m in sent)
        assert not any(m["type"] == "watch_start" and m["tab_id"] == 77
                       for m in sent)

    def test_adhoc_link_to_existing_job_by_url(self, idle, sent):
        db.upsert_job({
            "title": "Engineer", "company": "Acme",
            "url": "https://jobs.lever.co/acme/123",
            "source": "lever", "location": "SF", "is_remote": False,
            "description": "d", "posted_date": None})
        ext_backend.handle_message(ext_protocol.FillHere(
            tab_id=55, url="https://jobs.lever.co/acme/123/apply", title="Acme"))
        linked = ext_backend.link_adhoc(tab_id=55)
        assert linked["job_id"] is not None
        job = db.get_job(linked["job_id"])
        assert "jobs.lever.co/acme/123" in job["url"]


class TestReconnectRearmsWatch:
    """Hotfix: an MV3 service worker restart wipes the extension's in-memory
    `watched` map. If the app doesn't re-send watch_start on the new
    connection, content scripts are never told to scan and filling silently
    stops mid-queue."""

    def test_reconnect_resends_watch_start(self, queue, sent):
        open_the_tab(queue, sent)
        # the worker dies and a fresh one connects
        ext_backend.unregister(sent.append)
        sent.clear()
        ext_backend.register(sent.append, lambda code: None, "1.0.1")
        watch = [m for m in sent if m["type"] == "watch_start"]
        assert watch, "reconnect did not re-arm the watch"
        assert watch[0]["tab_id"] == 40 and watch[0]["job_id"] == queue

    def test_reconnect_without_active_session_sends_nothing(self, tmp_db, sent):
        ext_backend.reset_for_tests()
        sent.clear()
        ext_backend.register(sent.append, lambda code: None, "1.0.1")
        assert not [m for m in sent if m["type"] == "watch_start"]


class TestDiscoveryProtocol012:
    """012: score_request / save_job inbound message validation."""

    def test_score_request_parses(self):
        msg = ext_protocol.parse_inbound(json.dumps({
            "v": 1, "type": "score_request", "tab_id": 7,
            "url": "https://x/1", "title": "SWE", "company": "Acme",
            "description": "python",
        }))
        assert isinstance(msg, ext_protocol.ScoreRequest)
        assert msg.tab_id == 7 and msg.company == "Acme"

    def test_save_job_parses_with_optional_location(self):
        msg = ext_protocol.parse_inbound(json.dumps({
            "v": 1, "type": "save_job", "tab_id": 7, "url": "https://x/1",
            "title": "SWE", "company": "Acme", "description": "d",
        }))
        assert isinstance(msg, ext_protocol.SaveJob)
        assert msg.location == ""

    def test_unknown_type_rejected(self):
        with pytest.raises(ext_protocol.ProtocolError):
            ext_protocol.parse_inbound(json.dumps({"v": 1, "type": "bogus"}))

    def test_oversize_rejected(self):
        big = "x" * (ext_protocol.MAX_MESSAGE_BYTES + 1)
        with pytest.raises(ext_protocol.ProtocolError):
            ext_protocol.parse_inbound(json.dumps({
                "v": 1, "type": "score_request", "tab_id": 1, "url": "u",
                "title": "t", "company": "c", "description": big,
            }))


class TestDiscoveryHandlers012:
    """012: the discovery handlers are INDEPENDENT of the fill session —
    they never read or mutate _watch / bc._state."""

    def _profile(self):
        db.save_profile(first_name="A", last_name="B", email="a@b.com",
                        resume_text="python verilog fpga", skills=[])

    def test_score_request_emits_score_result(self, tmp_db, sent):
        self._profile()
        ext_backend.handle_message(ext_protocol.ScoreRequest(
            tab_id=99, url="https://x/1", title="FPGA Engineer",
            company="Acme", description="python fpga"))
        results = [m for m in sent if m["type"] == "score_result"]
        assert results, "no score_result emitted"
        r = results[0]
        assert r["tab_id"] == 99
        assert "match_score" in r and "sponsor_grade" in r
        assert r["needs_resume"] is False
        # independence: no watch session was created
        assert ext_backend._watch["tab_id"] is None

    def test_save_job_persists_marks_saved_and_dedups(self, tmp_db, sent):
        ext_backend.handle_message(ext_protocol.SaveJob(
            tab_id=5, url="https://x/save/1", title="SWE", company="Acme",
            description="d", location="SF"))
        first = [m for m in sent if m["type"] == "save_result"][-1]
        assert first["already"] is False
        job = db.get_job_by_url("https://x/save/1")
        assert job is not None and job["status"] == "saved" and job["source"] == "manual"
        # repeat save of the same url → already, no duplicate
        sent.clear()
        ext_backend.handle_message(ext_protocol.SaveJob(
            tab_id=5, url="https://x/save/1", title="SWE", company="Acme",
            description="d", location="SF"))
        second = [m for m in sent if m["type"] == "save_result"][-1]
        assert second["already"] is True
        with db._conn() as conn:
            n = conn.execute("SELECT COUNT(*) c FROM jobs WHERE url=?",
                             ("https://x/save/1",)).fetchone()["c"]
        assert n == 1
        # independence
        assert ext_backend._watch["tab_id"] is None

    def test_save_job_cross_source_duplicate_reports_already(self, tmp_db, sent):
        # an existing job from another source, same (company,title,location)
        db.upsert_job({"title": "SWE", "company": "Acme",
                       "url": "https://greenhouse/acme/1", "source": "greenhouse",
                       "location": "SF", "description": "d", "posted_date": None})
        sent.clear()
        ext_backend.handle_message(ext_protocol.SaveJob(
            tab_id=5, url="https://linkedin/acme/9", title="SWE", company="Acme",
            description="d", location="SF"))
        res = [m for m in sent if m["type"] == "save_result"][-1]
        assert res["already"] is True
        # the cross-source dup is not duplicated
        with db._conn() as conn:
            n = conn.execute(
                "SELECT COUNT(*) c FROM jobs WHERE title='SWE'").fetchone()["c"]
        assert n == 1
