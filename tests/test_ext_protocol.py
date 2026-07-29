"""010 T003: bridge message schemas — strict validation at the trust
boundary. Everything arriving from the extension is untrusted input."""
import json

import pytest

from engine.autofill import ext_protocol as proto


def make_descriptor(**overrides):
    d = {
        "je_idx": "3", "doc": "abc123", "tag": "input", "type": "text",
        "name": "first_name", "id": "first_name", "label_text": "First name",
        "placeholder": "", "aria_label": "", "autocomplete": "given-name",
        "value": "", "focused": False, "visible": True,
    }
    d.update(overrides)
    return d


def envelope(type_, **payload):
    return json.dumps({"v": 1, "type": type_, "seq": 1, **payload})


class TestInboundParsing:
    def test_hello_round_trip(self):
        msg = proto.parse_inbound(envelope(
            "hello", secret="ab" * 32, version="1.0.0", chrome_version="127"
        ))
        assert isinstance(msg, proto.Hello)
        assert msg.secret == "ab" * 32

    def test_fields_with_descriptors(self):
        msg = proto.parse_inbound(envelope(
            "fields", tab_id=5, frame_id=0, url="https://x.example/apply",
            doc="abc123", descriptors=[make_descriptor()],
        ))
        assert isinstance(msg, proto.Fields)
        assert msg.descriptors[0].autocomplete == "given-name"

    def test_fields_descriptor_dict_shape_matches_watcher(self):
        """Descriptors must expose the exact keys watcher/fields classify
        on, so fields.py + adapters.py run unchanged."""
        msg = proto.parse_inbound(envelope(
            "fields", tab_id=1, frame_id=0, url="u", doc="d",
            descriptors=[make_descriptor()],
        ))
        raw = msg.descriptors[0].as_watcher_dict()
        for key in ("tag", "type", "name", "id", "label_text", "placeholder",
                    "aria_label", "autocomplete", "value", "focused",
                    "visible", "je_idx", "doc"):
            assert key in raw

    def test_fill_result_outcomes_validated(self):
        msg = proto.parse_inbound(envelope(
            "fill_result", tab_id=5, frame_id=0,
            items=[{"je_idx": "3", "outcome": "filled"}],
        ))
        assert msg.items[0].outcome == "filled"
        with pytest.raises(proto.ProtocolError):
            proto.parse_inbound(envelope(
                "fill_result", tab_id=5, frame_id=0,
                items=[{"je_idx": "3", "outcome": "exploded"}],
            ))

    def test_page_event_kinds(self):
        for kind in ("nav", "tab_closed", "frame_gone", "submit_detected"):
            msg = proto.parse_inbound(envelope(
                "page_event", tab_id=2, kind=kind, url="https://x.example"
            ))
            assert msg.kind == kind
        with pytest.raises(proto.ProtocolError):
            proto.parse_inbound(envelope("page_event", tab_id=2, kind="weird"))

    def test_fill_here_and_pong(self):
        here = proto.parse_inbound(envelope(
            "fill_here", tab_id=9, url="https://x.example/j", title="Job"
        ))
        assert isinstance(here, proto.FillHere)
        assert isinstance(proto.parse_inbound(envelope("pong")), proto.Pong)


class TestRejection:
    def test_malformed_json_rejected(self):
        with pytest.raises(proto.ProtocolError):
            proto.parse_inbound("{not json")

    def test_wrong_version_rejected(self):
        raw = json.dumps({"v": 99, "type": "pong", "seq": 1})
        with pytest.raises(proto.ProtocolError):
            proto.parse_inbound(raw)

    def test_unknown_type_rejected(self):
        with pytest.raises(proto.ProtocolError):
            proto.parse_inbound(envelope("launch_missiles"))

    def test_oversized_message_rejected(self):
        big = envelope("fields", tab_id=1, frame_id=0, url="u", doc="d",
                       descriptors=[make_descriptor(value="x" * 2_000_000)])
        with pytest.raises(proto.ProtocolError):
            proto.parse_inbound(big)

    def test_missing_required_field_rejected(self):
        with pytest.raises(proto.ProtocolError):
            proto.parse_inbound(envelope("hello", version="1.0.0"))  # no secret


