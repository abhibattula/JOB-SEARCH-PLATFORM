"""010 T007: the extension fill backend — command translation, inbound
scan→decision→fill batches, result recording into the shared facade state,
and the secret-handling guarantees. All through a fake sender; no browser,
no sockets."""
import json
import logging
import time

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
        # 016: a work-auth CUSTOM COMBOBOX with no profile fact must send NO
        # fill item and never reach a model — it is recorded needs-you for
        # the human (the fill-first replacement for the 015 pending gate).
        from engine.autofill import drafter

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
        # and it is surfaced for the human, not drafted
        record = drafter.get(
            queue, "Are you legally authorized to work in the US?")
        assert record is not None and record["state"] == "failed"
        assert record["reason"] == "profile_fact_missing"


class TestDecideFast016:
    """016 (T005, R1): the fields handler is decide-fast — no model call is
    reachable from handle_message; known fills dispatch incrementally while
    unknown questions draft in the background; a completed draft pushes a
    rescan nudge and the next scan fills it from the cache."""

    UNKNOWN = dict(je_idx="5", tag="textarea", type="", name="essay",
                   id="essay", label_text="Tell us why you want to join")

    @pytest.fixture(autouse=True)
    def _drafter(self):
        from engine.autofill import drafter

        drafter.reset_for_tests(backoff_base_s=0.1, backoff_cap_s=0.5)
        yield drafter
        drafter.reset_for_tests()

    @staticmethod
    def _wait(predicate, timeout=5.0):
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_no_model_call_reachable_from_handler(self, queue, sent,
                                                  monkeypatch):
        from engine import matcher, qa
        from engine.autofill import answer_bank, drafter

        def boom(*a, **k):
            raise AssertionError("model call reached from the bridge handler")

        monkeypatch.setattr(matcher, "_chat", boom)
        monkeypatch.setattr(qa, "draft", boom)
        monkeypatch.setattr(answer_bank, "suggest", boom)
        drafter.set_generator_for_tests(lambda q, c, p: None)
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(), descriptor(**self.UNKNOWN)]))
        fill = next(m for m in sent if m["type"] == "fill")
        assert any(i["value"] == "Abhinav" for i in fill["items"])
        self._wait(lambda: (drafter.get(queue, self.UNKNOWN["label_text"])
                            or {}).get("state") == "failed")

    def test_known_fills_dispatch_while_draft_still_running(self, queue, sent):
        import threading
        import time

        from engine.autofill import drafter

        release = threading.Event()
        drafter.set_generator_for_tests(
            lambda q, c, p: (release.wait(timeout=10), "late")[1])
        open_the_tab(queue, sent)
        sent.clear()
        start = time.monotonic()
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(), descriptor(**self.UNKNOWN)]))
        assert time.monotonic() - start < 1.0  # the handler never waited
        fill = next(m for m in sent if m["type"] == "fill")
        assert any(i["value"] == "Abhinav" for i in fill["items"])
        # heartbeat stays fresh while the draft is still running
        ext_backend.handle_message(ext_protocol.Pong())
        assert ext_backend.status()["last_seen_age_s"] < 1.0
        release.set()

    def test_draft_completion_pushes_rescan_then_next_scan_fills(
            self, queue, sent):
        from engine.autofill import drafter

        drafter.set_generator_for_tests(
            lambda q, c, p: "Because I love hardware.")
        open_the_tab(queue, sent)
        sent.clear()
        message = fields_msg(descriptors=[descriptor(**self.UNKNOWN)])
        ext_backend.handle_message(message)
        assert self._wait(
            lambda: any(m["type"] == "rescan" for m in sent)), \
            "completed draft never pushed a rescan nudge"
        ext_backend.handle_message(message)  # the nudged rescan arrives
        fill = [m for m in sent if m["type"] == "fill"][-1]
        item = next(i for i in fill["items"] if i["je_idx"] == "5")
        assert item["value"] == "Because I love hardware."
        assert item["flag"] == "ai_draft"

    def test_unique_question_drafts_once_across_rescans(self, queue, sent):
        from engine.autofill import drafter

        calls = []
        drafter.set_generator_for_tests(
            lambda q, c, p: calls.append(1) and None)
        open_the_tab(queue, sent)
        message = fields_msg(descriptors=[descriptor(**self.UNKNOWN)])
        for _ in range(5):
            ext_backend.handle_message(message)
        self._wait(lambda: len(calls) >= 1)
        import time

        time.sleep(0.05)  # give an (incorrect) second draft a chance
        assert len(calls) == 1


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
        # 019 (FR-004) narrowed this refusal: only a queue ACTIVELY mid-fill
        # on another tab is busy (a quiet session is superseded instead —
        # TestFillHereSupersede019 covers that side).
        import time as _time

        open_the_tab(queue, sent)
        with ext_backend._lock:
            ext_backend._inflight[(40, 0, "1")] = (
                {}, "first_name", "Abhinav", False, _time.monotonic())
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


class TestBrowserAndRejects015:
    """015 (T009): the companion session carries its browser identity, and
    rejected connection attempts are counted by kind so 'nothing knocking'
    is distinguishable from 'knocking but rejected'."""

    def test_register_stores_browser_and_status_reports_it(self):
        ext_backend.reset_for_tests()
        ext_backend.register(lambda m: None, lambda code: None, "1.5.0",
                             browser="chrome")
        status = ext_backend.status()
        assert status["connected"] is True
        assert status["browser"] == "chrome"

    def test_old_register_signature_defaults_browser_empty(self):
        ext_backend.reset_for_tests()
        ext_backend.register(lambda m: None, lambda code: None, "1.4.0")
        assert ext_backend.status()["browser"] == ""

    def test_reject_counters_by_kind(self):
        ext_backend.reset_for_tests()
        stats = ext_backend.reject_stats()
        assert stats == {"auth": 0, "protocol": 0,
                         "last_kind": None, "last_age_s": None}
        ext_backend.record_reject("auth")
        ext_backend.record_reject("auth")
        ext_backend.record_reject("protocol")
        stats = ext_backend.reject_stats()
        assert stats["auth"] == 2
        assert stats["protocol"] == 1
        assert stats["last_kind"] == "protocol"
        assert stats["last_age_s"] is not None and stats["last_age_s"] < 5

    def test_reset_clears_reject_counters(self):
        ext_backend.record_reject("auth")
        ext_backend.reset_for_tests()
        assert ext_backend.reject_stats()["auth"] == 0


