"""010 T004: transport-agnostic per-field decision rules, extracted from
watcher._process_field so the Playwright watcher and the extension backend
share ONE implementation of the safety-critical fill logic."""
import pytest

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


class TestLedgerRepair016:
    """016 (T007, R3): no_match/needs_manual settle WITH the drafter cache
    epoch — a NEWER answer re-opens the field; filled/skipped_existing stay
    permanently settled; legacy plain-string entries keep their old
    (never-retry) meaning."""

    def _descriptor(self, **over):
        d = {"je_idx": "3", "doc": "docA", "tag": "select", "type": "",
             "name": "auth", "id": "auth", "label_text": "Authorized?",
             "placeholder": "", "aria_label": "", "autocomplete": "",
             "value": "", "options": ["Yes", "No"], "maxlength": None,
             "focused": False, "visible": True, "widget": ""}
        d.update(over)
        return d

    def test_settle_entry_carries_epoch_for_retryable_outcomes(self):
        from engine.autofill import drafter

        drafter.reset_for_tests()
        entry = field_core.settle_entry("no_match")
        assert entry == ("no_match", drafter.cache_version())
        assert field_core.settle_entry("filled") == "filled"
        assert field_core.settle_entry("skipped_existing") == "skipped_existing"

    def test_no_match_retries_when_a_newer_answer_exists(self, monkeypatch):
        from engine.autofill import drafter

        drafter.reset_for_tests()
        handled = {("docA", "3"): ("no_match", 0)}
        monkeypatch.setattr(drafter, "cache_version", lambda: 1)  # newer
        decision = field_core.decide(None, self._descriptor(), handled,
                                     lambda tag, raw: "Yes")
        assert decision.action == "fill" and decision.option_label == "Yes"

    def test_no_match_skips_at_same_epoch(self):
        from engine.autofill import drafter

        drafter.reset_for_tests()
        handled = {("docA", "3"): ("no_match", drafter.cache_version())}
        decision = field_core.decide(None, self._descriptor(), handled,
                                     lambda tag, raw: "Yes")
        assert decision.action == "skip"

    def test_legacy_string_terminal_never_retries(self, monkeypatch):
        from engine.autofill import drafter

        drafter.reset_for_tests()
        monkeypatch.setattr(drafter, "cache_version", lambda: 99)
        handled = {("docA", "3"): "no_match"}
        decision = field_core.decide(None, self._descriptor(), handled,
                                     lambda tag, raw: "Yes")
        assert decision.action == "skip"

    def test_filled_stays_settled_regardless_of_epoch(self, monkeypatch):
        from engine.autofill import drafter

        drafter.reset_for_tests()
        monkeypatch.setattr(drafter, "cache_version", lambda: 99)
        handled = {("docA", "3"): "filled"}
        decision = field_core.decide(None, self._descriptor(), handled,
                                     lambda tag, raw: "Yes")
        assert decision.action == "skip"


class TestRadioGroupDecision016:
    """016 (T011/T013, R6): a grouped radio field decides to kind="radio"
    with the matched member label; an unmatched value settles no_match."""

    def _group(self, value=""):
        return {"je_idx": "7", "doc": "docA", "tag": "input",
                "type": "radio_group", "name": "authorized",
                "id": "auth_yes",
                "label_text": "Are you legally authorized to work in the US?",
                "placeholder": "", "aria_label": "", "autocomplete": "",
                "value": value, "options": ["Yes", "No"],
                "members": [{"je_idx": "7", "label": "Yes"},
                            {"je_idx": "8", "label": "No"}],
                "maxlength": None, "focused": False, "visible": True,
                "widget": "", "required": True}

    def test_matched_value_fills_as_radio_kind(self):
        decision = field_core.decide(None, self._group(), {},
                                     lambda tag, raw: "Yes")
        assert decision.action == "fill" and decision.kind == "radio"
        assert decision.option_label == "Yes" and decision.value == "Yes"

    def test_unmatched_value_settles_no_match(self):
        decision = field_core.decide(None, self._group(), {},
                                     lambda tag, raw: "A long paragraph")
        assert decision.action == "settle" and decision.outcome == "no_match"

    def test_already_checked_group_is_sacred(self):
        decision = field_core.decide(None, self._group(value="No"), {},
                                     lambda tag, raw: "Yes")
        assert decision.action == "settle"
        assert decision.outcome == "skipped_existing"


