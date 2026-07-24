"""009 T005: deterministic per-ATS field maps — exact name/id attributes
from real Greenhouse/Lever/Ashby markup, consulted before the generic
classifier."""
from engine.autofill import adapters


def d(**overrides):
    field = {"tag": "input", "type": "text", "name": "", "id": "",
             "label_text": "", "placeholder": "", "aria_label": "",
             "autocomplete": "", "automation_id": ""}
    field.update(overrides)
    return field


class TestAtsFromUrl:
    def test_known_hosts(self):
        assert adapters.ats_from_url("https://boards.greenhouse.io/stripe/jobs/1") == "greenhouse"
        assert adapters.ats_from_url("https://job-boards.greenhouse.io/stripe/jobs/1") == "greenhouse"
        assert adapters.ats_from_url("https://jobs.lever.co/org/id/apply") == "lever"
        assert adapters.ats_from_url("https://jobs.ashbyhq.com/org/id/application") == "ashby"

    def test_unknown_hosts_none(self):
        assert adapters.ats_from_url("https://www.indeed.com/viewjob?jk=x") is None
        assert adapters.ats_from_url("") is None


class TestGreenhouseMap:
    def test_native_names(self):
        assert adapters.classify("greenhouse", d(name="first_name")) == "first_name"
        assert adapters.classify("greenhouse", d(name="last_name")) == "last_name"
        assert adapters.classify("greenhouse", d(name="email")) == "email"
        assert adapters.classify("greenhouse", d(name="phone")) == "phone"
        assert adapters.classify("greenhouse", d(name="resume", type="file")) == "resume_upload"
        assert adapters.classify("greenhouse", d(name="cover_letter", type="file")) == "cover_letter"

    def test_classic_embed_bracket_names(self):
        assert adapters.classify(
            "greenhouse", d(name="job_application[first_name]")
        ) == "first_name"
        assert adapters.classify(
            "greenhouse", d(name="job_application[email]")
        ) == "email"

    def test_unknown_custom_question_returns_none(self):
        assert adapters.classify(
            "greenhouse", d(name="job_application[answers_attributes][0][text_value]")
        ) is None


class TestLeverMap:
    def test_native_names(self):
        assert adapters.classify("lever", d(name="name")) == "full_name"
        assert adapters.classify("lever", d(name="email")) == "email"
        assert adapters.classify("lever", d(name="phone")) == "phone"
        assert adapters.classify("lever", d(name="resume", type="file")) == "resume_upload"
        assert adapters.classify("lever", d(name="urls[LinkedIn]")) == "linkedin_url"
        assert adapters.classify("lever", d(name="urls[GitHub]")) == "portfolio_url"
        assert adapters.classify("lever", d(name="urls[Portfolio]")) == "portfolio_url"
        assert adapters.classify("lever", d(name="comments", tag="textarea")) == "cover_letter"


class TestAshbyMap:
    def test_systemfield_ids(self):
        assert adapters.classify("ashby", d(id="_systemfield_name")) == "full_name"
        assert adapters.classify("ashby", d(id="_systemfield_email")) == "email"
        assert adapters.classify("ashby", d(id="_systemfield_phone")) == "phone"
        assert adapters.classify(
            "ashby", d(id="_systemfield_resume", type="file")
        ) == "resume_upload"


class TestSharedAutocomplete:
    def test_autocomplete_map_applies_on_any_known_ats(self):
        assert adapters.classify("greenhouse", d(autocomplete="given-name")) == "first_name"
        assert adapters.classify("lever", d(autocomplete="family-name")) == "last_name"
        assert adapters.classify("ashby", d(autocomplete="tel")) == "phone"


class TestWorkday011:
    def test_host_detection_dynamic_subdomains(self):
        assert adapters.ats_from_url(
            "https://nvidia.wd5.myworkdayjobs.com/en-US/apply") == "workday"
        assert adapters.ats_from_url(
            "https://amd.wd1.myworkdayjobs.com/careers") == "workday"
        assert adapters.ats_from_url(
            "https://foo.myworkdayjobs.com/x") == "workday"

    def test_data_automation_id_map(self):
        assert adapters.classify(
            "workday", d(automation_id="legalNameSection_firstName")) == "first_name"
        assert adapters.classify(
            "workday", d(automation_id="legalNameSection_lastName")) == "last_name"
        assert adapters.classify("workday", d(automation_id="email")) == "email"
        assert adapters.classify(
            "workday", d(automation_id="phone-number")) == "phone"
        assert adapters.classify(
            "workday", d(automation_id="addressSection_city")) == "location_city"

    def test_unknown_automation_id_falls_through(self):
        assert adapters.classify(
            "workday", d(automation_id="somethingWeirdTenantSpecific")) is None


class TestIcimsTaleo011:
    def test_icims_host_and_fields(self):
        assert adapters.ats_from_url(
            "https://careers-acme.icims.com/jobs/123/apply") == "icims"
        assert adapters.classify("icims", d(id="firstname")) == "first_name"
        assert adapters.classify("icims", d(id="lastname")) == "last_name"
        assert adapters.classify("icims", d(id="email")) == "email"

    def test_taleo_host_and_fields(self):
        assert adapters.ats_from_url(
            "https://acme.taleo.net/careersection/x") == "taleo"
        assert adapters.classify("taleo", d(name="firstName")) == "first_name"
        assert adapters.classify("taleo", d(name="lastName")) == "last_name"


class TestUnknownAts:
    def test_none_ats_returns_none(self):
        assert adapters.classify(None, d(name="first_name")) is None
        # workday keys on data-automation-id, so a bare name is not mapped
        assert adapters.classify("workday", d(name="first_name")) is None