class TestInflightTTL016:
    """016 (T007): a fill whose result never comes back must not block its
    field forever — in-flight entries expire (~20 s) and the next scan
    re-decides."""

    def test_expired_inflight_entry_is_retried(self, queue, sent):
        import time as time_mod

        open_the_tab(queue, sent)
        message = fields_msg(descriptors=[descriptor()])
        ext_backend.handle_message(message)
        assert len([m for m in sent if m["type"] == "fill"]) == 1
        # the fill_result never arrives; age the entry past the TTL
        with ext_backend._lock:
            for fkey, info in list(ext_backend._inflight.items()):
                ext_backend._inflight[fkey] = info[:-1] + (
                    time_mod.monotonic() - ext_backend.INFLIGHT_TTL_S - 1,)
        ext_backend.handle_message(message)
        assert len([m for m in sent if m["type"] == "fill"]) == 2

    def test_fresh_inflight_entry_still_blocks_double_fill(self, queue, sent):
        open_the_tab(queue, sent)
        message = fields_msg(descriptors=[descriptor()])
        ext_backend.handle_message(message)
        ext_backend.handle_message(message)
        assert len([m for m in sent if m["type"] == "fill"]) == 1

    def test_settled_no_match_records_epoch_tuple(self, queue, sent, monkeypatch):
        from engine.autofill import answer_bank, drafter

        monkeypatch.setattr(answer_bank, "lookup",
                            lambda q: {"answer": "A paragraph that matches "
                                       "no option at all", "source": "user"})
        open_the_tab(queue, sent)
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(je_idx="6", tag="select", type="", name="auth",
                       id="auth", label_text="Authorized?",
                       options=["Yes", "No"]),
        ]))
        entry = bc._state.handled[queue][("docA", "6")]
        assert isinstance(entry, tuple) and entry[0] == "no_match"
        assert entry[1] == drafter.cache_version()


class TestTabFollowing016:
    """016 (T008, R4): watch-transfer — a tab opened FROM the watched tab
    becomes the fill target; open_tab gets ack timeout + one retry then a
    visible launch_failed; wrong-tab fields are counted for the doctor."""

    def test_child_tab_transfers_watch(self, queue, sent):
        open_the_tab(queue, sent)  # tab 40
        sent.clear()
        ext_backend.handle_message(ext_protocol.ChildTab(
            tab_id=99, opener_tab_id=40))
        assert ext_backend._watch["tab_id"] == 99
        assert any(m["type"] == "watch_start" and m["tab_id"] == 99
                   for m in sent)
        # filling continues in the child tab
        ext_backend.handle_message(fields_msg(
            tab_id=99, doc="docB", descriptors=[descriptor(doc="docB")]))
        assert any(m["type"] == "fill" for m in sent)

    def test_child_of_unwatched_opener_ignored(self, queue, sent):
        open_the_tab(queue, sent)
        ext_backend.handle_message(ext_protocol.ChildTab(
            tab_id=99, opener_tab_id=777))
        assert ext_backend._watch["tab_id"] == 40

    def test_wrong_tab_fields_increment_doctor_counter(self, queue, sent):
        open_the_tab(queue, sent)
        before = ext_backend.counters()["dropped_fields"]
        ext_backend.handle_message(fields_msg(
            tab_id=555, descriptors=[descriptor()]))
        assert ext_backend.counters()["dropped_fields"] == before + 1

    def test_open_ack_timeout_retries_once_then_launch_failed(self, tmp_db,
                                                              sent):
        # No running queue here: the live worker thread must not race the
        # explicit check_pending_open() calls (it legitimately runs the
        # same check every ~2 s while an extension queue is active).
        ext_backend.open_job(7, "https://x.example/apply")
        assert len([m for m in sent if m["type"] == "open_tab"]) == 1

        def age_all():
            with ext_backend._lock:
                for entry in ext_backend._watch["pending_open"].values():
                    entry["deadline"] = 0.0

        age_all()
        ext_backend.check_pending_open()
        assert len([m for m in sent if m["type"] == "open_tab"]) == 2  # retry
        age_all()
        ext_backend.check_pending_open()
        assert bc._state.outcomes[7]["reason"] == "launch_failed"
        assert not ext_backend._watch["pending_open"]  # never hangs silently


