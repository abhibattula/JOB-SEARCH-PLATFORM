"""019 (T057): the escort's judgment — when the app may advance a wizard.

Pure logic, no browser, no sockets. Every refusal in `should_advance` is a
constitutional condition (v1.2.0: allowlist-first, one-shot per rendered
step, capped, paused on needs-you / bot check / ambiguity), so each one gets
a row here. A missing row is a permission nobody checked.
"""
import pytest

from engine.autofill import escort


def step(**over):
    """A step that WOULD advance, so each test can spoil exactly one thing."""
    base = dict(doc="docA", fieldset_hash="f1", visible_required_pending=0,
                inflight=0, needs_you=0, focused=False, captcha=False,
                missing_login=False, quiet_for=5.0, seen=6)
    base.update(over)
    return escort.StepView(**base)


class TestTheHappyPath:
    def test_a_complete_quiet_step_advances(self):
        d = escort.Escort().should_advance(step())
        assert d.advance is True
        assert d.kind == "next"
        assert d.reason == "step_complete"

    def test_the_decision_is_truthy_only_when_it_advances(self):
        e = escort.Escort()
        assert bool(e.should_advance(step()))
        assert not bool(e.should_advance(step(needs_you=1)))


class TestEveryRefusal:
    """Each row is a condition the constitution requires."""

    @pytest.mark.parametrize("spoiler,reason,state", [
        ({"captcha": True}, "captcha", escort.STATE_CAPTCHA),
        ({"missing_login": True}, "no_saved_login", escort.STATE_NEEDS_LOGIN),
        ({"needs_you": 1}, "needs_you", escort.STATE_ESCORTING),
        ({"focused": True}, "user_typing", escort.STATE_ESCORTING),
        ({"inflight": 1}, "fill_in_flight", escort.STATE_ESCORTING),
        ({"visible_required_pending": 1}, "required_pending",
         escort.STATE_ESCORTING),
        ({"seen": 0}, "no_fields", escort.STATE_ESCORTING),
        ({"quiet_for": 0.2}, "still_settling", escort.STATE_ESCORTING),
    ])
    def test_it_refuses(self, spoiler, reason, state):
        d = escort.Escort().should_advance(step(**spoiler))
        assert d.advance is False
        assert d.reason == reason
        assert d.state == state

    def test_a_bot_check_outranks_a_complete_step(self):
        """FR-028 + the edge case: a challenge can appear beside a form that
        is otherwise finished. Detection wins."""
        d = escort.Escort().should_advance(step(captcha=True, needs_you=0))
        assert d.state == escort.STATE_CAPTCHA

    def test_needs_you_outranks_typing(self):
        d = escort.Escort().should_advance(step(needs_you=1, focused=True))
        assert d.reason == "needs_you"

    def test_the_escort_can_be_turned_off(self):
        e = escort.Escort(enabled=False)
        assert e.should_advance(step()).reason == "escort_off"

    def test_it_never_acts_across_a_version_mismatch(self):
        """FR-035: the page is running code that does not match this app."""
        d = escort.Escort().should_advance(step(), version_ok=False)
        assert d.advance is False
        assert d.reason == "version_mismatch"

    def test_it_never_acts_on_an_automation_hostile_host(self):
        """FR-033: LinkedIn. Filling continues; clicking does not happen."""
        d = escort.Escort().should_advance(step(), clickable_host=False)
        assert d.advance is False
        assert d.reason == "no_click_host"


class TestOneShotPerStep:
    def test_the_same_step_advances_once(self):
        e = escort.Escort()
        s = step()
        assert e.should_advance(s).advance is True
        e.note_advance(s.key)
        assert e.should_advance(s).reason == "already_advanced"

    def test_a_new_step_in_the_same_document_advances(self):
        """The SPA case: same address, same doc token, different form. The
        fieldset is what makes it a different step."""
        e = escort.Escort()
        first = step(fieldset_hash="f1")
        e.note_advance(first.key)
        assert e.should_advance(step(fieldset_hash="f2")).advance is True

    def test_a_new_document_advances(self):
        e = escort.Escort()
        e.note_advance(step(doc="docA").key)
        assert e.should_advance(step(doc="docB")).advance is True