class TestShapeEnforcedAtDecision017:
    """017-T031 (FR-012): decide() refuses to emit a fill whose shape does not
    fit the control. Both live-run defect classes end here.
    """

    AKUNA_EXPIRY = ("If you have a current work authorization/status, when "
                    "does it expire? (Please enter N/A if you do not require "
                    "work authorization.)")

    def test_a_yes_no_fact_is_not_written_into_a_descriptive_text_field(self):
        d = decide(make_descriptor(label_text=self.AKUNA_EXPIRY,
                                   name="", id=""),
                   value="Yes")
        assert d.action == "settle"
        assert d.outcome == "no_match"

    def test_a_real_answer_for_that_field_still_fills(self):
        d = decide(make_descriptor(label_text=self.AKUNA_EXPIRY,
                                   name="", id=""),
                   value="2027-06-30")
        assert d.action == "fill"
        assert d.value == "2027-06-30"

    def test_prose_is_not_written_into_a_choice_with_unknown_options(self):
        paragraph = ("Yes, I have applied to a full-time or internship "
                     "position with Akuna in the past. I am currently an "
                     "embedded systems intern.")
        d = decide(make_descriptor(widget="custom_combobox", options=None,
                                   label_text="Acknowledgement", name="",
                                   id=""),
                   value=paragraph)
        assert d.action == "settle"
        assert d.outcome == "no_match"

    def test_prose_is_not_written_into_an_input_nested_in_a_choice_widget(self):
        """The React-select search box: its own attributes say free text, its
        ancestry says dropdown."""
        d = decide(make_descriptor(nested_in_choice=True, options=None,
                                   label_text="Acknowledgement", name="",
                                   id=""),
                   value="Yes, I acknowledge this and understand the terms.")
        assert d.action == "settle"
        assert d.outcome == "no_match"

    def test_a_short_label_still_fills_a_combobox(self):
        d = decide(make_descriptor(widget="custom_combobox", options=None,
                                   label_text="How did you hear about us?",
                                   name="", id=""),
                   value="LinkedIn")
        assert d.action == "fill"
        assert d.kind == "combobox"

    def test_ordinary_prose_still_fills_a_textarea(self):
        d = decide(make_descriptor(tag="textarea", label_text="Cover letter",
                                   name="", id=""),
                   value="I am excited about this role because ...")
        assert d.action == "fill"
        assert d.kind == "text"


class TestNameLayout017:
    """017-T035 (FR-017): first-vs-full name is a DOCUMENT-level question.

    classify() sees one field at a time, so a lone "Name" box and a "Name"
    box sitting beside "Last name" are indistinguishable to it. On a form
    with both, "Name" means the first name.
    """

    def layout(self, *labels):
        descriptors = [
            make_descriptor(je_idx=str(index), name="", id="",
                            label_text=label)
            for index, label in enumerate(labels)
        ]
        return field_core.name_layout(descriptors), descriptors

    def test_a_lone_name_field_stays_the_full_name(self):
        overrides, _ = self.layout("Name")
        assert overrides == {}

    def test_name_beside_last_name_means_first_name(self):
        overrides, _ = self.layout("Name", "Last name")
        assert overrides == {"0": "first_name"}

    def test_first_and_last_are_untouched(self):
        overrides, _ = self.layout("First name", "Last name")
        assert overrides == {}

    def test_preferred_name_is_not_demoted(self):
        """It is its own tag, not a full-name candidate."""
        overrides, _ = self.layout("Name", "Preferred name")
        assert overrides == {}

    def test_only_name_fields_in_the_same_document_count(self):
        first = make_descriptor(je_idx="1", doc="docA", name="", id="",
                                label_text="Name")
        other = make_descriptor(je_idx="2", doc="docB", name="", id="",
                                label_text="Last name")
        assert field_core.name_layout([first, other]) == {}

    def test_the_override_is_honoured_by_decide(self):
        d = field_core.decide(
            None,
            make_descriptor(je_idx="0", name="", id="", label_text="Name",
                            tag_override="first_name"),
            {},
            lambda tag, descriptor: "Abhinav" if tag == "first_name" else
            "Abhinav Battula",
        )
        assert d.action == "fill"
        assert d.tag == "first_name"
        assert d.value == "Abhinav"