class TestOutbound:
    def test_fill_item_kinds_validated(self):
        item = proto.FillItem(je_idx="3", kind="secret", value="hunter2")
        assert item.kind == "secret"
        with pytest.raises(Exception):
            proto.FillItem(je_idx="3", kind="clicky", value="x")

    def test_outbound_builders_produce_versioned_envelopes(self):
        out = proto.outbound("fill", tab_id=1, frame_id=0, items=[
            proto.FillItem(je_idx="3", kind="text", value="Abhinav").model_dump()
        ])
        assert out["v"] == proto.PROTOCOL_V and out["type"] == "fill"
        assert out["seq"] > 0
        again = proto.outbound("ping")
        assert again["seq"] > out["seq"]

    def test_fill_item_secret_repr_masked(self):
        """A FillItem holding a secret must not leak it via repr/str
        (defensive: log formatting of pydantic models)."""
        item = proto.FillItem(je_idx="3", kind="secret", value="hunter2")
        assert "hunter2" not in repr(item)
        assert "hunter2" not in str(item)


class TestWidgetKinds011:
    """011: custom dropdown + typeahead fill kinds and the widget descriptor."""

    def test_combobox_and_typeahead_kinds_accepted(self):
        combo = proto.FillItem(je_idx="4", kind="combobox", value="Yes",
                               option_label="Yes")
        assert combo.kind == "combobox" and combo.option_label == "Yes"
        ta = proto.FillItem(je_idx="5", kind="typeahead", value="Austin, TX")
        assert ta.kind == "typeahead"

    def test_descriptor_carries_widget_and_automation_id(self):
        msg = proto.parse_inbound(envelope(
            "fields", tab_id=1, frame_id=0, url="u", doc="d",
            descriptors=[make_descriptor(widget="custom_combobox",
                                         automation_id="legalNameSection_firstName")],
        ))
        d = msg.descriptors[0]
        assert d.widget == "custom_combobox"
        assert d.automation_id == "legalNameSection_firstName"
        assert d.as_watcher_dict()["widget"] == "custom_combobox"

    def test_descriptor_widget_defaults_empty(self):
        msg = proto.parse_inbound(envelope(
            "fields", tab_id=1, frame_id=0, url="u", doc="d",
            descriptors=[make_descriptor()],
        ))
        assert msg.descriptors[0].widget == ""
        assert msg.descriptors[0].automation_id == ""

    def test_unknown_widget_value_rejected(self):
        with pytest.raises(proto.ProtocolError):
            proto.parse_inbound(envelope(
                "fields", tab_id=1, frame_id=0, url="u", doc="d",
                descriptors=[make_descriptor(widget="wobble")],
            ))


class TestProtocolAdditions016:
    """016 (T002): additive protocol — PROTOCOL_V stays 1; payloads from
    old companions (no new fields) remain valid; new messages parse."""

    def test_protocol_v_still_1(self):
        assert proto.PROTOCOL_V == 1

    def test_descriptor_members_and_required_parse(self):
        msg = proto.parse_inbound(envelope(
            "fields", tab_id=1, frame_id=0, url="u", doc="d",
            descriptors=[make_descriptor(
                type="radio_group", options=["Yes", "No"],
                members=[{"je_idx": "7", "label": "Yes"},
                         {"je_idx": "8", "label": "No"}],
                required=True,
            )],
        ))
        d = msg.descriptors[0]
        assert d.type == "radio_group"
        assert [m.label for m in d.members] == ["Yes", "No"]
        assert d.required is True
        raw = d.as_watcher_dict()
        assert raw["members"][0]["je_idx"] == "7"
        assert raw["required"] is True

    def test_old_descriptor_without_new_fields_still_valid(self):
        msg = proto.parse_inbound(envelope(
            "fields", tab_id=1, frame_id=0, url="u", doc="d",
            descriptors=[make_descriptor()],
        ))
        assert msg.descriptors[0].members == []
        assert msg.descriptors[0].required is False

    def test_scan_error_message(self):
        msg = proto.parse_inbound(envelope(
            "scan_error", tab_id=3, message="TypeError: boom"))
        assert isinstance(msg, proto.ScanError)
        assert msg.tab_id == 3 and "boom" in msg.message

    def test_child_tab_message(self):
        msg = proto.parse_inbound(envelope(
            "child_tab", tab_id=10, opener_tab_id=4))
        assert isinstance(msg, proto.ChildTab)
        assert msg.tab_id == 10 and msg.opener_tab_id == 4

    def test_fill_again_message(self):
        msg = proto.parse_inbound(envelope("fill_again", tab_id=6))
        assert isinstance(msg, proto.FillAgain)
        assert msg.tab_id == 6

    def test_fill_item_radio_kind_and_needs_you_flag(self):
        item = proto.FillItem(je_idx="7", kind="radio", value="Yes",
                              flag="needs_you")
        assert item.kind == "radio" and item.flag == "needs_you"

    def test_rescan_outbound_envelope(self):
        out = proto.outbound("rescan", reason="draft_ready")
        assert out["type"] == "rescan" and out["v"] == 1