class TestVersionGate016:
    """016 (T013, FR-015): new fill kinds are withheld from an old
    companion — it would text-set the radio and lie (silent mis-fill)."""

    GROUP = dict(je_idx="7", tag="input", type="radio_group",
                 name="authorized", id="auth",
                 label_text="Are you legally authorized to work in the US?",
                 options=["Yes", "No"],
                 members=[{"je_idx": "7", "label": "Yes"},
                          {"je_idx": "8", "label": "No"}])

    def _prep(self, queue, sent):
        db.save_profile(authorized_without_sponsorship="yes")
        open_the_tab(queue, sent)
        sent.clear()

    def test_old_companion_never_receives_radio_kind(self, queue, sent):
        self._prep(queue, sent)  # fixture registered version "1.0.0"
        ext_backend.handle_message(fields_msg(
            descriptors=[descriptor(**self.GROUP)]))
        for m in sent:
            if m["type"] == "fill":
                assert not any(i.get("kind") == "radio" for i in m["items"])

    def test_current_companion_receives_radio_fill(self, queue, sent,
                                                   monkeypatch):
        from engine import APP_VERSION

        self._prep(queue, sent)
        ext_backend.register(sent.append, lambda code: None, APP_VERSION)
        sent.clear()
        ext_backend.handle_message(fields_msg(
            descriptors=[descriptor(**self.GROUP)]))
        fill = next(m for m in sent if m["type"] == "fill")
        item = fill["items"][0]
        assert item["kind"] == "radio" and item["value"] == "Yes"


class TestFillAgain016:
    """016 (T016, R10): the panel's Fill again clears retryable ledger
    entries, re-arms failed drafts, and nudges a rescan — user-typed
    values stay sacred via the write-time guards."""

    def test_fill_again_clears_ledger_resets_backoff_and_nudges(
            self, queue, sent):
        from engine.autofill import drafter, field_core

        drafter.reset_for_tests(backoff_base_s=60.0)
        drafter.set_generator_for_tests(lambda q, c, p: None)  # always fails
        open_the_tab(queue, sent)
        with bc._lock:
            bc._state.handled[queue] = {
                ("docA", "1"): "filled",
                ("docA", "2"): "skipped_existing",
                ("docA", "3"): field_core.settle_entry("no_match"),
            }
        drafter.ensure(queue, "Hard question?", {"tag": "free_text_unknown",
                                                 "options": [],
                                                 "maxlength": None,
                                                 "widget": ""}, {})
        deadline_ok = False
        import time as time_mod
        for _ in range(200):
            record = drafter.get(queue, "Hard question?")
            if record and record["state"] == "failed":
                deadline_ok = True
                break
            time_mod.sleep(0.01)
        assert deadline_ok
        sent.clear()

        ext_backend.handle_message(ext_protocol.FillAgain(tab_id=40))

        ledger = bc._state.handled[queue]
        assert ("docA", "2") in ledger          # skipped_existing kept
        assert ("docA", "1") not in ledger      # re-decides (sacred rule guards)
        assert ("docA", "3") not in ledger
        record = drafter.get(queue, "Hard question?")
        assert record["next_retry_at"] == 0.0   # backoff re-armed
        assert any(m["type"] == "rescan" for m in sent)
        drafter.reset_for_tests()

    def test_fill_again_from_unwatched_tab_ignored(self, queue, sent):
        open_the_tab(queue, sent)
        with bc._lock:
            bc._state.handled[queue] = {("docA", "3"): "no_match"}
        sent.clear()
        ext_backend.handle_message(ext_protocol.FillAgain(tab_id=999))
        assert bc._state.handled[queue] == {("docA", "3"): "no_match"}
        assert not any(m["type"] == "rescan" for m in sent)


class TestAnswerCapture017:
    """017-T065 (D7, FR-045/FR-046): a question we refused becomes a question
    the applicant answers ONCE.

    Under the new refusal policy a real application leaves several questions
    for the applicant. Capturing what they type — as THEIR answer — means the
    manual effort decays across applications instead of repeating.
    """

    def _watching(self, tmp_db, monkeypatch, job_id=7):
        sent = []
        monkeypatch.setattr(ext_backend, "send", lambda payload: sent.append(payload))
        with ext_backend._lock:
            ext_backend._watch["tab_id"] = 11
            ext_backend._watch["job_id"] = job_id
        return sent

    def test_the_answer_is_stored_as_the_applicants_own(self, tmp_db,
                                                        monkeypatch):
        from engine.autofill import answer_bank, ext_protocol

        self._watching(tmp_db, monkeypatch)
        ext_backend.handle_message(ext_protocol.AnswerQuestion(
            tab_id=11, je_idx="31",
            question="Have you ever applied to Akuna in the past?",
            answer="No"))

        row = answer_bank.lookup("Have you ever applied to Akuna in the past?")
        assert row["answer"] == "No"
        assert row["source"] == "user"

    def test_it_survives_a_purge_of_model_written_answers(self, tmp_db,
                                                          monkeypatch):
        from engine.autofill import answer_bank, ext_protocol

        self._watching(tmp_db, monkeypatch)
        ext_backend.handle_message(ext_protocol.AnswerQuestion(
            tab_id=11, question="Do you live in New York or California?",
            answer="No"))

        answer_bank.purge_model_written()

        assert answer_bank.lookup(
            "Do you live in New York or California?")["answer"] == "No"

    def test_it_is_stored_verbatim(self, tmp_db, monkeypatch):
        from engine.autofill import answer_bank, ext_protocol

        self._watching(tmp_db, monkeypatch)
        typed = "Yes — 2 weeks from the offer date"
        ext_backend.handle_message(ext_protocol.AnswerQuestion(
            tab_id=11, question="What is your notice period?", answer=typed))
        assert answer_bank.lookup("What is your notice period?")["answer"] == \
            typed

    def test_the_refusal_is_cleared_and_a_rescan_requested(self, tmp_db,
                                                           monkeypatch):
        from engine.autofill import drafter, ext_protocol

        sent = self._watching(tmp_db, monkeypatch)
        drafter.mark_needs_you(7, "Any offer deadlines?", "never_generated")

        ext_backend.handle_message(ext_protocol.AnswerQuestion(
            tab_id=11, question="Any offer deadlines?", answer="No"))

        assert drafter.get(7, "Any offer deadlines?") is None
        assert any(p.get("type") == "rescan" for p in sent)

    def test_an_empty_answer_is_ignored(self, tmp_db, monkeypatch):
        from engine.autofill import answer_bank, ext_protocol

        self._watching(tmp_db, monkeypatch)
        ext_backend.handle_message(ext_protocol.AnswerQuestion(
            tab_id=11, question="Any offer deadlines?", answer="   "))
        assert answer_bank.lookup("Any offer deadlines?") is None

    def test_a_message_from_another_tab_is_ignored(self, tmp_db, monkeypatch):
        from engine.autofill import answer_bank, ext_protocol

        self._watching(tmp_db, monkeypatch)
        ext_backend.handle_message(ext_protocol.AnswerQuestion(
            tab_id=999, question="Any offer deadlines?", answer="No"))
        assert answer_bank.lookup("Any offer deadlines?") is None