class TestCheckboxGroup017:
    """017-T029 (C8, FR-014): a checkbox set sharing one question is ONE
    field. 016 left them separate, so the Akuna pronoun group became five
    independent essay questions and each received its own paragraph."""

    def group(self, value):
        return decide(
            make_descriptor(type="checkbox_group", name="", id="",
                            label_text="Add your personal pronouns below.",
                            options=["She/her/hers", "He/him/his",
                                     "They/them/theirs",
                                     "I do not wish to answer."],
                            members=[{"je_idx": "10", "label": "She/her/hers"},
                                     {"je_idx": "11", "label": "He/him/his"},
                                     {"je_idx": "12",
                                      "label": "They/them/theirs"},
                                     {"je_idx": "13",
                                      "label": "I do not wish to answer."}]),
            value=value)

    def test_a_member_label_ticks_that_member(self):
        d = self.group("He/him/his")
        assert d.action == "fill"
        assert d.kind == "checkbox"
        assert d.option_label == "He/him/his"

    def test_prose_never_reaches_it(self):
        d = self.group("As a recent M.S. Computer Engineering graduate with "
                       "hands-on experience in embedded systems...")
        assert d.action == "settle"
        assert d.outcome == "no_match"

    def test_an_unmatched_answer_is_left_for_the_human(self):
        d = self.group("Ze/zir")
        assert d.action == "settle"
        assert d.outcome == "no_match"


class TestPlaceholderChoiceIsUnanswered019:
    """019 (T031, FR-010): a choice control resting on "Select…" displays a
    value but the applicant has chosen nothing. Treating it as sacred is why
    those dropdowns were skipped_existing forever."""

    def _decide(self, raw, value="Yes"):
        return field_core.decide("greenhouse", raw, {},
                                 lambda tag, r: value)

    def _select(self, value, options):
        return {
            "je_idx": "1", "doc": "d", "tag": "select", "type": "select-one",
            "name": "authorized", "id": "authorized",
            "label_text": "Are you authorized to work in the US?",
            "placeholder": "", "aria_label": "", "autocomplete": "",
            "value": value, "options": options, "visible": True,
            "focused": False, "widget": "native_select",
        }

    def test_select_placeholder_text_counts_as_empty(self):
        d = self._decide(self._select("Select…", ["Select…", "Yes", "No"]))
        assert d.action == "fill"

    def test_dash_placeholder_counts_as_empty(self):
        d = self._decide(self._select("-- Please Select --",
                                      ["-- Please Select --", "Yes", "No"]))
        assert d.action == "fill"

    def test_a_real_choice_is_still_sacred(self):
        d = self._decide(self._select("No", ["Select…", "Yes", "No"]))
        assert d.action != "fill"

    def test_placeholder_rule_is_exported_for_the_serializers(self):
        """One rule, three call sites (scanner.js, field_core, filler.js) —
        the Python half must be importable so the parity test can pin it."""
        assert field_core.is_placeholder_value("Select…") is True
        assert field_core.is_placeholder_value("Choose one") is True
        assert field_core.is_placeholder_value("-- Please Select --") is True
        assert field_core.is_placeholder_value("United States") is False
        assert field_core.is_placeholder_value("") is True