class TestHelloBrowser015:
    """015 (T009): Hello gains an OPTIONAL browser field — additive,
    PROTOCOL_V stays 1, old companions (no field) remain valid."""

    def test_hello_without_browser_still_valid(self):
        import json

        from engine.autofill import ext_protocol

        msg = ext_protocol.parse_inbound(json.dumps({
            "v": 1, "type": "hello", "seq": 1,
            "secret": "s3", "version": "1.4.0",
        }))
        assert isinstance(msg, ext_protocol.Hello)
        assert msg.browser == ""

    def test_hello_with_browser_parses(self):
        import json

        from engine.autofill import ext_protocol

        msg = ext_protocol.parse_inbound(json.dumps({
            "v": 1, "type": "hello", "seq": 1,
            "secret": "s3", "version": "1.5.0", "browser": "edge",
        }))
        assert msg.browser == "edge"


class TestSessionControl018:
    """018 (FR-030/FR-032/FR-036): Stop and Next from the page.

    Additive: PROTOCOL_V stays 1, so a companion older than the app simply
    never sends this, and an app older than the companion rejects it through
    the existing protocol-reject path rather than crashing.
    """

    def test_stop_and_next_validate(self):
        for action in ("stop", "next"):
            msg = proto.parse_inbound(json.dumps({
                "v": 1, "type": "session_control", "seq": 1,
                "tab_id": 7, "action": action,
            }))
            assert isinstance(msg, proto.SessionControl)
            assert msg.action == action
            assert msg.tab_id == 7

    def test_an_unknown_field_is_ignored_not_fatal(self):
        """`extra="ignore"` is the forward-compatibility mechanism: a
        companion NEWER than the app must not be rejected wholesale for
        sending a field this version has never heard of. The extra field is
        dropped, and it cannot smuggle in behaviour — `submit` here is not a
        thing this message can do."""
        msg = proto.parse_inbound(json.dumps({
            "v": 1, "type": "session_control", "seq": 1,
            "tab_id": 7, "action": "stop", "submit": True,
        }))
        assert msg.action == "stop"
        assert not hasattr(msg, "submit")

    def test_a_missing_required_field_is_rejected(self):
        with pytest.raises(proto.ProtocolError):
            proto.parse_inbound(json.dumps({
                "v": 1, "type": "session_control", "seq": 1, "tab_id": 7,
            }))

    def test_an_unknown_action_is_refused_with_a_reason(self):
        """Not a schema error on purpose: the refusal has to reach the
        applicant's screen (FR-010), and a protocol reject is silent to the
        page."""
        from engine.autofill import ext_backend

        sent = []
        ext_backend.register(sent.append, lambda code: None, "1.0.0")
        with ext_backend._lock:
            ext_backend._watch["tab_id"] = 7
        try:
            ext_backend.handle_message(proto.SessionControl(
                tab_id=7, action="submit_the_application"))
        finally:
            ext_backend.reset_for_tests()
        errors = [m for m in sent if m.get("type") == "error"]
        assert errors and errors[0]["code"] == "bad_action"

    def test_protocol_version_is_unchanged(self):
        assert proto.PROTOCOL_V == 1

    def test_a_017_era_overlay_state_still_builds(self):
        """The new optional summary fields are additive — the old shape must
        still be valid, or an older companion breaks on upgrade."""
        payload = proto.outbound("overlay_state", tab_id=1, summary={
            "seen": 3, "filled": 2, "needs_you": 1, "drafts": 0,
            "needs_you_idx": ["4"], "attention": ["Why us?"],
            "message": "you click the actual apply/submit",
        })
        assert payload["type"] == "overlay_state"
        assert payload["summary"]["seen"] == 3

    def test_a_017_era_answers_payload_still_builds(self):
        payload = proto.outbound("answers", tab_id=1, job_id=2, items=[
            {"question": "Q", "answer": "A", "state": "drafted",
             "reason": None, "askable": False},
        ], truncated=False)
        assert payload["items"][0]["question"] == "Q"
