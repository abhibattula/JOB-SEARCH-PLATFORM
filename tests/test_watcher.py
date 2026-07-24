"""009 T008: one watch tick (FR-003..FR-006) — driven entirely by fakes.

The invariants under test are the ones whose absence shipped a non-working
fill engine twice: fields are addressed ONLY by scan-time stamps, filling
is idempotent across ticks, a focused field is never touched, every write
re-checks the field first, late-appearing and multi-frame fields fill,
re-renders don't duplicate report rows, and nothing is EVER clicked.
"""
import pytest

from engine.autofill import watcher


# --- fakes -------------------------------------------------------------------

class FakeLocator:
    def __init__(self, frame, descriptor):
        self.frame = frame
        self.d = descriptor

    def evaluate(self, js, *args):
        return {"value": self.d.get("value") or "", "focused": bool(self.d.get("focused"))}

    def fill(self, value):
        self.d["value"] = str(value)
        self.frame.actions.append(("fill", self.d["je_idx"], value))

    def select_option(self, value=None, label=None):
        self.d["value"] = label if label is not None else value
        self.frame.actions.append(("select", self.d["je_idx"], self.d["value"]))

    def check(self):
        self.d["value"] = "on"
        self.frame.actions.append(("check", self.d["je_idx"]))

    def set_input_files(self, path):
        self.d["value"] = str(path)
        self.frame.actions.append(("attach", self.d["je_idx"], str(path)))

    def click(self):  # pragma: no cover - must never be reached
        raise AssertionError("the fill engine must never click anything")


class FakeFrame:
    def __init__(self, url="https://boards.greenhouse.io/acme/jobs/1",
                 descriptors=None, fail_serialize=False, doc="doc1"):
        self.url = url
        self.doc = doc
        self.descriptors = descriptors if descriptors is not None else []
        self.fail_serialize = fail_serialize
        self.actions = []

    def evaluate(self, js, arg=None):
        if self.fail_serialize:
            raise RuntimeError("Execution context was destroyed")
        # simulate the stamping eval faithfully: window.__jeNext persists
        # across re-renders, so a re-mounted (fresh) node gets a NEW stamp
        for d in self.descriptors:
            d.setdefault("doc", self.doc)
            if "je_idx" not in d:
                self._next = getattr(self, "_next", 0) + 1
                d["je_idx"] = str(self._next)
        return [dict(d) for d in self.descriptors]

    def locator(self, css):
        assert css.startswith('[data-je-idx="'), (
            f"elements must be addressed by stamp, never raw selectors: {css}"
        )
        idx = css.split('"')[1]
        for d in self.descriptors:
            if d.get("je_idx") == idx:
                return FakeLocator(self, d)
        raise AssertionError(f"no element with stamp {idx}")


class FakePage:
    def __init__(self, frames):
        self.frames = frames


def descriptor(**overrides):
    d = {"tag": "input", "type": "text", "name": "", "id": "",
         "label_text": "", "placeholder": "", "aria_label": "",
         "autocomplete": "", "value": "", "options": None,
         "focused": False, "visible": True}
    d.update(overrides)
    return d


def profile_get_value(tag, d):
    values = {
        "first_name": "Abhinav", "last_name": "Battula", "full_name": "Abhinav Battula",
        "email": "abhi@example.com", "phone": "(512) 555-0100",
        "linkedin_url": "https://linkedin.com/in/abhinav",
        "resume_upload": "C:\\data\\resume\\resume.pdf",
        "work_authorization": "Yes",
        "login_password": "secret-hunter2",
    }
    return values.get(tag)


class Recorder:
    def __init__(self):
        self.rows = []

    def __call__(self, d, tag, preview, outcome, ai_draft=False):
        self.rows.append({"tag": tag, "preview": preview, "outcome": outcome,
                          "je_idx": d.get("je_idx"), "ai_draft": ai_draft})


def run_tick(page, handled=None, get_value=profile_get_value, record=None):
    handled = handled if handled is not None else {}
    record = record or Recorder()
    result = watcher.tick(
        page, get_value=get_value, record=record, handled=handled
    )
    return result, handled, record


# --- tests -------------------------------------------------------------------

