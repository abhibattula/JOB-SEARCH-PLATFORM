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
