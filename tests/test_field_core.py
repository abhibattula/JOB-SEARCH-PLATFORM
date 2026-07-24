"""010 T004: transport-agnostic per-field decision rules, extracted from
watcher._process_field so the Playwright watcher and the extension backend
share ONE implementation of the safety-critical fill logic."""
from engine.autofill import field_core


def make_descriptor(**overrides):
    d = {
        "doc": "docA", "je_idx": "1", "tag": "input", "type": "text",
        "name": "first_name", "id": "first_name",
        "label_text": "First name", "placeholder": "", "aria_label": "",
        "autocomplete": "", "value": "", "options": None,
        "focused": False, "visible": True,
    }
    d.update(overrides)
    return d


def decide(descriptor, *, ats=None, handled=None, value="Abhinav"):
    return field_core.decide(
        ats, descriptor, handled if handled is not None else {},
        lambda tag, d: value,
    )


class TestGates:
    def test_invisible_non_file_ignored(self):
        d = decide(make_descriptor(visible=False))
        assert d.action == "ignore"

    def test_invisible_file_input_still_considered(self):
        d = decide(make_descriptor(visible=False, type="file",
                                   name="resume", label_text="Resume"),
                   value="C:/tmp/resume.pdf")
        assert d.action == "fill" and d.kind == "file"

    def test_terminal_ledger_entry_skips(self):
        handled = {("docA", "1"): "filled"}
        d = decide(make_descriptor(), handled=handled)
        assert d.action == "skip"

    def test_non_terminal_ledger_entry_retries(self):
        handled = {("docA", "1"): "pending_answer"}
        d = decide(make_descriptor(), handled=handled)
        assert d.action == "fill"

    def test_existing_value_is_sacred(self):
        d = decide(make_descriptor(value="already here"))
        assert d.action == "settle" and d.outcome == "skipped_existing"

    def test_existing_value_on_unknown_field_stays_silent(self):
        d = decide(make_descriptor(value="typed", name="mystery_field",
                                   id="", label_text="Mystery"))
        assert d.action == "skip"

    def test_focused_field_never_touched(self):
        d = decide(make_descriptor(focused=True))
        assert d.action == "skip"

    def test_no_value_available_skips(self):
        d = decide(make_descriptor(), value=None)
        assert d.action == "skip"


class TestFillDecisions:
    def test_text_fill_with_preview(self):
        d = decide(make_descriptor())
        assert d.action == "fill" and d.kind == "text"
        assert d.value == "Abhinav" and d.preview == "Abhinav"
        assert d.tag == "first_name"

    def test_password_preview_masked(self):
        d = decide(make_descriptor(type="password", name="password",
                                   id="password", label_text="Password",
                                   autocomplete="current-password"),
                   value="hunter2")
        assert d.action == "fill"
        assert d.value == "hunter2" and d.preview == "•••"
        assert d.secret is True

    def test_select_with_matching_option(self):
        d = decide(make_descriptor(
            tag="select", type="", name="work_auth",
            label_text="Are you authorized to work?",
            options=["Select...", "Yes", "No"],
        ), value="Yes")
        assert d.action == "fill" and d.kind == "select"
        assert d.option_label == "Yes" and d.preview == "Yes"

    def test_select_without_match_settles_no_match(self):
        d = decide(make_descriptor(
            tag="select", type="", name="how_heard",
            label_text="How did you hear about us?",
            options=["Twitter", "Friend"],
        ), value="Job Engine")
        assert d.action == "settle" and d.outcome == "no_match"

    def test_checkbox_truthy_fills_falsy_skips(self):
        base = make_descriptor(type="checkbox", name="remote_ok",
                               label_text="Open to remote?")
        assert decide(base, value=True).action == "fill"
        assert decide(base, value=True).kind == "checkbox"
        assert decide(base, value=False).action == "skip"

    def test_file_preview_is_basename(self):
        d = decide(make_descriptor(type="file", name="resume",
                                   label_text="Resume"),
                   value="C:\\data\\resumes\\Abhinav Battula.pdf")
        assert d.kind == "file" and d.preview == "Abhinav Battula.pdf"

    def test_adapter_classification_wins_over_generic(self):
        d = decide(
            make_descriptor(name="job_application[first_name]", id="",
                            label_text=""),
            ats="greenhouse",
        )
        assert d.action == "fill" and d.tag == "first_name"


class TestVocabulary:
    def test_terminal_outcomes_exported(self):
        assert field_core.TERMINAL_OUTCOMES == {
            "filled", "skipped_existing", "no_match", "needs_manual",
        }

    def test_ledger_key_shape(self):
        assert field_core.key(make_descriptor()) == ("docA", "1")


class TestWidgetAware011:
    """011 T004: widget-aware decide — native select unchanged; custom
    combobox → 'combobox'; typeahead → 'typeahead'; option-match still gates;
    sensitive-question safety preserved regardless of widget (C1)."""

    def test_native_select_still_select(self):
        d = decide(make_descriptor(
            tag="select", type="", name="work_auth",
            label_text="Authorized to work?", widget="native_select",
            options=["Select...", "Yes", "No"]), value="Yes")
        assert d.action == "fill" and d.kind == "select"
        assert d.option_label == "Yes"

    def test_custom_combobox_emits_combobox(self):
        d = decide(make_descriptor(
            tag="how_heard", type="", name="source",
            label_text="How did you hear about us?", widget="custom_combobox",
            options=["Select...", "LinkedIn", "A friend"]), value="LinkedIn")
        assert d.action == "fill" and d.kind == "combobox"
        assert d.option_label == "LinkedIn"

    def test_custom_combobox_without_readable_options_uses_value_as_label(self):
        d = decide(make_descriptor(
            tag="how_heard", type="", name="source",
            label_text="How did you hear about us?", widget="custom_combobox",
            options=None), value="LinkedIn")
        assert d.action == "fill" and d.kind == "combobox"
        assert d.option_label == "LinkedIn"

    def test_combobox_no_matching_option_settles_no_match(self):
        d = decide(make_descriptor(
            tag="how_heard", type="", name="source",
            label_text="How did you hear?", widget="custom_combobox",
            options=["Twitter", "Friend"]), value="Job Engine")
        assert d.action == "settle" and d.outcome == "no_match"

    def test_typeahead_emits_typeahead(self):
        d = decide(make_descriptor(
            tag="location", type="text", name="city",
            label_text="City", widget="typeahead"), value="Austin, TX")
        assert d.action == "fill" and d.kind == "typeahead"
        assert d.value == "Austin, TX"

    def test_c1_sensitive_combobox_unanswered_skips_never_fills(self):
        # a work-auth custom combobox with NO saved answer: get_value returns
        # None (browser_controller sets the confirm-pending slot), so decide
        # must SKIP — the widget kind must never bypass the value gate.
        d = field_core.decide(
            None,
            make_descriptor(tag="work_authorization", type="", name="wauth",
                            label_text="Are you authorized to work?",
                            widget="custom_combobox",
                            options=["Yes", "No"]),
            {}, lambda tag, desc: None)
        assert d.action == "skip"

    def test_c1_combobox_is_never_ai_draft(self):
        # even if a Draft somehow reached a combobox, it fills as a normal
        # option pick, not a flagged free-text draft (drafts are free-text only)
        d = decide(make_descriptor(
            tag="how_heard", type="", name="source", widget="custom_combobox",
            options=["LinkedIn"]), value=field_core.Draft("LinkedIn"))
        assert d.kind == "combobox" and d.ai_draft is False