class TestBasicFill:
    def test_fills_recognized_empty_fields_by_stamp(self):
        frame = FakeFrame(descriptors=[
            descriptor(name="first_name"),
            descriptor(name="email", type="email"),
        ])
        result, handled, record = run_tick(FakePage([frame]))
        assert ("fill", "1", "Abhinav") in frame.actions
        assert ("fill", "2", "abhi@example.com") in frame.actions
        assert result.fields_seen == 2 and result.filled_now == 2
        assert {r["outcome"] for r in record.rows} == {"filled"}

    def test_idempotent_across_ticks(self):
        frame = FakeFrame(descriptors=[descriptor(name="first_name")])
        page = FakePage([frame])
        _, handled, record = run_tick(page)
        result2, _, _ = run_tick(page, handled=handled, record=record)
        assert result2.filled_now == 0
        fills = [a for a in frame.actions if a[0] == "fill"]
        assert len(fills) == 1  # never re-filled
        assert len([r for r in record.rows if r["outcome"] == "filled"]) == 1

    def test_existing_value_is_sacred(self):
        frame = FakeFrame(descriptors=[
            descriptor(name="first_name", value="Typed Byhand"),
        ])
        _, handled, record = run_tick(FakePage([frame]))
        assert frame.actions == []
        assert record.rows[0]["outcome"] == "skipped_existing"
        # and the skip is recorded exactly once across ticks
        _, _, _ = run_tick(FakePage([frame]), handled=handled, record=record)
        assert len(record.rows) == 1

    def test_focused_field_never_touched(self):
        frame = FakeFrame(descriptors=[
            descriptor(name="first_name", focused=True),
            descriptor(name="email", type="email"),
        ])
        result, _, _ = run_tick(FakePage([frame]))
        assert ("fill", "2", "abhi@example.com") in frame.actions
        assert not any(a[1] == "1" for a in frame.actions)

    def test_prewrite_recheck_blocks_race(self):
        # descriptor said empty at scan time, but by write time the user
        # started typing (locator.evaluate reflects live state)
        frame = FakeFrame(descriptors=[descriptor(name="first_name")])

        original_locator = frame.locator

        def racing_locator(css):
            loc = original_locator(css)
            loc.d["value"] = "Us"  # user typed between scan and write
            return loc

        frame.locator = racing_locator
        result, _, record = run_tick(FakePage([frame]))
        assert not any(a[0] == "fill" for a in frame.actions)
        assert result.filled_now == 0

    def test_invisible_fields_skipped_but_file_inputs_allowed(self):
        frame = FakeFrame(descriptors=[
            descriptor(name="first_name", visible=False),
            descriptor(name="resume", type="file", visible=False),
        ])
        _, _, _ = run_tick(FakePage([frame]))
        kinds = {a[0] for a in frame.actions}
        assert kinds == {"attach"}


class TestLateAndMultiFrame:
    def test_delayed_fields_fill_on_a_later_tick(self):
        frame = FakeFrame(descriptors=[])
        page = FakePage([frame])
        result1, handled, record = run_tick(page)
        assert result1.fields_seen == 0
        frame.descriptors.append(descriptor(name="email", type="email"))
        result2, _, _ = run_tick(page, handled=handled, record=record)
        assert result2.filled_now == 1
        assert ("fill", "1", "abhi@example.com") in frame.actions

    def test_fields_in_multiple_frames_all_fill(self):
        top = FakeFrame(doc="d-top", descriptors=[descriptor(name="first_name")])
        embed = FakeFrame(
            url="https://boards.greenhouse.io/embed/acme", doc="d-embed",
            descriptors=[descriptor(name="email", type="email")],
        )
        result, _, _ = run_tick(FakePage([top, embed]))
        assert result.filled_now == 2
        assert ("fill", "1", "Abhinav") in top.actions
        assert ("fill", "1", "abhi@example.com") in embed.actions

    def test_frame_count_bounded(self):
        frames = [FakeFrame(doc=f"d{i}", descriptors=[descriptor(name="email", type="email")])
                  for i in range(watcher.MAX_FRAMES + 5)]
        result, _, _ = run_tick(FakePage(frames))
        touched = sum(1 for f in frames if f.actions)
        assert touched == watcher.MAX_FRAMES

    def test_blank_frames_skipped(self):
        blank = FakeFrame(url="about:blank", descriptors=[descriptor(name="email")])
        real = FakeFrame(descriptors=[descriptor(name="email", type="email")])
        result, _, _ = run_tick(FakePage([blank, real]))
        assert blank.actions == []
        assert real.actions != []

    def test_rerender_refills_without_duplicate_report_rows(self):
        frame = FakeFrame(descriptors=[descriptor(name="email", type="email")])
        page = FakePage([frame])
        _, handled, record = run_tick(page)
        # framework re-mount: same document, NEW node (new stamp), empty again
        frame.descriptors[:] = [descriptor(name="email", type="email")]
        run_tick(page, handled=handled, record=record)
        fills = [a for a in frame.actions if a[0] == "fill"]
        assert len(fills) == 2  # refilled the fresh empty node
        filled_rows = [r for r in record.rows if r["outcome"] == "filled"]
        assert len(filled_rows) == 2  # one row per distinct element, no spam