class TestApplyHere017:
    """017-T070 (FR-038): the badge's Apply with Apply Assist saves the
    posting and starts a NON-ad-hoc watch on that tab, so the session is tied
    to a real job and the apply-opener is armed."""

    def test_it_saves_the_posting_and_watches_the_tab(self, tmp_db,
                                                      monkeypatch):
        from engine import db
        from engine.autofill import browser_controller, ext_protocol

        sent = []
        monkeypatch.setattr(ext_backend, "send", lambda p: sent.append(p))
        started = {}

        def fake_start(ids, adopt_tab_id=None):
            started["ids"] = ids
            started["adopt_tab_id"] = adopt_tab_id

        monkeypatch.setattr(browser_controller, "start_queue", fake_start)

        ext_backend.handle_message(ext_protocol.ApplyHere(
            tab_id=21, url="https://job-boards.greenhouse.io/akuna/jobs/6532",
            title="Software Engineer (Entry-Level) - C++",
            company="Akuna Capital", description="desc"))

        row = db.get_job_by_url(
            "https://job-boards.greenhouse.io/akuna/jobs/6532")
        assert row is not None
        assert row["status"] == "saved"
        # a REAL job id, not the -2 ad-hoc sentinel — and 019 (FR-003): the
        # session ADOPTS the pressed tab (watch_start itself is exercised
        # unstubbed by TestApplyHereAdopts019).
        assert started["ids"] == [row["id"]]
        assert row["id"] > 0
        assert started["adopt_tab_id"] == 21

    def test_a_failure_to_start_is_surfaced_not_swallowed(self, tmp_db,
                                                          monkeypatch):
        from engine.autofill import browser_controller, ext_protocol

        sent = []
        monkeypatch.setattr(ext_backend, "send", lambda p: sent.append(p))

        def boom(_ids, adopt_tab_id=None):
            raise RuntimeError("no browser")

        monkeypatch.setattr(browser_controller, "start_queue", boom)

        ext_backend.handle_message(ext_protocol.ApplyHere(
            tab_id=21, url="https://x.example/apply-here-fail", title="T",
            company="C"))

        errors = [p for p in sent if p.get("type") == "error"]
        assert errors and "no browser" in errors[0]["message"]


class TestAnswersFeed018:
    """018 US3 (FR-019/FR-020/FR-027): what reaches the page.

    Through v1.7.0 the `answers` payload came from `drafter.answers_for_page`,
    which reads `drafter._records` — only questions routed to the AI drafter.
    Every field resolved from the profile or the answer bank was invisible on
    the page, and no entry carried a `je_idx`, so the panel's Insert and Show
    me buttons never rendered at all.
    """

    def _answers(self, sent):
        return [m for m in sent if m["type"] == "answers"]

    def test_a_profile_filled_field_reaches_the_page(self, queue, sent):
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[descriptor()]))
        feed = self._answers(sent)
        assert feed, "no answers payload was sent at all"
        items = feed[-1]["items"]
        questions = [i["question"] for i in items]
        assert "First name" in questions, (
            f"a profile-filled field is missing from the feed: {questions}")
        first = next(i for i in items if i["question"] == "First name")
        assert first["answer"] == "Abhinav"
        assert first["group"] == "profile"

    def test_every_item_carries_the_field_it_belongs_to(self, queue, sent):
        """R4: without this the panel cannot offer Insert or Show me."""
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[descriptor()]))
        items = self._answers(sent)[-1]["items"]
        assert items
        assert all("je_idx" in i for i in items)
        first = next(i for i in items if i["question"] == "First name")
        assert first["je_idx"] == "1"
        assert first["key"]

    def test_an_unchanged_scan_pushes_nothing(self, queue, sent):
        """FR-027: this payload used to go out on EVERY scan — up to 400 KB
        every two seconds — and every push rebuilt the panel, which is what
        destroyed half-typed answers."""
        open_the_tab(queue, sent)
        sent.clear()
        msg = fields_msg(descriptors=[descriptor()])
        ext_backend.handle_message(msg)
        assert len(self._answers(sent)) == 1
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[descriptor()]))
        assert self._answers(sent) == [], (
            "an identical scan pushed the answer feed again")

    def test_a_changed_answer_does_push(self, queue, sent):
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[descriptor()]))
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(),
            descriptor(je_idx="2", name="email", id="email",
                       label_text="Email"),
        ]))
        assert self._answers(sent), "a new field did not reach the page"

    def test_a_secret_never_reaches_the_page(self, queue, sent):
        """FR-037: fill-and-forget. It goes into the field and is never
        rendered, logged or sent back."""
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(je_idx="9", name="password", id="password",
                       type="password", label_text="Password"),
        ]))
        for message in self._answers(sent):
            for item in message["items"]:
                assert "password" not in (item["question"] or "").lower() or \
                    item["answer"] == ""

    def test_the_feed_is_resent_after_the_applicant_answers(self, queue, sent):
        """The digest must not suppress the one push that proves their typed
        answer landed."""
        open_the_tab(queue, sent)
        ext_backend.handle_message(fields_msg(descriptors=[descriptor()]))
        sent.clear()
        ext_backend.handle_message(ext_protocol.AnswerQuestion(
            tab_id=40, je_idx="3", question="When does it expire?",
            answer="2027-05-01"))
        ext_backend.handle_message(fields_msg(descriptors=[descriptor()]))
        assert self._answers(sent), (
            "the feed stayed suppressed after a captured answer")

    def test_a_filled_field_stays_in_the_feed_after_it_is_filled(self, queue,
                                                                 sent):
        """The scan AFTER a successful fill sees a non-empty field and
        decides "skip". Recording that skip over the fill made every filled
        field vanish from the panel a second after it appeared — the profile
        group emptied itself while the applicant watched."""
        open_the_tab(queue, sent)
        ext_backend.handle_message(fields_msg(descriptors=[descriptor()]))
        sent.clear()
        # the same field, now carrying the value we just put in it
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(value="Abhinav"),
        ]))
        ext_backend.handle_message(ext_protocol.AnswerQuestion(
            tab_id=40, je_idx="1", question="ping", answer="pong"))
        ext_backend.handle_message(fields_msg(descriptors=[
            descriptor(value="Abhinav"),
        ]))
        feed = [m for m in sent if m["type"] == "answers"]
        assert feed, "no answers payload after the field was filled"
        questions = [i["question"] for i in feed[-1]["items"]]
        assert "First name" in questions, (
            f"the filled field dropped out of the feed: {questions}")


