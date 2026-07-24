"""005-T010: engine/autofill/fields.py classifier — fixture-dict tests only,
no real browser/DOM handle involved (per plan.md's testability requirement).
"""
from engine.autofill import fields


def field(**overrides):
    base = {
        "tag": "input",
        "type": "text",
        "name": "",
        "id": "",
        "label_text": "",
        "placeholder": "",
        "aria_label": "",
        "autocomplete": "",
        "form_context": None,
    }
    base.update(overrides)
    return base


class TestBasicIdentityFields:
    def test_email_field(self):
        assert fields.classify(field(type="email", label_text="Email address")) == "email"

    def test_phone_field(self):
        assert fields.classify(field(type="tel", label_text="Phone number")) == "phone"

    def test_first_name(self):
        assert fields.classify(field(label_text="First Name")) == "first_name"

    def test_last_name(self):
        assert fields.classify(field(label_text="Last Name")) == "last_name"

    def test_full_name(self):
        assert fields.classify(field(label_text="Full Name")) == "full_name"

    def test_resume_upload_default_for_file_input(self):
        assert fields.classify(field(tag="input", type="file", label_text="Attach resume")) == "resume_upload"

    def test_resume_upload_default_for_unlabeled_file_input(self):
        # most lone file inputs on a job application are the resume
        assert fields.classify(field(tag="input", type="file", label_text="")) == "resume_upload"

    def test_linkedin_url(self):
        assert fields.classify(field(label_text="LinkedIn Profile URL")) == "linkedin_url"

    def test_portfolio_url(self):
        assert fields.classify(field(label_text="Portfolio / GitHub link")) == "portfolio_url"


class TestLegallySensitiveTagsWinOverGenericCatchAlls:
    """Checklist CHK005/CHK012 concern: these must be matched before any
    generic yes/no or free-text catch-all, and the taxonomy is open/extensible
    (spec FR-012) — not limited to two hardcoded categories."""

    def test_work_authorization(self):
        assert fields.classify(field(
            label_text="Are you legally authorized to work in the United States?"
        )) == "work_authorization"

    def test_sponsorship_requirement(self):
        assert fields.classify(field(
            label_text="Will you now or in the future require visa sponsorship?"
        )) == "sponsorship_requirement"

    def test_sponsorship_requirement_alternate_phrasing(self):
        assert fields.classify(field(
            label_text="Do you require sponsorship to work in this role?"
        )) == "sponsorship_requirement"

    def test_eeo_disclosure_disability(self):
        assert fields.classify(field(
            label_text="Do you have a disability? (Voluntary Self-Identification)"
        )) == "eeo_disclosure"

    def test_eeo_disclosure_veteran_status(self):
        assert fields.classify(field(
            label_text="Veteran Status"
        )) == "eeo_disclosure"

    def test_eeo_disclosure_not_confused_with_generic_yes_no(self):
        # A generic yes/no question that is NOT legally sensitive must not
        # be misclassified into a sensitive category just because it has a
        # question-like shape.
        result = fields.classify(field(label_text="Are you willing to relocate?"))
        assert result not in ("work_authorization", "sponsorship_requirement", "eeo_disclosure")


class TestQABank:
    def test_years_experience(self):
        assert fields.classify(field(label_text="Years of experience with Python")) == "years_experience"

    def test_salary_expectation(self):
        assert fields.classify(field(label_text="Desired salary / compensation")) == "salary_expectation"

    def test_how_heard(self):
        assert fields.classify(field(label_text="How did you hear about us?")) == "how_heard"

    def test_cover_letter_textarea(self):
        assert fields.classify(field(tag="textarea", label_text="Cover Letter")) == "cover_letter"

    def test_location_city_011(self):
        assert fields.classify(field(label_text="City")) == "location_city"
        assert fields.classify(field(label_text="Where are you located?")) == "location_city"
        assert fields.classify(field(label_text="Current location")) == "location_city"

    def test_school_011(self):
        assert fields.classify(field(label_text="School")) == "school"
        assert fields.classify(field(label_text="University or institution")) == "school"


class TestLoginFieldsRequireCorroboratingContext:
    """Checklist item: login_* tags must not fire on a bare type=password/
    type=email — a saved credential must never be routed into an unrelated
    profile field."""

    def test_password_type_alone_is_sufficient_for_login_password(self):
        # type="password" has no other legitimate use in a job application —
        # it is itself the corroborating signal.
        assert fields.classify(field(type="password", label_text="Password")) == "login_password"

    def test_bare_email_field_without_login_context_is_plain_email(self):
        assert fields.classify(field(type="email", label_text="Email")) == "email"

    def test_email_field_with_login_form_context_is_login_email(self):
        assert fields.classify(field(
            type="email", label_text="Email", autocomplete="username",
            form_context="login",
        )) == "login_email"

    def test_email_field_with_username_autocomplete_but_no_login_context_stays_plain_email(self):
        # autocomplete alone, without form_context="login", is not enough —
        # avoids misrouting a profile email field that merely reuses the
        # username autocomplete hint.
        assert fields.classify(field(
            type="email", label_text="Email", autocomplete="username",
        )) == "email"


