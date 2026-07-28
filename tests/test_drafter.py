"""016 (T003): the bounded background drafter — one draft per unique
question per session, bounded pool, exponential backoff, sensitive
denylist, option validation, ordered completion side effects.

All tests use the generator/bank seams — no model is ever loaded.
"""
import threading
import time

import pytest

from engine.autofill import drafter


@pytest.fixture(autouse=True)
def clean_drafter():
    drafter.reset_for_tests(backoff_base_s=0.15, backoff_cap_s=1.0)
    yield
    drafter.reset_for_tests()


def wait_until(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def ctx(**over):
    base = {"type": "text", "options": [], "maxlength": None,
            "tag": "free_text_unknown", "widget": ""}
    base.update(over)
    return base


PROFILE = {"name": "Abhinav"}


class TestOneDraftPerKey:
    def test_hammered_ensure_generates_exactly_once(self):
        calls = []

        def gen(question, dctx, profile):
            calls.append(question)
            time.sleep(0.05)
            return "drafted answer"

        drafter.set_generator_for_tests(gen)
        threads = [threading.Thread(
            target=drafter.ensure,
            args=(7, "Why do you want this job?", ctx(), PROFILE))
            for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert wait_until(
            lambda: drafter.answer_for(7, "Why do you want this job?"))
        assert len(calls) == 1

    def test_normalization_coalesces_whitespace_and_case(self):
        calls = []
        drafter.set_generator_for_tests(
            lambda q, c, p: calls.append(q) or "ans")
        drafter.ensure(7, "  Why   US? ", ctx(), PROFILE)
        drafter.ensure(7, "why us?", ctx(), PROFILE)
        assert wait_until(lambda: drafter.answer_for(7, "why us?"))
        assert len(calls) == 1

    def test_same_question_different_jobs_draft_separately(self):
        calls = []
        drafter.set_generator_for_tests(
            lambda q, c, p: calls.append(q) or "ans")
        drafter.ensure(1, "Why us?", ctx(), PROFILE)
        drafter.ensure(2, "Why us?", ctx(), PROFILE)
        assert wait_until(lambda: drafter.answer_for(1, "Why us?")
                          and drafter.answer_for(2, "Why us?"))
        assert len(calls) == 2


class TestBoundedPool:
    def test_max_two_concurrent_generations(self):
        active = []
        peak = []
        lock = threading.Lock()

        def gen(question, dctx, profile):
            with lock:
                active.append(1)
                peak.append(len(active))
            time.sleep(0.08)
            with lock:
                active.pop()
            return "x"

        drafter.set_generator_for_tests(gen)
        for i in range(6):
            drafter.ensure(9, f"question {i}?", ctx(), PROFILE)
        assert wait_until(
            lambda: all(drafter.answer_for(9, f"question {i}?")
                        for i in range(6)))
        assert max(peak) <= 2


class TestValidation:
    def test_option_answer_stored_canonically(self):
        drafter.set_generator_for_tests(lambda q, c, p: "  yes, i am  ")
        drafter.ensure(3, "Are you authorized?",
                       ctx(type="select", options=["No", "Yes, I am"]),
                       PROFILE)
        assert wait_until(lambda: drafter.answer_for(3, "Are you authorized?"))
        assert drafter.answer_for(3, "Are you authorized?") == "Yes, I am"

    def test_non_option_answer_fails_not_filled(self):
        drafter.set_generator_for_tests(
            lambda q, c, p: "A long descriptive paragraph about my history.")
        drafter.ensure(3, "Authorized?",
                       ctx(type="select", options=["Yes", "No"]), PROFILE)
        assert wait_until(
            lambda: (drafter.get(3, "Authorized?") or {}).get("state")
            == "failed")
        rec = drafter.get(3, "Authorized?")
        assert rec["reason"] == "no_valid_option"
        assert drafter.answer_for(3, "Authorized?") is None

    def test_maxlength_truncates(self):
        drafter.set_generator_for_tests(lambda q, c, p: "abcdefghij-tail")
        drafter.ensure(3, "Short one?", ctx(maxlength=10), PROFILE)
        assert wait_until(lambda: drafter.answer_for(3, "Short one?"))
        assert len(drafter.answer_for(3, "Short one?")) <= 10


class TestSensitive:
    def test_sensitive_tag_never_generates(self):
        called = []
        drafter.set_generator_for_tests(lambda q, c, p: called.append(1) or "x")
        drafter.ensure(4, "What is your ethnicity?",
                       ctx(tag="eeo_disclosure"), PROFILE)
        rec = drafter.get(4, "What is your ethnicity?")
        assert rec["state"] == "failed" and rec["reason"] == "sensitive"
        time.sleep(0.1)
        assert not called

    def test_sensitive_tags_cover_the_specified_classes(self):
        for tag in ("eeo_disclosure", "demographics", "disability",
                    "veteran_status", "criminal_history", "references"):
            assert tag in drafter.SENSITIVE_TAGS


class TestBackoff:
    def test_failure_backs_off_then_retries_and_doubles(self):
        calls = []
        drafter.set_generator_for_tests(lambda q, c, p: calls.append(1) and None)
        drafter.ensure(5, "Hard one?", ctx(), PROFILE)
        assert wait_until(
            lambda: (drafter.get(5, "Hard one?") or {}).get("state") == "failed")
        assert len(calls) == 1
        drafter.ensure(5, "Hard one?", ctx(), PROFILE)  # inside backoff window
        time.sleep(0.05)
        assert len(calls) == 1
        time.sleep(0.15)  # base window passed
        drafter.ensure(5, "Hard one?", ctx(), PROFILE)
        assert wait_until(lambda: len(calls) == 2)
        rec = drafter.get(5, "Hard one?")
        assert rec["attempts"] == 2
        # second failure waits ~2x base
        gap = rec["next_retry_at"] - time.monotonic()
        assert gap > 0.2

    def test_reset_backoff_for_re_arms_immediately(self):
        calls = []
        drafter.set_generator_for_tests(lambda q, c, p: calls.append(1) and None)
        drafter.ensure(5, "Hard one?", ctx(), PROFILE)
        assert wait_until(
            lambda: (drafter.get(5, "Hard one?") or {}).get("state") == "failed")
        drafter.reset_backoff_for(5, ["Hard one?"])
        drafter.ensure(5, "Hard one?", ctx(), PROFILE)
        assert wait_until(lambda: len(calls) == 2)


class TestCompletionSideEffects:
    def test_cache_version_bumps_per_completion(self):
        drafter.set_generator_for_tests(lambda q, c, p: "ans")
        v0 = drafter.cache_version()
        drafter.ensure(6, "q1?", ctx(), PROFILE)
        assert wait_until(lambda: drafter.cache_version() == v0 + 1)
        drafter.ensure(6, "q2?", ctx(), PROFILE)
        assert wait_until(lambda: drafter.cache_version() == v0 + 2)

    def test_bank_save_then_callback_with_answer_available(self):
        events = []
        drafter.set_generator_for_tests(lambda q, c, p: "ans")
        drafter.set_bank_save_for_tests(
            lambda **kw: events.append(("bank", kw)))
        drafter.register_on_complete(
            lambda job_id, question, answer: events.append(
                ("cb", drafter.answer_for(job_id, question))))
        drafter.ensure(6, "q?", ctx(tag="cover_letter"), PROFILE)
        assert wait_until(lambda: len(events) == 2)
        assert events[0][0] == "bank" and events[1] == ("cb", "ans")

    def test_bank_save_scoping_job_specific_vs_agnostic(self):
        saves = []
        drafter.set_generator_for_tests(lambda q, c, p: "ans")
        drafter.set_bank_save_for_tests(lambda **kw: saves.append(kw))
        drafter.ensure(11, "Cover letter?", ctx(tag="cover_letter"), PROFILE)
        drafter.ensure(11, "Notice period?", ctx(tag="notice_period"), PROFILE)
        assert wait_until(lambda: len(saves) == 2)
        by_tag = {s["tag"]: s for s in saves}
        assert by_tag["cover_letter"]["job_id"] == 11      # job-scoped prose
        assert by_tag["notice_period"]["job_id"] is None   # reusable fact
        assert all(s["origin"] == "ai" for s in saves)


class TestConstrainedDrafting016:
    """016 (T012): the drafter's default generator forwards the descriptor
    context, and combobox answers must be short option labels."""

    def test_default_generator_passes_ctx_to_suggest(self, monkeypatch):
        from engine.autofill import answer_bank

        seen = {}

        def fake_suggest(question, category, profile, descriptor_ctx=None):
            seen["ctx"] = descriptor_ctx
            return "Yes"

        monkeypatch.setattr(answer_bank, "suggest", fake_suggest)
        drafter.set_bank_save_for_tests(lambda **kw: None)
        drafter.ensure(3, "Are you authorized?",
                       ctx(type="select", options=["Yes", "No"],
                           tag="work_authorization"), PROFILE)
        assert wait_until(lambda: drafter.answer_for(3, "Are you authorized?"))
        assert seen["ctx"]["options"] == ["Yes", "No"]

    def test_combobox_long_answer_fails_not_filled(self):
        drafter.set_generator_for_tests(
            lambda q, c, p: "a rambling answer of far too many words to be "
                            "an option label")
        drafter.ensure(3, "Source?", ctx(widget="custom_combobox"), PROFILE)
        assert wait_until(
            lambda: (drafter.get(3, "Source?") or {}).get("state") == "failed")
        assert drafter.get(3, "Source?")["reason"] == "not_an_option_label"

    def test_combobox_short_label_passes(self):
        drafter.set_generator_for_tests(lambda q, c, p: "LinkedIn")
        drafter.ensure(3, "Source?", ctx(widget="custom_combobox"), PROFILE)
        assert wait_until(lambda: drafter.answer_for(3, "Source?"))
        assert drafter.answer_for(3, "Source?") == "LinkedIn"


class TestFillAgainReset016:
    def test_reset_backoff_for_job_rearms_all_failed_non_sensitive(self):
        drafter.set_generator_for_tests(lambda q, c, p: None)
        drafter.ensure(9, "Hard A?", ctx(), PROFILE)
        drafter.ensure(9, "Hard B?", ctx(), PROFILE)
        drafter.mark_needs_you(9, "Ethnicity?", "sensitive")
        assert wait_until(
            lambda: all((drafter.get(9, q) or {}).get("state") == "failed"
                        for q in ("Hard A?", "Hard B?")))
        drafter.reset_backoff_for_job(9)
        assert drafter.get(9, "Hard A?")["next_retry_at"] == 0.0
        assert drafter.get(9, "Hard B?")["next_retry_at"] == 0.0
        assert drafter.get(9, "Ethnicity?")["next_retry_at"] == float("inf")


class TestNoRegenerationLoop017:
    """017-T011 (R1, corrected): characterisation tests.

    An earlier reading of the 2026-07-28 live run claimed a self-feeding loop
    in which every completed draft re-armed every other failed draft for the
    job. Reading the code disproved it — `reset_backoff_for_job` is reachable
    only from the explicit `fill_again` handler, and `on_draft_complete`
    touches no drafter state. These tests pin that behaviour so a future
    change cannot quietly introduce the loop that was feared.
    """

    def test_completing_one_draft_does_not_rearm_a_failed_sibling(self):
        answers = {"Easy?": "Yes"}

        def gen(question, dctx, profile):
            return answers.get(question)  # None => failure for the sibling

        drafter.set_generator_for_tests(gen)
        drafter.ensure(11, "Hard?", ctx(), PROFILE)
        assert wait_until(
            lambda: (drafter.get(11, "Hard?") or {}).get("state") == "failed")
        armed_at = drafter.get(11, "Hard?")["next_retry_at"]
        assert armed_at > 0.0

        drafter.ensure(11, "Easy?", ctx(), PROFILE)
        assert wait_until(lambda: drafter.answer_for(11, "Easy?") == "Yes")

        assert drafter.get(11, "Hard?")["next_retry_at"] == armed_at, \
            "a completed draft must not re-arm another question's backoff"

    def test_a_repeated_scan_loop_generates_each_question_once(self):
        """What a real 90-field form does: the same descriptors are decided
        again every couple of seconds."""
        calls = []

        def gen(question, dctx, profile):
            calls.append(question)
            return "An answer"

        drafter.set_generator_for_tests(gen)
        questions = ["Graduation Month*", "What is your GPA?*",
                     "Have you applied before?*"]
        for _ in range(25):
            for question in questions:
                drafter.ensure(12, question, ctx(), PROFILE)
        assert wait_until(
            lambda: all(drafter.answer_for(12, q) for q in questions))
        for _ in range(25):
            for question in questions:
                drafter.ensure(12, question, ctx(), PROFILE)

        assert sorted(calls) == sorted(questions), \
            f"expected one generation per question, got {len(calls)}"

    def test_question_keys_are_normalised_so_markers_do_not_fragment(self):
        """A required marker or stray whitespace in the label must not create
        a second record for the same question."""
        calls = []

        def gen(question, dctx, profile):
            calls.append(question)
            return "An answer"

        drafter.set_generator_for_tests(gen)
        for variant in ("Graduation Month*", "Graduation Month* ",
                        "  Graduation Month*", "Graduation  Month*"):
            drafter.ensure(13, variant, ctx(), PROFILE)
        assert wait_until(lambda: drafter.answer_for(13, "Graduation Month*"))
        assert len(calls) == 1, f"one question fragmented into {len(calls)}"


class TestGenerationBounds017:
    """017-T013 (R2, FR-002/FR-003): generation is bounded.

    The drafter is already idempotent per question, so these are guards, not
    repairs: a pathological form must not be able to spend unbounded model
    time, and a question that keeps failing must end up with the human
    instead of retrying forever.
    """

    def test_a_question_stops_after_the_attempt_cap(self):
        calls = []

        def gen(question, dctx, profile):
            calls.append(question)
            return None  # never validates

        drafter.reset_for_tests(backoff_base_s=0.01, backoff_cap_s=0.02,
                               max_attempts=2)
        drafter.set_generator_for_tests(gen)

        for _ in range(20):
            drafter.ensure(21, "Impossible?", ctx(), PROFILE)
            time.sleep(0.03)

        assert len(calls) == 2, f"attempt cap ignored: {len(calls)} calls"
        record = drafter.get(21, "Impossible?")
        assert record["state"] == "failed"
        assert record["reason"] == "attempts_exhausted"

    def test_an_exhausted_question_is_handed_to_the_human(self):
        drafter.reset_for_tests(backoff_base_s=0.01, backoff_cap_s=0.02,
                               max_attempts=1)
        drafter.set_generator_for_tests(lambda q, c, p: None)
        drafter.ensure(22, "Impossible?", ctx(), PROFILE)
        assert wait_until(
            lambda: (drafter.get(22, "Impossible?") or {}).get("reason")
            == "attempts_exhausted")

        entries = drafter.list_for_job(22)
        assert [e["state"] for e in entries] == ["needs_you"]

    def test_an_exhausted_question_is_not_re_armed_by_fill_again(self):
        """Fill again re-arms retryable failures only — an exhausted question
        would just burn the same budget again."""
        drafter.reset_for_tests(backoff_base_s=0.01, backoff_cap_s=0.02,
                               max_attempts=1)
        drafter.set_generator_for_tests(lambda q, c, p: None)
        drafter.ensure(23, "Impossible?", ctx(), PROFILE)
        assert wait_until(
            lambda: (drafter.get(23, "Impossible?") or {}).get("reason")
            == "attempts_exhausted")

        drafter.reset_backoff_for_job(23)
        assert drafter.get(23, "Impossible?")["next_retry_at"] == float("inf")

    def test_a_job_cannot_exceed_its_draft_budget(self):
        calls = []

        def gen(question, dctx, profile):
            calls.append(question)
            return "An answer"

        drafter.reset_for_tests(max_drafts_per_job=3)
        drafter.set_generator_for_tests(gen)

        for index in range(10):
            drafter.ensure(24, f"Question {index}?", ctx(), PROFILE)
        assert wait_until(lambda: len(calls) >= 3)
        time.sleep(0.2)

        assert len(calls) == 3, f"job budget ignored: {len(calls)} generations"
        beyond = drafter.get(24, "Question 9?")
        assert beyond["state"] == "failed"
        assert beyond["reason"] == "job_budget_exhausted"

    def test_the_budget_is_per_job_not_global(self):
        calls = []

        drafter.reset_for_tests(max_drafts_per_job=2)
        drafter.set_generator_for_tests(
            lambda q, c, p: calls.append(q) or "An answer")

        for index in range(3):
            drafter.ensure(25, f"Q{index}?", ctx(), PROFILE)
        for index in range(3):
            drafter.ensure(26, f"Q{index}?", ctx(), PROFILE)
        assert wait_until(lambda: len(calls) >= 4)
        time.sleep(0.2)

        assert len(calls) == 4, "each job gets its own budget"


class TestRefusalIsTerminal017:
    """017-T015 (FR-006): a refusal ends the question — retrying cannot
    conjure a fact the applicant never gave us."""

    def test_a_refusal_becomes_a_non_retryable_needs_you(self):
        from engine.autofill import answer_bank

        calls = []

        def gen(question, dctx, profile):
            calls.append(question)
            return answer_bank.REFUSAL_TOKEN

        drafter.reset_for_tests(backoff_base_s=0.01, backoff_cap_s=0.02)
        drafter.set_generator_for_tests(gen)
        question = "Do you have any offer deadlines that we should be aware of?"
        drafter.ensure(31, question, ctx(), PROFILE)
        assert wait_until(
            lambda: (drafter.get(31, question) or {}).get("state") == "failed")

        record = drafter.get(31, question)
        assert record["reason"] == "cannot_answer"
        assert record["next_retry_at"] == float("inf")
        assert drafter.answer_for(31, question) is None

        for _ in range(10):
            drafter.ensure(31, question, ctx(), PROFILE)
            time.sleep(0.02)
        assert len(calls) == 1, "a refusal must never be retried"

    def test_a_refusal_is_shown_to_the_applicant(self):
        from engine.autofill import answer_bank

        drafter.set_generator_for_tests(
            lambda q, c, p: answer_bank.REFUSAL_TOKEN)
        drafter.ensure(32, "Did you complete our Options 101 course?", ctx(),
                       PROFILE)
        assert wait_until(
            lambda: (drafter.get(32, "Did you complete our Options 101 "
                                 "course?") or {}).get("reason")
            == "cannot_answer")
        entries = drafter.list_for_job(32)
        assert [e["state"] for e in entries] == ["needs_you"]

    def test_a_refusal_is_never_saved_to_the_answer_bank(self):
        """The token must not become a reusable "answer" for this question."""
        from engine.autofill import answer_bank

        saved = []
        drafter.set_bank_save_for_tests(
            lambda **kw: saved.append(kw))
        drafter.set_generator_for_tests(
            lambda q, c, p: answer_bank.REFUSAL_TOKEN)
        drafter.ensure(33, "Do you live in New York or California?", ctx(),
                       PROFILE)
        assert wait_until(
            lambda: (drafter.get(33, "Do you live in New York or "
                                 "California?") or {}).get("state") == "failed")
        assert saved == []


class TestNeverGenerated017:
    """017-T019/T020 (FR-008): the model never sees a question about the
    applicant's own history or self-identification."""

    QUESTIONS = [
        ("applied_before", "Have you ever applied to a full time or "
                           "internship position with Akuna in the past?"),
        ("prior_industry_experience", "Do you have prior experience working "
                                      "at an options market making firm?"),
        ("completed_course", "Did you complete our online Options 101 "
                             "Course?"),
        ("offer_deadlines", "Do you have any offer deadlines that we should "
                            "be aware of?"),
        ("residency_state", "Do you live in New York or California?"),
        ("criminal_history", "Have you ever been convicted of a felony?"),
        ("references", "Please provide three professional references."),
        ("selfid_gender", "How would you describe your gender identity?"),
        ("selfid_orientation", "How would you describe your sexual "
                               "orientation?"),
        ("pronouns", "Add your personal pronouns below."),
    ]

    @pytest.mark.parametrize("tag,question", QUESTIONS)
    def test_the_generator_is_never_invoked(self, tag, question):
        calls = []
        drafter.set_generator_for_tests(
            lambda q, c, p: calls.append(q) or "Yes, definitely.")
        drafter.ensure(41, question, ctx(tag=tag), PROFILE)
        time.sleep(0.05)
        assert calls == [], f"{tag} reached the generator"
        assert drafter.answer_for(41, question) is None

    @pytest.mark.parametrize("tag,question", QUESTIONS)
    def test_it_is_handed_to_the_applicant_instead(self, tag, question):
        drafter.set_generator_for_tests(lambda q, c, p: "Yes")
        drafter.ensure(42, question, ctx(tag=tag), PROFILE)
        record = drafter.get(42, question)
        assert record["state"] == "failed"
        assert record["reason"] in drafter._NEEDS_YOU_REASONS

    def test_the_016_alias_still_resolves(self):
        assert drafter.SENSITIVE_TAGS is drafter.NEVER_GENERATED_TAGS
        assert "eeo_disclosure" in drafter.NEVER_GENERATED_TAGS