class TestSessionControl018:
    """018 (FR-030/FR-032): Stop and Next from the page. No new capability —
    the same functions the app's own Apply Assist page already calls."""

    def test_stop_stops_the_queue(self, queue, sent):
        open_the_tab(queue, sent)
        assert bc._state.running
        ext_backend.handle_message(ext_protocol.SessionControl(
            tab_id=40, action="stop"))
        assert not bc._state.running

    def test_it_ignores_a_control_for_another_tab(self, queue, sent):
        """The same guard fill_again and answer_question already apply: a
        message must be about the tab we are actually watching."""
        open_the_tab(queue, sent)
        ext_backend.handle_message(ext_protocol.SessionControl(
            tab_id=999, action="stop"))
        assert bc._state.running

    def test_next_advances_the_queue(self, queue, sent):
        open_the_tab(queue, sent)
        called = []
        original = bc.advance
        try:
            bc.advance = lambda: called.append(True) or None
            ext_backend.handle_message(ext_protocol.SessionControl(
                tab_id=40, action="next"))
        finally:
            bc.advance = original
        assert called == [True]

    def test_an_unknown_action_is_refused_not_obeyed(self, queue, sent):
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(ext_protocol.SessionControl(
            tab_id=40, action="submit"))
        assert bc._state.running, "an unknown action must change nothing"
        errors = [m for m in sent if m["type"] == "error"]
        assert errors and errors[0]["code"] == "bad_action"

    def test_the_overlay_summary_carries_session_context(self, queue, sent):
        """FR-032: which job, and how many remain — so the companion can
        offer Next without the applicant opening the app."""
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(fields_msg(descriptors=[descriptor()]))
        overlay = next(m for m in sent if m["type"] == "overlay_state")
        assert overlay["summary"]["session"] == "filling"
        assert overlay["summary"]["current_job_id"] == queue
        assert overlay["summary"]["remaining"] == 0


class TestVersionSkew019:
    """019 (T004, FR-002): a version mismatch is NEVER a silent drop — the
    withheld radio fill surfaces as needs-you with the mismatch named, and
    the doctor counts it. The `sent` fixture registers version "1.0.0",
    which mismatches APP_VERSION by construction."""

    GROUP = TestVersionGate016.GROUP

    def test_mismatch_radio_is_visible_not_silent(self, queue, sent):
        db.save_profile(authorized_without_sponsorship="yes")
        open_the_tab(queue, sent)
        sent.clear()
        before = ext_backend.counters().get("version_mismatch_fills", 0)
        ext_backend.handle_message(fields_msg(
            descriptors=[descriptor(**self.GROUP)]))
        after = ext_backend.counters().get("version_mismatch_fills", 0)
        assert after == before + 1
        answers = [m for m in sent if m["type"] == "answers"]
        assert answers, "the withheld field must reach the on-page feed"
        entry = next(i for i in answers[-1]["items"]
                     if "authorized" in i["question"].lower())
        assert entry["group"] == "needs_you"
        assert entry["reason"] == "version_mismatch"

    def test_matched_version_pays_no_penalty(self, queue, sent):
        from engine import APP_VERSION

        db.save_profile(authorized_without_sponsorship="yes")
        open_the_tab(queue, sent)
        ext_backend.register(sent.append, lambda code: None, APP_VERSION)
        sent.clear()
        before = ext_backend.counters().get("version_mismatch_fills", 0)
        ext_backend.handle_message(fields_msg(
            descriptors=[descriptor(**self.GROUP)]))
        assert ext_backend.counters().get("version_mismatch_fills", 0) == before
        fill = next(m for m in sent if m["type"] == "fill")
        assert fill["items"][0]["kind"] == "radio"

    def test_version_ok_seam_for_escort_arming(self, queue, sent):
        """FR-035: the escort consults this seam and never arms on a
        mismatch."""
        assert ext_backend.version_ok() is False  # fixture version "1.0.0"
        from engine import APP_VERSION

        ext_backend.register(sent.append, lambda code: None, APP_VERSION)
        assert ext_backend.version_ok() is True