class TestFallback:
    def test_unrecognized_text_field_is_free_text_unknown(self):
        assert fields.classify(field(label_text="Anything else you'd like to add?")) == "free_text_unknown"


class TestMatchOption:
    """007-T021 (FR-006): structured inputs (select/radio/checkbox) answer
    by choosing the option whose text best matches the confirmed answer —
    and stay untouched when no option matches confidently."""

    def test_exact_option_text_matches(self):
        assert fields.match_option("Yes", ["Yes", "No"]) == "Yes"

    def test_case_and_whitespace_insensitive(self):
        assert fields.match_option("yes", ["  Yes  ", "No"]) == "  Yes  "

    def test_answer_contained_in_longer_option(self):
        options = ["Yes, I am authorized", "No, I am not authorized"]
        assert fields.match_option("Yes", options) == "Yes, I am authorized"

    def test_fuzzy_phrasing_matches(self):
        options = ["LinkedIn", "Indeed", "Company website", "Other"]
        assert fields.match_option("Linked In", options) == "LinkedIn"

    def test_no_confident_match_returns_none(self):
        """Below the confidence threshold the input is left untouched and
        reported unfilled — never a wrong structured answer (FR-006)."""
        assert fields.match_option("Purple", ["Yes", "No"]) is None

    def test_yes_no_never_cross_matches(self):
        """'No' must never fuzzily land on a 'Yes...' option — this is the
        legally-dangerous failure mode for authorization dropdowns."""
        options = ["Yes, I am authorized", "No, I am not authorized"]
        assert fields.match_option("No", options) == "No, I am not authorized"

    def test_empty_inputs(self):
        assert fields.match_option("", ["Yes", "No"]) is None
        assert fields.match_option("Yes", []) is None


def raw_attr_field(**overrides):
    """A descriptor the way real ATS forms present it: NO label/placeholder/
    aria — only raw name/id attributes (the exact shape that silently never
    classified before 009: \s* does not match underscores)."""
    field = {"tag": "input", "type": "text", "name": "", "id": "",
             "label_text": "", "placeholder": "", "aria_label": "",
             "autocomplete": ""}
    field.update(overrides)
    return field


class TestRawAttributeClassification009:
    def test_greenhouse_style_underscore_names(self):
        assert fields.classify(raw_attr_field(name="first_name")) == "first_name"
        assert fields.classify(raw_attr_field(name="last_name")) == "last_name"
        assert fields.classify(raw_attr_field(name="full_name")) == "full_name"
        assert fields.classify(raw_attr_field(id="given_name")) == "first_name"
        assert fields.classify(raw_attr_field(id="family_name")) == "last_name"

    def test_qa_bank_underscore_names(self):
        assert fields.classify(raw_attr_field(name="years_experience")) == "years_experience"
        assert fields.classify(raw_attr_field(name="how_did_you_hear")) == "how_heard"
        assert fields.classify(raw_attr_field(name="pay_expectation")) == "salary_expectation"
        assert fields.classify(
            raw_attr_field(tag="textarea", name="cover_letter")
        ) == "cover_letter"
        assert fields.classify(raw_attr_field(name="personal_website")) == "portfolio_url"

    def test_hyphen_and_compact_variants(self):
        assert fields.classify(raw_attr_field(name="first-name")) == "first_name"
        assert fields.classify(raw_attr_field(name="firstname")) == "first_name"
        assert fields.classify(raw_attr_field(id="lastname")) == "last_name"

    def test_autocomplete_attribute_classifies(self):
        assert fields.classify(raw_attr_field(autocomplete="given-name")) == "first_name"
        assert fields.classify(raw_attr_field(autocomplete="family-name")) == "last_name"
        assert fields.classify(raw_attr_field(autocomplete="name")) == "full_name"
        assert fields.classify(raw_attr_field(autocomplete="email")) == "email"
        assert fields.classify(raw_attr_field(autocomplete="tel")) == "phone"

    def test_lever_bare_name_attribute_is_full_name(self):
        assert fields.classify(raw_attr_field(name="name")) == "full_name"

    def test_sensitive_categories_still_win_over_identity(self):
        # regression guard: separator widening must not weaken precedence
        field = raw_attr_field(name="first_name",
                              label_text="Are you authorized to work in the US?")
        assert fields.classify(field) == "work_authorization"
