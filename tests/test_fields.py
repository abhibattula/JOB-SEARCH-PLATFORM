"""005-T010: engine/autofill/fields.py classifier — fixture-dict tests only,
no real browser/DOM handle involved (per plan.md's testability requirement).
"""
import pytest

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


class TestFactualHistoryTags017:
    """017-T019 (R6, FR-008): questions about the applicant's own history are
    unknowable from a resume. Every one of these was fabricated on the
    2026-07-28 Akuna run, so they get real tags and are never generated.
    """

    CASES = [
        ("Have you ever applied to a full time or internship position with "
         "Akuna in the past?", "applied_before"),
        ("Have you applied to this role at Akuna previously?",
         "applied_before"),
        ("Have you ever worked for us before?", "worked_here_before"),
        ("Are you a former employee of this company?", "worked_here_before"),
        ("Do you have prior experience working at an options market making "
         "firm?", "prior_industry_experience"),
        ("Did you complete our online Options 101 Course? If not, head to "
         "akunacapital.teachable.com for more information on this free "
         "course that is open to all (but not required in order to apply)!",
         "completed_course"),
        ("Do you have any offer deadlines that we should be aware of?",
         "offer_deadlines"),
        ("If you have upcoming deadlines, please indicate which company and "
         "when the deadline is:", "offer_deadlines"),
        ("Do you live in New York or California?", "residency_state"),
        ("Are you currently employed?", "currently_employed"),
        ("Have you ever been convicted of a felony?", "criminal_history"),
        ("Please provide three professional references.", "references"),
    ]

    @pytest.mark.parametrize("label,expected", CASES)
    def test_classified(self, label, expected):
        assert fields.classify(field(label_text=label)) == expected

    def test_none_of_them_fall_through_to_free_text(self):
        for label, _ in self.CASES:
            assert fields.classify(field(label_text=label)) != \
                "free_text_unknown", label

    def test_a_years_of_experience_question_is_unaffected(self):
        """Guard against the new prior-experience pattern swallowing the
        existing tag."""
        assert fields.classify(
            field(label_text="How many years of experience do you have?")
        ) == "years_experience"

    def test_a_city_question_is_unaffected(self):
        assert fields.classify(field(label_text="City")) == "location_city"


class TestNameAndPhoneRegressions017:
    """017-T033 (C3, C4): two wrong-value defects from the live Akuna run,
    both caused by patterns matching more text than they meant to."""

    def test_phonetically_is_not_a_phone_field(self):
        """_PHONE_RE had no word boundary, so "how your name is pronounced
        PHONEtically" matched and received the applicant's phone number."""
        label = ("We care about addressing everyone correctly. To help us get "
                 "it right, please write out how your name is pronounced "
                 "phonetically to share with the hiring team.")
        assert fields.classify(field(label_text=label)) != "phone"

    def test_a_real_phone_field_still_classifies(self):
        for label in ("Phone", "Phone*", "Mobile number", "Telephone",
                      "Cell phone"):
            assert fields.classify(field(label_text=label)) == "phone", label

    def test_someone_elses_name_is_not_the_applicants_name(self):
        """"please list their name" received the applicant's own name."""
        label = ("If you heard about Akuna through an Akuna employee, please "
                 "list their name:")
        assert fields.classify(field(label_text=label)) not in (
            "first_name", "last_name", "full_name")

    @pytest.mark.parametrize("label", [
        "Reference name",
        "Manager's name",
        "Emergency contact name",
        "Referrer name",
    ])
    def test_third_party_name_fields_are_not_claimed(self, label):
        assert fields.classify(field(label_text=label)) not in (
            "first_name", "last_name", "full_name")

    def test_preferred_name_is_its_own_tag(self):
        label = ("Do you have a preferred name, other than the name indicated "
                 "above? If yes, please indicate that name below.")
        assert fields.classify(field(label_text=label)) == "preferred_name"

    def test_middle_name_is_its_own_tag(self):
        assert fields.classify(field(label_text="Middle name")) == \
            "middle_name"

    def test_the_applicants_own_name_fields_still_classify(self):
        assert fields.classify(field(label_text="First Name*")) == "first_name"
        assert fields.classify(field(label_text="Last Name*")) == "last_name"
        assert fields.classify(field(label_text="Full name")) == "full_name"
        assert fields.classify(
            field(label_text="What is your legal first name?")) == "first_name"

    def test_lever_bare_name_attribute_is_unchanged(self):
        assert fields.classify(field(name="name")) == "full_name"


class TestLocationAndLibraryTags017:
    """017-T042/T044 (FR-021/FR-022): questions the profile can answer.

    `Country*` was left blank on the live run because no country tag existed,
    and Greenhouse's location field was mapped to free_text_unknown — so the
    model was asked to guess where the applicant lives.
    """

    LOCATION = [
        ("Country", "location_country"),
        ("Country*", "location_country"),
        ("State", "location_state"),
        ("State / Province", "location_state"),
        ("Zip code", "location_postal"),
        ("Postal code", "location_postal"),
        ("Street address", "location_address1"),
        ("Address line 2", "location_address2"),
        ("City", "location_city"),
    ]

    @pytest.mark.parametrize("label,expected", LOCATION)
    def test_location_tags(self, label, expected):
        assert fields.classify(field(label_text=label)) == expected

    LIBRARY = [
        ("Are you at least 18 years of age?", "age_18_plus"),
        ("Are you 18 years or older?", "age_18_plus"),
        ("Are you subject to a non-compete agreement?", "non_compete"),
        ("Do you hold an active security clearance?", "security_clearance"),
        ("Are you willing to undergo a background check?", "background_check"),
        ("Are you willing to submit to a drug test?", "drug_test"),
        ("Are you willing to relocate?", "relocate"),
        ("Are you willing to travel?", "travel"),
        ("What is your earliest start date?", "start_date"),
        ("What is your notice period?", "notice_period"),
        ("What is your GPA?", "gpa"),
        ("What education level are you currently pursuing?", "degree"),
        ("Graduation Month", "graduation_date"),
        ("Graduation Year", "graduation_date"),
    ]

    @pytest.mark.parametrize("label,expected", LIBRARY)
    def test_library_tags(self, label, expected):
        assert fields.classify(field(label_text=label)) == expected

    ACKNOWLEDGEMENTS = [
        ("I certify that all information I have provided in order to apply "
         "for this position with Akuna is true, complete, and accurate.",
         "acknowledgement"),
        ("I acknowledge that my resume must be submitted in PDF format to be "
         "considered.", "acknowledgement"),
    ]

    @pytest.mark.parametrize("label,expected", ACKNOWLEDGEMENTS)
    def test_acknowledgement_tag(self, label, expected):
        assert fields.classify(field(label_text=label)) == expected

    def test_a_binding_acknowledgement_is_recognised_as_binding(self):
        """D5: this one withdraws the applicant from every other Tech/Quant
        role at the firm for the season. It must never be auto-answered."""
        label = ("By submitting this application and answering “yes” below, I "
                 "acknowledge that this role is my top preference and I will "
                 "not be considered for other Tech and/or Quant roles at "
                 "Akuna for this recruiting season.")
        assert fields.classify(field(label_text=label)) == "acknowledgement"
        assert fields.is_binding_acknowledgement(label) is True

    def test_a_routine_acknowledgement_is_not_binding(self):
        assert fields.is_binding_acknowledgement(
            "I certify that all information I have provided is accurate."
        ) is False