class TestApplyHereAdopts019:
    """019 (T009, FR-003): Apply-with-Apply-Assist runs in the tab the user
    pressed it on. No duplicate tab, and a stray tab_opened can never steal
    the adopted watch (the v1.8.0 bug)."""

    def _apply_here(self, sent, tab_id=55):
        ext_backend.handle_message(ext_protocol.ApplyHere(
            tab_id=tab_id, url="https://boards.greenhouse.io/x/jobs/9",
            title="SWE, New Grad", company="X Robotics", description="d"))

    def test_apply_here_never_opens_a_tab(self, tmp_db, monkeypatch, sent):
        monkeypatch.setattr(bc, "_dispatch", lambda *a, **k: None)
        from engine import matcher

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        db.save_profile(first_name="Abhinav", email="abhi@example.com")
        self._apply_here(sent)
        assert not any(m["type"] == "open_tab" for m in sent), (
            "apply_here must adopt the pressed tab, never open a duplicate")
        watch = next(m for m in sent if m["type"] == "watch_start")
        assert watch["tab_id"] == 55
        assert ext_backend._watch["tab_id"] == 55

    def test_stray_tab_opened_cannot_steal_an_adopted_watch(
            self, tmp_db, monkeypatch, sent):
        monkeypatch.setattr(bc, "_dispatch", lambda *a, **k: None)
        from engine import matcher

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        db.save_profile(first_name="Abhinav", email="abhi@example.com")
        self._apply_here(sent)
        ext_backend.handle_message(ext_protocol.TabOpened(
            req_id="stray", tab_id=99))
        assert ext_backend._watch["tab_id"] == 55


class TestFillHereSupersede019:
    """019 (T012, FR-004): Fill this page is always honoured on a fillable
    page — a quiet session is superseded; busy only while another tab is
    actively mid-fill, and then the refusal names it."""

    def test_supersedes_a_quiet_running_session(self, queue, sent):
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(ext_protocol.FillHere(
            tab_id=99, url="https://co.example/careers/apply", title="t"))
        assert not any(m["type"] == "error" and m.get("code") == "busy"
                       for m in sent)
        watch = next(m for m in sent if m["type"] == "watch_start")
        assert watch["tab_id"] == 99
        assert watch["job_id"] == ext_backend.ADHOC_JOB_ID

    def test_busy_only_while_another_tab_is_mid_fill_and_names_it(
            self, queue, sent):
        import time as _time

        open_the_tab(queue, sent)
        with ext_backend._lock:
            ext_backend._inflight[(40, 0, "1")] = (
                {}, "first_name", "Abhinav", False, _time.monotonic())
        sent.clear()
        ext_backend.handle_message(ext_protocol.FillHere(
            tab_id=99, url="https://co.example/careers/apply", title="t"))
        err = next(m for m in sent if m["type"] == "error")
        assert err["code"] == "busy"
        assert "40" in err["message"], "the refusal must name the busy tab"

    def test_same_tab_fill_here_supersedes_even_mid_fill(self, queue, sent):
        import time as _time

        open_the_tab(queue, sent)
        with ext_backend._lock:
            ext_backend._inflight[(40, 0, "1")] = (
                {}, "first_name", "Abhinav", False, _time.monotonic())
        sent.clear()
        ext_backend.handle_message(ext_protocol.FillHere(
            tab_id=40, url="https://co.example/careers/apply", title="t"))
        assert not any(m["type"] == "error" for m in sent)
        watch = next(m for m in sent if m["type"] == "watch_start")
        assert watch["tab_id"] == 40


class TestFileTokenRetry019:
    """019 (T014, FR-005): a transient attach failure must not burn the
    resume — tokens stay redeemable within TTL and die with the session."""

    def test_token_redeemable_more_than_once_within_ttl(self):
        ext_backend.reset_for_tests()
        tok = ext_backend.issue_file_token("C:/resumes/abhinav.pdf")
        assert ext_backend.consume_file_token(tok) == "C:/resumes/abhinav.pdf"
        assert ext_backend.consume_file_token(tok) == "C:/resumes/abhinav.pdf"

    def test_token_expires_at_ttl(self):
        ext_backend.reset_for_tests()
        tok = ext_backend.issue_file_token("C:/resumes/abhinav.pdf")
        with ext_backend._lock:
            path, issued = ext_backend._file_tokens[tok]
            ext_backend._file_tokens[tok] = (
                path, issued - ext_backend.FILE_TOKEN_TTL - 1)
        assert ext_backend.consume_file_token(tok) is None

    def test_tokens_die_with_the_session(self, queue, sent):
        open_the_tab(queue, sent)
        tok = ext_backend.issue_file_token("C:/resumes/abhinav.pdf")
        ext_backend.close_current()
        assert ext_backend.consume_file_token(tok) is None


