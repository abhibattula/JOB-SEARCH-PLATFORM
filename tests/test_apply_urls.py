"""009 T004: posting URL → application-form URL resolution (root cause A2:
the stored job.url is the description page; the form lives elsewhere on
Lever/Ashby)."""
from engine.autofill import apply_urls


def job(url):
    return {"url": url}


class TestResolve:
    def test_lever_posting_gets_apply_suffix(self):
        assert apply_urls.resolve(job(
            "https://jobs.lever.co/tenstorrent/1234-abcd"
        )) == "https://jobs.lever.co/tenstorrent/1234-abcd/apply"

    def test_lever_already_apply_is_idempotent(self):
        url = "https://jobs.lever.co/tenstorrent/1234-abcd/apply"
        assert apply_urls.resolve(job(url)) == url

    def test_lever_query_string_preserved(self):
        assert apply_urls.resolve(job(
            "https://jobs.lever.co/org/12?lever-origin=applied"
        )) == "https://jobs.lever.co/org/12/apply?lever-origin=applied"

    def test_ashby_posting_gets_application_suffix(self):
        assert apply_urls.resolve(job(
            "https://jobs.ashbyhq.com/openai/5678-efgh"
        )) == "https://jobs.ashbyhq.com/openai/5678-efgh/application"

    def test_ashby_already_application_is_idempotent(self):
        url = "https://jobs.ashbyhq.com/openai/5678-efgh/application"
        assert apply_urls.resolve(job(url)) == url

    def test_greenhouse_left_as_is(self):
        for url in (
            "https://boards.greenhouse.io/stripe/jobs/12345",
            "https://job-boards.greenhouse.io/stripe/jobs/12345",
        ):
            assert apply_urls.resolve(job(url)) == url

    def test_unknown_hosts_left_as_is(self):
        for url in (
            "https://www.indeed.com/viewjob?jk=abc123",
            "https://apply.workable.com/huggingface/j/ABCDEF/",
            "https://example.com/careers/42",
        ):
            assert apply_urls.resolve(job(url)) == url

    def test_lever_org_root_not_suffixed(self):
        # an org landing page (no posting id) must not become /apply
        url = "https://jobs.lever.co/tenstorrent"
        assert apply_urls.resolve(job(url)) == url
