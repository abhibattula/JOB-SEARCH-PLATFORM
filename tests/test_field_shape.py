"""017-T006: field_core.value_fits — an answer may only be written to a
field whose SHAPE accepts it (FR-012).

Two live defects from the 2026-07-28 Akuna Capital run share one cause:
nothing checked that the answer's shape fitted the control.

  * `qa.profile_fact_answer` returns "Yes"/"No" for anything matching the
    work-authorization regex, so four FREE-TEXT questions asking for a date,
    a status, extension options and a description each received "Yes".
  * A paragraph reached a custom dropdown because the only length guard was
    keyed on the `custom_combobox` widget flag, which the offending element
    (a search input nested inside the widget) did not carry.

The predicate is consulted by both `field_core.decide` (before emitting a
fill) and `drafter._validate` (before accepting a generation), so neither
path can write a mis-shaped value.
"""
import pytest

from engine.autofill import field_core


def descriptor(**overrides):
    base = {
        "tag": "input",
        "type": "text",
        "name": "",
        "id": "",
        "label_text": "",
        "placeholder": "",
        "aria_label": "",
        "options": [],
        "members": [],
        "widget": "",
        "maxlength": None,
        "nested_in_choice": False,
    }
    base.update(overrides)
    return base


PARAGRAPH = (
    "Yes, I have applied to a full-time or internship position with Akuna "
    "Capital University in the past. I am currently an embedded systems "
    "intern developing an AI-powered edge computing solution."
)


# --- the four Akuna work-authorization free-text questions -------------

AKUNA_WORK_AUTH_QUESTIONS = [
    "If you have a current work authorization/status, when does it expire? "
    "(Please enter N/A if you do not require work authorization.)",
    "If applicable, please list any extension options for your current work "
    "authorization status. (Please enter N/A if you do not require work "
    "authorization.)",
    "Please provide additional detail about your sponsorship needs, current "
    "work authorization status, or eligibility for a work authorization "
    "status. (Please enter N/A if you do not require work authorization.)",
    "If you answered “Yes” above to requiring visa sponsorship now "
    "or in the future for work authorization, please respond to the "
    "following questions. What is your current immigration status/basis of "
    "your current work authorization?",
]


@pytest.mark.parametrize("question", AKUNA_WORK_AUTH_QUESTIONS)
def test_bare_yes_is_refused_for_a_descriptive_free_text_question(question):
    """Every one of these received "Yes" on the live run."""
    ok, reason = field_core.value_fits(
        descriptor(label_text=question), "Yes")
    assert ok is False
    assert reason == "wrong_shape"


@pytest.mark.parametrize("question", AKUNA_WORK_AUTH_QUESTIONS)
def test_a_real_answer_is_accepted_for_the_same_question(question):
    ok, reason = field_core.value_fits(
        descriptor(label_text=question), "F-1 STEM OPT, expires 2027-06-30")
    assert ok is True, reason


def test_na_is_accepted_for_a_descriptive_question():
    """The form itself instructs "enter N/A" — that is a real answer."""
    ok, _ = field_core.value_fits(
        descriptor(label_text=AKUNA_WORK_AUTH_QUESTIONS[0]), "N/A")
    assert ok is True


def test_bare_no_is_also_refused():
    ok, reason = field_core.value_fits(
        descriptor(label_text=AKUNA_WORK_AUTH_QUESTIONS[0]), "No")
    assert (ok, reason) == (False, "wrong_shape")


def test_a_plain_yes_no_text_field_still_accepts_yes():
    """Only DESCRIPTIVE labels reject a yes/no token. A free-text field that
    genuinely asks a yes/no question must keep working."""
    ok, _ = field_core.value_fits(
        descriptor(label_text="Are you at least 18 years of age?"), "Yes")
    assert ok is True


# --- prose into a choice control ---------------------------------------

def test_paragraph_refused_for_a_choice_with_unknown_options():
    """The acknowledgement dropdown case: options are not readable until the
    widget is opened, so the answer must look like an option label."""
    ok, reason = field_core.value_fits(
        descriptor(widget="custom_combobox"), PARAGRAPH)
    assert (ok, reason) == (False, "not_an_option_label")


