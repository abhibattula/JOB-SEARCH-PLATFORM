"""021 Workstream A — the shareable page report.

v2.0.0 met a real Intel Workday application and reported Filled 5 / Needs you
149 / Seen 156, most rows blank. Three causes were readable from source, but
one question was not: is that 156 one scan genuinely seeing 156 descriptors,
or a stale-frame count summing forever? The existing Workday fixtures hold 9
and 2 fields, so the suite could never answer it.

This module is how the applicant hands back what is actually on the page —
which means it must be safe to hand back. It records SHAPE, never content:
`has_value` is a boolean and that is the entire signal about what was typed.

Every refusal test here is paired with a substance test. A refusal assertion
on its own passes happily against a builder that emits nothing at all, and
this project has shipped that mistake before.
"""
from __future__ import annotations

import json

import pytest

from engine.autofill import page_report


def descriptor(**kw):
    """A field as scanner.js serializes it."""
    base = {
        "doc": "abc123",
        "je_idx": "7",
        "tag": "input",
        "type": "text",
        "name": "country",
        "id": "input-23",
        "label_text": "Country/Region",
        "placeholder": "",
        "aria_label": "",
        "autocomplete": "",
        "value": "",
        "options": [],
        "widget": "",
        "automation_id": "countryDropdown",
        "required": True,
        "visible": True,
        "focused": False,
        "form_context": "",
        "section_label": "Address",
        "section_index": 0,
    }
    base.update(kw)
    return base


def record(desc=None, **kw):
    """One field plus what the app decided about it."""
    base = {
        "descriptor": desc if desc is not None else descriptor(),
        "decision": "skip",
        "tag": "location_country",
        "reason": "profile_fact_missing",
    }
    base.update(kw)
    return base


def build(records, **kw):
    kwargs = {
        "captured_at": "2026-08-02T18:04:11Z",
        "app_version": "2.1.0",
        "ats": "workday",
        "url_host": "intel.wd1.myworkdayjobs.com",
    }
    kwargs.update(kw)
    return page_report.build(records, **kwargs)


class TestItRefusesToCarryContent:
    """FR-002 / contracts/page_report.md — the report is safe to share."""

    def test_a_typed_value_never_appears(self):
        report = build([record(descriptor(value="Bengaluru, Karnataka"))])
        assert "Bengaluru" not in json.dumps(report)

    def test_every_value_on_a_crowded_page_is_dropped(self):
        secrets = [f"secret-value-{n}" for n in range(20)]
        records = [record(descriptor(je_idx=str(n), value=v))
                   for n, v in enumerate(secrets)]
        blob = json.dumps(build(records))
        for value in secrets:
            assert value not in blob

    def test_a_selected_option_is_not_carried(self):
        report = build([record(descriptor(
            widget="native_select", value="Yes, I am a veteran",
            options=["Select…", "Yes, I am a veteran", "I decline"]))])
        blob = json.dumps(report)
        assert "veteran" not in blob.lower()

    def test_a_password_field_carries_nothing(self):
        report = build([record(
            descriptor(type="password", name="password",
                       value="hunter2-the-real-one"),
            tag="password", decision="fill")])
        assert "hunter2" not in json.dumps(report)

    def test_the_url_is_reduced_to_a_host(self):
        """A real ATS URL routinely carries a session or candidate token."""
        report = build(
            [record()],
            url_host=page_report.safe_host(
                "https://intel.wd1.myworkdayjobs.com/en-US/apply"
                "?token=SECRETSESSIONTOKEN&candidate=99"),
        )
        blob = json.dumps(report)
        assert "SECRETSESSIONTOKEN" not in blob
        assert "candidate=99" not in blob
        assert "/en-US/apply" not in blob
        assert report["url_host"] == "intel.wd1.myworkdayjobs.com"

    def test_has_value_is_a_boolean_not_the_value(self):
        report = build([
            record(descriptor(je_idx="1", value="")),
            record(descriptor(je_idx="2", value="something typed")),
        ])
        assert report["fields"][0]["has_value"] is False
        assert report["fields"][1]["has_value"] is True

    def test_a_whitespace_only_value_does_not_count_as_answered(self):
        report = build([record(descriptor(value="   "))])
        assert report["fields"][0]["has_value"] is False