class TestTheCap:
    def test_it_stops_at_twelve(self):
        e = escort.Escort()
        for i in range(escort.MAX_ADVANCES_PER_JOB):
            s = step(fieldset_hash=f"f{i}")
            assert e.should_advance(s).advance is True, f"stopped early at {i}"
            e.note_advance(s.key)
        d = e.should_advance(step(fieldset_hash="f99"))
        assert d.advance is False
        assert d.state == escort.STATE_PAUSED_CAP

    def test_a_refused_advance_does_not_burn_the_budget(self):
        """note_advance is called only when the click actually went out."""
        e = escort.Escort()
        for _ in range(30):
            e.should_advance(step(needs_you=1))
        assert e.advances == 0

    def test_the_applicant_can_resume_after_the_cap(self):
        e = escort.Escort()
        for i in range(escort.MAX_ADVANCES_PER_JOB):
            e.note_advance(f"docA::f{i}")
        assert e.should_advance(step(fieldset_hash="new")).state == \
            escort.STATE_PAUSED_CAP
        e.resume()
        assert e.should_advance(step(fieldset_hash="new")).advance is True


class TestSubmitAttribution:
    """A wizard step POSTs its form. Without this, every escorted step looks
    like an application the applicant submitted."""

    def test_a_submit_inside_the_window_is_ours(self):
        e = escort.Escort()
        e.note_advance("docA::f1", now=100.0)
        assert e.attribute_submit(now=100.5) == "app"

    def test_a_submit_outside_the_window_is_theirs(self):
        e = escort.Escort()
        e.note_advance("docA::f1", now=100.0)
        assert e.attribute_submit(
            now=100.0 + escort.ATTRIBUTION_WINDOW_S + 1) == "user"

    def test_a_submit_with_no_advance_at_all_is_theirs(self):
        assert escort.Escort().attribute_submit(now=5.0) == "user"


class TestFieldsetHash:
    def test_the_same_fields_hash_the_same(self):
        fields = [{"je_idx": "1", "name": "first", "label_text": "First"},
                  {"je_idx": "2", "name": "last", "label_text": "Last"}]
        assert escort.fieldset_hash(fields) == escort.fieldset_hash(fields)

    def test_a_relabelled_field_is_still_the_same_step(self):
        """A site that re-words its own question — or a label that briefly
        carried the answer — must not make the step look brand new. A step
        that never settles never advances."""
        before = [{"je_idx": "1", "name": "q_auth",
                   "label_text": "Authorized to work?"}]
        after = [{"je_idx": "1", "name": "q_auth",
                  "label_text": "Authorized to work? Yes"}]
        assert escort.fieldset_hash(before) == escort.fieldset_hash(after)

    def test_invisible_scaffolding_is_not_part_of_the_step(self):
        visible_only = [{"je_idx": "1", "name": "first", "visible": True}]
        with_hidden = visible_only + [
            {"je_idx": "2", "name": "mirror", "visible": False}]
        assert escort.fieldset_hash(visible_only) ==             escort.fieldset_hash(with_hidden)

    def test_order_does_not_matter(self):
        a = [{"je_idx": "1", "name": "first"}, {"je_idx": "2", "name": "last"}]
        assert escort.fieldset_hash(a) == escort.fieldset_hash(list(reversed(a)))

    def test_different_fields_hash_differently(self):
        a = [{"je_idx": "1", "name": "first"}]
        b = [{"je_idx": "1", "name": "phone"}]
        assert escort.fieldset_hash(a) != escort.fieldset_hash(b)

    def test_an_empty_step_still_hashes(self):
        assert escort.fieldset_hash([])


class TestReadyForReview:
    def test_the_door_has_its_own_state(self):
        assert escort.Escort().note_ready() == escort.STATE_READY