def test_paragraph_refused_for_an_input_nested_inside_a_choice_widget():
    """The exact C6 element: a search <input> inside div.select__control. Its
    own attributes look like free text; its ancestry does not."""
    ok, reason = field_core.value_fits(
        descriptor(nested_in_choice=True), PARAGRAPH)
    assert (ok, reason) == (False, "not_an_option_label")


def test_short_label_accepted_for_a_choice_with_unknown_options():
    ok, _ = field_core.value_fits(descriptor(widget="custom_combobox"), "Yes")
    assert ok is True


def test_multi_word_but_option_like_label_is_accepted():
    ok, _ = field_core.value_fits(
        descriptor(widget="custom_combobox"), "Prefer not to say")
    assert ok is True


def test_sentence_is_refused_even_when_short():
    ok, reason = field_core.value_fits(
        descriptor(widget="custom_combobox"), "Yes, I did.")
    assert (ok, reason) == (False, "not_an_option_label")


def test_long_run_on_label_is_refused():
    ok, reason = field_core.value_fits(
        descriptor(widget="custom_combobox"),
        "Currently pursuing a Master's in Computer Engineering")
    assert (ok, reason) == (False, "not_an_option_label")


def test_typeahead_is_treated_as_a_choice_control():
    ok, reason = field_core.value_fits(
        descriptor(widget="typeahead"), PARAGRAPH)
    assert (ok, reason) == (False, "not_an_option_label")


# --- groups -------------------------------------------------------------

def test_radio_group_accepts_a_long_member_label():
    """Member labels are known, so the 4-word budget must NOT apply — real
    EEO options are full sentences."""
    ok, _ = field_core.value_fits(
        descriptor(type="radio_group",
                   options=["I am a protected veteran",
                            "I am not a protected veteran",
                            "I don't wish to answer"]),
        "I am not a protected veteran")
    assert ok is True


def test_checkbox_group_accepts_a_member_label():
    ok, _ = field_core.value_fits(
        descriptor(type="checkbox_group",
                   options=["She/her/hers", "He/him/his", "They/them/theirs"]),
        "He/him/his")
    assert ok is True


def test_group_refuses_prose_that_is_not_a_member():
    ok, reason = field_core.value_fits(
        descriptor(type="checkbox_group",
                   options=["She/her/hers", "He/him/his"]),
        PARAGRAPH)
    assert ok is False
    assert reason in ("no_valid_option", "not_an_option_label")


def test_native_select_with_options_accepts_an_option():
    ok, _ = field_core.value_fits(
        descriptor(tag="select", widget="native_select",
                   options=["Select...", "Yes", "No"]),
        "Yes")
    assert ok is True


# --- free text ----------------------------------------------------------

def test_plain_free_text_accepts_prose():
    ok, _ = field_core.value_fits(
        descriptor(tag="textarea", label_text="Cover letter"), PARAGRAPH)
    assert ok is True


def test_maxlength_does_not_reject_it_is_a_truncation_concern():
    ok, _ = field_core.value_fits(
        descriptor(label_text="Notice period", maxlength=10),
        "Two weeks from the offer date")
    assert ok is True


# --- files --------------------------------------------------------------

def test_file_field_accepts_a_path():
    ok, _ = field_core.value_fits(
        descriptor(type="file", label_text="Resume/CV"),
        "/data/tailored/6532.pdf")
    assert ok is True


def test_file_field_refuses_prose():
    """A cover-letter file input was handed drafted prose and passed it to
    set_input_files as if it were a path."""
    ok, reason = field_core.value_fits(
        descriptor(type="file", label_text="Cover letter"), PARAGRAPH)
    assert (ok, reason) == (False, "wrong_shape")


# --- empties ------------------------------------------------------------

@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_values_never_fit(value):
    ok, reason = field_core.value_fits(descriptor(), value)
    assert (ok, reason) == (False, "empty")


def test_ok_results_carry_no_reason():
    ok, reason = field_core.value_fits(descriptor(), "Arlington, TX")
    assert ok is True
    assert reason == ""