class TestCredentialFill019:
    """019 (T045-T048, FR-015/FR-016/FR-019): the vault fills the wall, and
    the Sign in click is armed by STATE — never by button text."""

    LOGIN = dict(je_idx="1", tag="input", type="email", name="email",
                 id="email", label_text="Email Address",
                 autocomplete="username", form_context="login")
    PASSWORD = dict(je_idx="2", tag="input", type="password", name="password",
                    id="password", label_text="Password",
                    autocomplete="current-password", form_context="login")

    def _wall(self, tab_id=40, url="https://wd5.myworkdayjobs.com/en-US/login"):
        return fields_msg(job_url=url, tab_id=tab_id, doc="wall1",
                          descriptors=[descriptor(**self.LOGIN),
                                       descriptor(**self.PASSWORD)])

    def _vault(self, monkeypatch, saved=None):
        from engine import credentials

        monkeypatch.setattr(
            credentials, "get",
            lambda domain: saved or {"email": "me@example.com",
                                     "password": "s3cret-Pa55!"})

    def _matched_companion(self, sent):
        """FR-035: the escort never arms across a version mismatch, and the
        shared fixture registers "1.0.0" on purpose. An arming test has to
        speak for a companion that actually matches."""
        from engine import APP_VERSION

        ext_backend.register(sent.append, lambda code: None, APP_VERSION)

    def test_saved_login_fills_both_fields(self, queue, sent, monkeypatch):
        self._vault(monkeypatch)
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(self._wall())
        fills = [i for m in sent if m["type"] == "fill" for i in m["items"]]
        kinds = {i["je_idx"]: i["kind"] for i in fills}
        assert kinds.get("1") == "text"
        assert kinds.get("2") == "secret"

    def test_the_secret_never_reaches_the_page_feed(self, queue, sent,
                                                    monkeypatch):
        self._vault(monkeypatch)
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(self._wall())
        blob = json.dumps([m for m in sent if m["type"] == "answers"])
        assert "s3cret-Pa55!" not in blob

    def test_sign_in_arms_only_after_the_engine_filled_both(
            self, queue, sent, monkeypatch):
        self._vault(monkeypatch)
        open_the_tab(queue, sent)
        self._matched_companion(sent)
        ext_backend.handle_message(self._wall())
        sent.clear()
        # nothing yet: the fills have not reported back
        assert not any(m["type"] == "advance_step" for m in sent)
        ext_backend.handle_message(ext_protocol.FillResult(
            tab_id=40, frame_id=0,
            items=[{"je_idx": "1", "outcome": "filled"},
                   {"je_idx": "2", "outcome": "filled"}]))
        step = next(m for m in sent if m["type"] == "advance_step")
        assert step["kind"] == "sign_in"
        assert step["frame_id"] == 0

    def test_sign_in_is_one_shot_per_document(self, queue, sent, monkeypatch):
        self._vault(monkeypatch)
        open_the_tab(queue, sent)
        ext_backend.handle_message(self._wall())
        ext_backend.handle_message(ext_protocol.FillResult(
            tab_id=40, frame_id=0,
            items=[{"je_idx": "1", "outcome": "filled"},
                   {"je_idx": "2", "outcome": "filled"}]))
        sent.clear()
        # a re-render of the SAME wall must not fire a second click
        ext_backend.handle_message(self._wall())
        ext_backend.handle_message(ext_protocol.FillResult(
            tab_id=40, frame_id=0,
            items=[{"je_idx": "1", "outcome": "filled"},
                   {"je_idx": "2", "outcome": "filled"}]))
        assert not any(m["type"] == "advance_step" for m in sent)

    def test_a_chrome_prefilled_password_still_arms_sign_in(
            self, queue, sent, monkeypatch):
        """FR-019: the browser's own password manager got there first. That
        is a satisfied credential, not a dead end."""
        self._vault(monkeypatch)
        open_the_tab(queue, sent)
        self._matched_companion(sent)
        sent.clear()
        prefilled = fields_msg(
            job_url="https://wd5.myworkdayjobs.com/en-US/login", tab_id=40,
            doc="wall2",
            descriptors=[descriptor(**dict(self.LOGIN, value="me@example.com")),
                         descriptor(**dict(self.PASSWORD, value="already"))])
        ext_backend.handle_message(prefilled)
        step = next(m for m in sent if m["type"] == "advance_step")
        assert step["kind"] == "sign_in"

    def test_no_saved_login_is_visible_not_silent(self, queue, sent,
                                                  monkeypatch):
        """FR-017: this used to be a silent skip — the applicant never
        learned why nothing happened."""
        from engine import credentials

        monkeypatch.setattr(credentials, "get", lambda domain: None)
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(self._wall())
        answers = [m for m in sent if m["type"] == "answers"]
        assert answers
        entry = next(i for i in answers[-1]["items"]
                     if "password" in i["question"].lower()
                     or "email" in i["question"].lower())
        assert entry["group"] == "needs_you"
        assert entry["reason"] == "no_saved_login"
        assert not any(m["type"] == "advance_step" for m in sent)


class TestCredentialSave019:
    """019 (T047-T048, FR-017/FR-018): a login saved from the page goes to
    the vault and NOWHERE else."""

    def test_it_saves_and_acknowledges_without_the_secret(self, queue, sent,
                                                          monkeypatch):
        saved = {}
        from engine import credentials

        monkeypatch.setattr(credentials, "save",
                            lambda d, e, p: saved.update(domain=d, email=e,
                                                         password=p))
        open_the_tab(queue, sent)
        sent.clear()
        ext_backend.handle_message(ext_protocol.CredentialSave(
            tab_id=40, domain="wd5.myworkdayjobs.com",
            email="me@example.com", password="s3cret-Pa55!"))
        assert saved["domain"] == "wd5.myworkdayjobs.com"
        assert saved["password"] == "s3cret-Pa55!"
        blob = json.dumps(sent)
        assert "s3cret-Pa55!" not in blob
        assert "me@example.com" not in blob

    def test_saving_never_logs_the_secret(self, queue, sent, monkeypatch,
                                          caplog):
        from engine import credentials

        monkeypatch.setattr(credentials, "save", lambda d, e, p: None)
        open_the_tab(queue, sent)
        with caplog.at_level(logging.DEBUG):
            ext_backend.handle_message(ext_protocol.CredentialSave(
                tab_id=40, domain="d.example", email="me@example.com",
                password="s3cret-Pa55!"))
        assert "s3cret-Pa55!" not in caplog.text