class TestRichText020:
    """020 US4 (guarantees D1-D3): a rich-text editor decides like a textarea.

    Everything that made these fields invisible was upstream — the selector.
    Once they arrive as descriptors, the decision path must treat them as the
    long free-text answers they are, with no new special cases in the honesty
    rules (the v1.7.0 refusal contract is untouched).
    """

    def rich(self, **overrides):
        base = {
            "tag": "div", "type": "richtext", "widget": "richtext",
            "name": "", "id": "cover-editor",
            "label_text": "Cover Letter", "value": "",
            "automation_id": "coverLetter",
        }
        base.update(overrides)
        return make_descriptor(**base)

    def test_it_fills_as_text_not_as_a_choice(self):
        """D1: a rich-text box has no options, so it must never be routed to
        the select/combobox path."""
        d = decide(self.rich(), value="Dear hiring manager…")
        assert d.action == "fill"
        assert d.kind == "richtext"
        assert d.value == "Dear hiring manager…"

    def test_an_already_answered_editor_is_left_alone(self):
        """The applicant's own words always win."""
        d = decide(self.rich(value="I already wrote this myself."))
        assert d.action in ("settle", "skip")

    def test_a_focused_editor_is_never_written_over(self):
        d = decide(self.rich(focused=True))
        assert d.action != "fill"

    def test_it_classifies_as_a_cover_letter_without_a_name(self):
        """D3: an editable div has no .name, so classification has to work
        from the label and automation id alone."""
        from engine.autofill import fields

        tag = fields.classify(self.rich(label_text="Cover Letter", name=""))
        assert tag == "cover_letter"

    def test_an_unclassifiable_editor_stays_free_text_not_a_wrong_tag(self):
        """A missing .name must never be an excuse to guess."""
        from engine.autofill import fields

        tag = fields.classify(
            self.rich(label_text="Anything else we should know?",
                      name="", automation_id=""))
        assert tag == "free_text_unknown"

    def test_a_secret_never_travels_as_rich_text(self):
        """W4: kind 'secret' and 'richtext' are mutually exclusive. A
        credential rendered into a contenteditable would also land in the
        on-page answer feed."""
        d = decide(self.rich(label_text="Password", name="password",
                             type="richtext"),
                   value="hunter2")
        assert d.kind != "richtext" or not d.secret


class TestHumanizeIdentifier:
    """021 (FR-007): a field the label ladder cannot name usually still has a
    stable identity. scanner.js has captured `data-automation-id` since 011;
    the panel threw it away, so the row rendered blank."""

    @pytest.mark.parametrize("raw,expected", [
        ("countryRegionPhoneCode", "Country Region Phone Code"),
        ("overall_result_gpa", "Overall Result Gpa"),
        ("phone-number", "Phone Number"),
        ("legalNameSection_firstName", "Legal Name Section First Name"),
        ("school", "School"),
        ("wd_first", "Wd First"),
    ])
    def test_an_identifier_becomes_a_readable_question(self, raw, expected):
        assert field_core.humanize_identifier(raw) == expected

    @pytest.mark.parametrize("raw", [
        "", "   ",
        "input-23",              # the form-library default
        "react-select-4-input",  # react-select
        ":r1a:",                 # React 18 useId
        "field_7", "textbox-2", "control12",
        "a3f9c2b18e4d",          # a generated hex handle
        "42",
    ])
    def test_a_generated_identifier_names_nothing(self, raw):
        """Naming a question `input-23` is noise dressed up as information —
        worse than admitting the field could not be named, because the
        applicant cannot tell the two apart on the page."""
        assert field_core.humanize_identifier(raw) == ""

    def test_a_trailing_repeat_index_is_dropped(self):
        """`gpa-1` is "Overall Result (GPA)" in the SECOND education block.
        The section index already says which block; repeating it in the
        question text would defeat the de-duplication it feeds."""
        assert field_core.humanize_identifier("gpa-1") == "Gpa"
        assert field_core.humanize_identifier("jobTitle-3") == "Job Title"
