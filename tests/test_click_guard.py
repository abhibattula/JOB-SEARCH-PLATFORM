"""011 T003: the submit denylist — the single guarantee that the companion
(now allowed to click field widgets) never clicks a submit/apply/next/login
control. The Python guard is the source of truth; extension/content/
click_guard.js mirrors it (parity asserted in test_extension_assets)."""
import pytest

from engine.autofill import click_guard as cg


class TestDenied:
    @pytest.mark.parametrize("text", [
        "Submit", "Submit application", "Apply", "Apply now",
        "Next", "Continue", "Save", "Save and continue", "Finish",
        "Review and submit", "Log in", "Login", "Sign in", "Sign up",
        "Register", "Create account", "Pay", "Checkout", "Proceed to pay",
        "SUBMIT", "  submit  ", "Continue »",
    ])
    def test_submit_class_text_denied(self, text):
        assert cg.is_denylisted(text=text, type="button", role="button")

    def test_type_submit_denied_regardless_of_text(self):
        # a <button type=submit> with an innocuous label is still a submit
        assert cg.is_denylisted(text="Go", type="submit", role="")

    def test_disabled_next_still_denied(self):
        # the guard doesn't see 'disabled' — text/type/role decide; a Next
        # is denied whether or not it's disabled
        assert cg.is_denylisted(text="Next", type="button", role="button")


class TestAllowed:
    @pytest.mark.parametrize("text", [
        "Yes", "No", "Authorized to work in the US",
        "Not authorized", "United States", "Canada", "LinkedIn",
        "A friend", "Abhinav Battula", "Bachelor's degree",
        "Austin, TX", "5+ years", "Prefer not to say", "Male", "Female",
        "", "Select an option",
    ])
    def test_field_value_labels_allowed(self, text):
        assert not cg.is_denylisted(text=text, type="", role="option")

    def test_option_role_allowed(self):
        assert not cg.is_denylisted(text="Yes", type="", role="option")

    def test_plain_div_value_allowed(self):
        assert not cg.is_denylisted(text="Software Engineer", type="", role="")


class TestScope:
    """Clarify Q1: verdict from the clicked element's own text + descendants,
    NEVER ancestors. The caller passes the concatenated self+descendant text;
    a helper builds it so both backends compute the same thing."""

    def test_descendant_submit_denies(self):
        # a <div> the user would click that CONTAINS a submit button
        combined = cg.combined_signal(
            own_text="", own_type="", own_role="button",
            descendant_texts=["Submit application"],
            descendant_types=["submit"], descendant_roles=["button"],
        )
        assert cg.is_denylisted(**combined)

    def test_option_inside_form_with_submit_is_allowed(self):
        # the OPTION itself carries no submit signal; the form's Submit is an
        # ANCESTOR and must not be part of the signal
        combined = cg.combined_signal(
            own_text="Yes", own_type="", own_role="option",
            descendant_texts=[], descendant_types=[], descendant_roles=[],
        )
        assert not cg.is_denylisted(**combined)

    def test_option_labeled_next_step_is_denied(self):
        # defensive: an option whose own label is submit-class is refused
        combined = cg.combined_signal(
            own_text="Continue", own_type="", own_role="option",
            descendant_texts=[], descendant_types=[], descendant_roles=[],
        )
        assert cg.is_denylisted(**combined)


class TestExportedTerms:
    def test_patterns_exposed_for_parity_check(self):
        # the JS mirror is asserted identical in test_extension_assets; expose
        # the canonical term list here
        assert isinstance(cg.DENY_TERMS, (list, tuple))
        assert "submit" in cg.DENY_TERMS and "login" in cg.DENY_TERMS


class TestWidgetOwnNameJudgment019:
    """019 (T035, FR-012): a fillable widget is judged by its OWN accessible
    name. Folding descendant text made an ordinary dropdown unfillable
    whenever the card around it happened to contain "Next" or "Save"."""

    def test_widget_wrapper_with_progression_text_inside_is_fillable(self):
        assert cg.is_widget_operable(
            own_name="How did you hear about us?",
            descendant_text="Select… Next year Save the date",
            type_="", role="combobox") is True

    def test_an_option_labelled_next_year_is_selectable(self):
        assert cg.is_widget_operable(
            own_name="Next year", descendant_text="Next year",
            type_="", role="option") is True

    def test_a_real_submit_button_is_never_operable(self):
        assert cg.is_widget_operable(
            own_name="Submit application", descendant_text="Submit application",
            type_="submit", role="button") is False

    def test_a_real_next_button_is_never_operable(self):
        assert cg.is_widget_operable(
            own_name="Next", descendant_text="Next", type_="button",
            role="button") is False

    def test_a_wrapper_containing_a_submit_control_is_never_operable(self):
        """The real danger the 011 fold protected against is unchanged."""
        assert cg.is_widget_operable(
            own_name="Choose a date", descendant_text="Choose a date",
            type_="", role="combobox",
            descendant_types=["button", "submit"]) is False

    def test_fill_path_denylist_is_unchanged(self):
        assert cg.is_denylisted("Continue", "", "") is True
        assert cg.is_denylisted("anything", "submit", "") is True