class TestItActuallyCarriesSomething:
    """The other half. Without these, every test above passes against a
    builder that returns an empty dict — which is not a diagnostic."""

    def test_identity_and_shape_survive(self):
        report = build([record()])
        field = report["fields"][0]
        assert field["tag"] == "input"
        assert field["type"] == "text"
        assert field["name"] == "country"
        assert field["id"] == "input-23"
        assert field["automation_id"] == "countryDropdown"
        assert field["label_text"] == "Country/Region"

    def test_the_decision_and_its_reason_survive(self):
        report = build([record()])
        field = report["fields"][0]
        assert field["decision"] == "skip"
        assert field["tag_classified"] == "location_country"
        assert field["reason"] == "profile_fact_missing"

    def test_section_context_survives(self):
        report = build([record(descriptor(
            section_label="Work Experience", section_index=1))])
        field = report["fields"][0]
        assert field["section_label"] == "Work Experience"
        assert field["section_index"] == 1

    def test_visibility_and_requiredness_survive(self):
        report = build([record(descriptor(visible=False, required=False))])
        field = report["fields"][0]
        assert field["visible"] is False
        assert field["required"] is False

    def test_every_field_given_is_reported(self):
        records = [record(descriptor(je_idx=str(n))) for n in range(150)]
        assert len(build(records)["fields"]) == 150

    def test_document_order_is_preserved(self):
        records = [record(descriptor(je_idx=str(n), name=f"f{n}"))
                   for n in range(10)]
        names = [f["name"] for f in build(records)["fields"]]
        assert names == [f"f{n}" for n in range(10)]


class TestTheEnvelope:
    def test_it_records_when_and_what(self):
        report = build([record()])
        assert report["captured_at"] == "2026-08-02T18:04:11Z"
        assert report["app_version"] == "2.1.0"
        assert report["ats"] == "workday"
        assert report["protocol_v"] == 1

    def test_counts_are_derived_when_not_supplied(self):
        records = [
            record(descriptor(je_idx="1"), decision="fill"),
            record(descriptor(je_idx="2"), decision="skip"),
            record(descriptor(je_idx="3"), decision="skip"),
            record(descriptor(je_idx="4", section_label="Education"),
                   decision="ignore"),
        ]
        counts = build(records)["counts"]
        assert counts["seen"] == 4
        assert counts["filled"] == 1
        assert counts["needs_you"] == 2
        assert counts["sections"] == 2  # Address + Education

    def test_supplied_counts_win(self):
        """The app's own counters are authoritative — they see every frame."""
        counts = build([record()], counts={"seen": 156, "filled": 5,
                                           "needs_you": 149, "sections": 12})
        assert counts["counts"]["seen"] == 156

    def test_an_empty_page_still_produces_a_valid_report(self):
        report = build([])
        assert report["fields"] == []
        assert report["counts"]["seen"] == 0


class TestItRoundTrips:
    def test_the_report_is_json(self):
        blob = json.dumps(build([record()]))
        assert json.loads(blob)["fields"][0]["name"] == "country"

    def test_every_field_carries_the_full_key_set(self):
        """A key that only appears when it has content makes two reports from
        two pages impossible to diff — which is the whole point of the file."""
        expected = {
            "tag", "type", "widget", "role", "name", "id", "automation_id",
            "label_text", "section_label", "section_index", "visible",
            "required", "has_value", "decision", "tag_classified", "reason",
        }
        sparse = build([record(
            descriptor(name="", id="", automation_id="", label_text="",
                       section_label="", section_index=0),
            tag="", reason="")])
        assert set(sparse["fields"][0]) == expected

    def test_the_builder_is_pure(self):
        """No clock, no filesystem, no `web` import — `captured_at` is passed
        in, so these tests need no time freezing and the module can be reused
        by the frozen build and the test suite alike."""
        first = build([record()])
        second = build([record()])
        assert first == second