class TestEscortWiring019:
    """019 (T059/T060): the escort's verdict reaches the page as exactly one
    advance_step, and everything it refuses is visible instead."""

    STEP = dict(je_idx="1", tag="input", type="text", name="first_name",
                id="first_name", label_text="First name", required=True)

    def _matched(self, sent):
        from engine import APP_VERSION

        ext_backend.register(sent.append, lambda code: None, APP_VERSION)

    def _complete_step(self, tab_id=40, doc="stepA", url=None):
        return fields_msg(
            job_url=url or "https://boards.greenhouse.io/figma/jobs/77",
            tab_id=tab_id, doc=doc,
            descriptors=[descriptor(**dict(self.STEP, value="Abhinav"))])

    def _settle(self, sent, msg):
        """Two scans a quiet-period apart — the escort will not advance a
        step that is still rendering."""
        ext_backend.handle_message(msg)
        for key in list(ext_backend._quiet_since):
            fh, _at = ext_backend._quiet_since[key]
            ext_backend._quiet_since[key] = (fh, time.monotonic() - 10)
        sent.clear()
        ext_backend.handle_message(msg)

    def test_a_complete_step_advances_once(self, queue, sent):
        open_the_tab(queue, sent)
        self._matched(sent)
        self._settle(sent, self._complete_step())
        steps = [m for m in sent if m["type"] == "advance_step"]
        assert len(steps) == 1
        assert steps[0]["kind"] == "next"
        assert steps[0]["step_key"]

        # ...and never again for the same rendered step
        sent.clear()
        ext_backend.handle_message(self._complete_step())
        assert not [m for m in sent if m["type"] == "advance_step"]

    def test_a_pending_required_field_blocks_the_advance(self, queue, sent):
        open_the_tab(queue, sent)
        self._matched(sent)
        unfilled = fields_msg(
            tab_id=40, doc="stepB",
            descriptors=[descriptor(**dict(self.STEP, je_idx="9",
                                           name="zz_unknown", id="zz",
                                           label_text="Unanswerable?",
                                           value=""))])
        self._settle(sent, unfilled)
        assert not [m for m in sent if m["type"] == "advance_step"]

    def test_a_captcha_pauses_and_says_so(self, queue, sent):
        open_the_tab(queue, sent)
        self._matched(sent)
        msg = self._complete_step(doc="stepC")
        msg.captcha = True
        self._settle(sent, msg)
        assert not [m for m in sent if m["type"] == "advance_step"]
        overlay = [m for m in sent if m["type"] == "overlay_state"][-1]
        assert overlay["summary"]["session"] == "your_turn_captcha"

    def test_linkedin_is_never_clicked(self, queue, sent):
        open_the_tab(queue, sent)
        self._matched(sent)
        self._settle(sent, self._complete_step(
            doc="stepD", url="https://www.linkedin.com/jobs/view/123/"))
        assert not [m for m in sent if m["type"] == "advance_step"]

    def test_a_stale_companion_is_never_escorted(self, queue, sent):
        """FR-035: the fixture's "1.0.0" mismatches by construction."""
        open_the_tab(queue, sent)
        self._settle(sent, self._complete_step(doc="stepE"))
        assert not [m for m in sent if m["type"] == "advance_step"]

    def test_the_click_lands_in_the_activity_trail(self, queue, sent):
        open_the_tab(queue, sent)
        self._matched(sent)
        ext_backend.handle_message(ext_protocol.AdvanceResult(
            tab_id=40, frame_id=0, kind="next", status="clicked",
            selector_kind="workday_next", control_hash="abc"))
        trail = ext_backend.progression_clicks()
        assert trail and trail[-1]["kind"] == "next"
        assert trail[-1]["status"] == "clicked"

    def test_a_refusal_is_recorded_too(self, queue, sent):
        open_the_tab(queue, sent)
        ext_backend.handle_message(ext_protocol.AdvanceResult(
            tab_id=40, frame_id=0, kind="next", status="refused",
            selector_kind="final_class", control_hash=""))
        assert ext_backend.progression_clicks()[-1]["status"] == "refused"


class TestSubmitAttribution019:
    """019 (FR-032): a wizard step POSTs its form. Without attribution every
    escorted step would look like an application the applicant sent."""

    def test_a_submit_right_after_our_advance_is_ours(self, queue, sent):
        open_the_tab(queue, sent)
        ext_backend._get_escort().note_advance("docA::f1")
        ext_backend.handle_message(ext_protocol.PageEvent(
            tab_id=40, kind="submit_detected",
            url="https://boards.greenhouse.io/figma/jobs/77"))
        assert not ext_backend.pending_submissions()

    def test_a_submit_with_no_advance_is_the_applicants(self, queue, sent):
        open_the_tab(queue, sent)
        ext_backend.handle_message(ext_protocol.PageEvent(
            tab_id=40, kind="submit_detected",
            url="https://boards.greenhouse.io/figma/jobs/77"))
        assert ext_backend.pending_submissions()


class TestNoClickHosts019:
    """019 (FR-033): the domain rule that keeps us off LinkedIn."""

    def test_linkedin_and_its_subdomains_are_refused(self):
        for url in ("https://www.linkedin.com/jobs/view/1/",
                    "https://linkedin.com/jobs/view/1/",
                    "https://in.linkedin.com/jobs/view/1/"):
            assert ext_backend._clickable_host(url) is False, url

    def test_an_explicit_port_cannot_defeat_the_rule(self):
        """netloc carries the port; a host rule that ":443" slips past is
        not a rule."""
        assert ext_backend._clickable_host(
            "https://www.linkedin.com:443/jobs/view/1/") is False

    def test_ordinary_ats_hosts_are_clickable(self):
        for url in ("https://boards.greenhouse.io/x/jobs/1",
                    "https://co.wd5.myworkdayjobs.com/en-US/careers",
                    "https://notlinkedin.com/jobs"):
            assert ext_backend._clickable_host(url) is True, url
