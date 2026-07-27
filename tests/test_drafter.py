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