class TestSafeHost:
    @pytest.mark.parametrize("url,expected", [
        ("https://intel.wd1.myworkdayjobs.com/en-US/apply?t=x",
         "intel.wd1.myworkdayjobs.com"),
        ("https://boards.greenhouse.io/acme/jobs/123", "boards.greenhouse.io"),
        ("http://localhost:8756/practice", "localhost:8756"),
        ("", ""),
        ("not a url at all", ""),
    ])
    def test_only_the_host_survives(self, url, expected):
        assert page_report.safe_host(url) == expected

    def test_credentials_in_a_url_are_dropped(self):
        """https://user:pass@host/ is legal and carries a password."""
        assert page_report.safe_host(
            "https://alice:hunter2@jobs.example.com/apply"
        ) == "jobs.example.com"

    @pytest.mark.parametrize("value", [
        "jobs.example.com/apply?token=SECRET",
        "jobs.example.com/apply#SECRET",
        "jobs.example.com:443/apply?token=SECRET",
    ])
    def test_a_schemeless_url_is_still_reduced(self, value):
        """urlsplit() puts a schemeless string entirely in `path`, so a naive
        netloc read returns "" and a caller falling back to the raw value
        would ship the query string. Found by writing the paired test."""
        assert "SECRET" not in page_report.safe_host(value)
        assert page_report.safe_host(value).startswith("jobs.example.com")


class TestTheHostFieldCannotLeak:
    def test_a_full_url_passed_as_the_host_is_reduced_anyway(self):
        report = build([record()],
                       url_host="https://x.com/apply?token=SECRETTOKEN")
        assert "SECRETTOKEN" not in json.dumps(report)
        assert report["url_host"] == "x.com"

    def test_a_schemeless_url_passed_as_the_host_is_reduced_anyway(self):
        """The fallback path — this is the one that leaked."""
        report = build([record()], url_host="x.com/apply?token=SECRETTOKEN")
        assert "SECRETTOKEN" not in json.dumps(report)
        assert report["url_host"] == "x.com"


@pytest.fixture()
def client(tmp_db, monkeypatch):
    from fastapi.testclient import TestClient

    from engine import matcher

    monkeypatch.setenv("REFRESH_SYNC", "1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
    from web.main import create_app

    return TestClient(create_app())


class TestTheReportRoutes:
    """021 (FR-002): the applicant retrieves the file from the app."""

    def test_an_empty_reports_directory_is_not_an_error(self, client,
                                                        tmp_path, monkeypatch):
        from engine import paths

        monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
        assert client.get("/api/reports").json() == {"reports": []}

    def test_reports_are_listed_newest_first(self, client, tmp_path,
                                             monkeypatch):
        import os
        import time

        from engine import paths

        monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
        directory = tmp_path / "reports"
        directory.mkdir()
        for name in ("page-20260801T100000Z.json", "page-20260802T100000Z.json"):
            (directory / name).write_text(
                json.dumps({"fields": [{"name": "x"}]}), encoding="utf-8")
        older = directory / "page-20260801T100000Z.json"
        os.utime(older, (time.time() - 600, time.time() - 600))

        rows = client.get("/api/reports").json()["reports"]
        assert [r["filename"] for r in rows] == [
            "page-20260802T100000Z.json", "page-20260801T100000Z.json"]
        assert rows[0]["fields"] == 1

    def test_a_report_downloads(self, client, tmp_path, monkeypatch):
        from engine import paths

        monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
        directory = tmp_path / "reports"
        directory.mkdir()
        (directory / "page-20260802T100000Z.json").write_text(
            json.dumps({"fields": []}), encoding="utf-8")

        response = client.get("/api/reports/page-20260802T100000Z.json")
        assert response.status_code == 200
        assert response.json() == {"fields": []}

    @pytest.mark.parametrize("name", [
        "../jobs.db",
        "..%2Fjobs.db",
        "page-x.json/../../jobs.db",
        "page-.json",
        "jobs.db",
        "page-20260802T100000Z.json.bak",
    ])
    def test_a_name_outside_the_pattern_is_refused(self, client, tmp_path,
                                                   monkeypatch, name):
        """An allowlist of the exact shape this app writes, not a sanitizer —
        sanitizing invites an encoding that slips through."""
        from engine import paths

        monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
        assert client.get(f"/api/reports/{name}").status_code in (404, 400)

    def test_a_missing_report_is_a_404_not_a_500(self, client, tmp_path,
                                                 monkeypatch):
        from engine import paths

        monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
        assert client.get(
            "/api/reports/page-20990101T000000Z.json").status_code == 404