class TestStructuredAndSpecialFields:
    def test_select_filled_via_option_match(self):
        frame = FakeFrame(descriptors=[descriptor(
            tag="select", type="select-one", name="work_authorization",
            label_text="Are you authorized to work in the US?",
            options=["--", "Yes, I am authorized", "No"],
        )])
        _, _, record = run_tick(FakePage([frame]))
        assert ("select", "1", "Yes, I am authorized") in frame.actions
        assert record.rows[0]["outcome"] == "filled"

    def test_select_without_confident_match_left_untouched(self):
        frame = FakeFrame(descriptors=[descriptor(
            tag="select", type="select-one", name="work_authorization",
            label_text="Are you authorized to work in the US?",
            options=["Maybe", "Unsure"],
        )])
        _, handled, record = run_tick(FakePage([frame]))
        assert frame.actions == []
        assert record.rows[0]["outcome"] == "no_match"
        # no_match is recorded once, not per tick
        run_tick(FakePage([frame]), handled=handled, record=record)
        assert len(record.rows) == 1

    def test_resume_attached_and_password_masked(self):
        frame = FakeFrame(descriptors=[
            descriptor(name="resume", type="file"),
            descriptor(name="password", type="password", form_context="login"),
        ])
        _, _, record = run_tick(FakePage([frame]))
        attach = next(r for r in record.rows if r["tag"] == "resume_upload")
        assert attach["outcome"] == "filled"
        pw = next(r for r in record.rows if r["tag"] == "login_password")
        assert pw["preview"] == "•••"
        assert "hunter2" not in str(record.rows)

    def test_attach_failure_reported_needs_manual(self):
        frame = FakeFrame(descriptors=[descriptor(name="resume", type="file")])

        original_locator = frame.locator

        def failing_locator(css):
            loc = original_locator(css)
            def boom(path):
                raise RuntimeError("custom widget rejected programmatic file")
            loc.set_input_files = boom
            return loc

        frame.locator = failing_locator
        _, handled, record = run_tick(FakePage([frame]))
        assert record.rows[0]["outcome"] == "needs_manual"
        run_tick(FakePage([frame]), handled=handled, record=record)
        assert len(record.rows) == 1  # reported once

    def test_unanswerable_fields_skipped_silently(self):
        frame = FakeFrame(descriptors=[descriptor(
            name="custom_question_77", label_text="Describe your ideal team",
        )])
        result, _, record = run_tick(
            FakePage([frame]), get_value=lambda tag, d: None
        )
        assert frame.actions == []
        assert result.filled_now == 0


class TestScanFailureTolerance:
    def test_all_frames_failing_sets_scan_error(self):
        frame = FakeFrame(fail_serialize=True)
        result, _, _ = run_tick(FakePage([frame]))
        assert result.scan_error is not None

    def test_partial_frame_failure_is_tolerated(self):
        bad = FakeFrame(fail_serialize=True, doc="bad")
        good = FakeFrame(descriptors=[descriptor(name="email", type="email")])
        result, _, _ = run_tick(FakePage([bad, good]))
        assert result.scan_error is None
        assert result.filled_now == 1

    def test_closed_page_error_propagates(self):
        class ClosedPage:
            @property
            def frames(self):
                raise RuntimeError("Target page, context or browser has been closed")

        with pytest.raises(RuntimeError, match="has been closed"):
            watcher.tick(ClosedPage(), get_value=profile_get_value,
                         record=Recorder(), handled={})


class TestGuardedClick011:
    """011: the Playwright fill path's click guard refuses submit-class
    controls (parity with the extension's safeClick)."""

    class _SigLocator:
        def __init__(self, sig):
            self._sig = sig
            self.clicked = False

        def evaluate(self, js):
            return self._sig

        def click(self):
            self.clicked = True

    def test_denylisted_control_is_never_clicked(self):
        loc = self._SigLocator({"text": "Submit application", "type": "submit",
                                "role": "button"})
        with pytest.raises(watcher._DenylistedClick):
            watcher._guarded_click(loc)
        assert loc.clicked is False

    def test_option_control_is_clicked(self):
        loc = self._SigLocator({"text": "Yes", "type": "", "role": "option"})
        watcher._guarded_click(loc)
        assert loc.clicked is True

    def test_wrapper_containing_submit_refused(self):
        # a div whose evaluate() reports a folded 'submit' type (a descendant
        # submit button) is refused
        loc = self._SigLocator({"text": "Apply now", "type": "submit",
                                "role": ""})
        with pytest.raises(watcher._DenylistedClick):
            watcher._guarded_click(loc)
        assert loc.clicked is False
