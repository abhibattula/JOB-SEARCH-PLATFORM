"""019 (T058): the escort — when may the app advance an application?

Pure decision logic, no I/O and no imports from `web` (constitution IV). It
answers three questions and holds the small amount of state needed to answer
them honestly:

  * is this rendered step COMPLETE enough to advance? (`should_advance`)
  * has this step already been advanced? (one shot, always)
  * was that submit event the applicant's, or ours? (`attribute_submit`)

The permission it exercises is narrow by constitution (v1.2.0): a
progression click is allowlist-first, one-shot per rendered step, capped,
ledger-recorded, and MUST pause into a "your turn" state on any needs-you
item, bot check, or ambiguity. Every one of those conditions is a branch
below, and each has a test.

What this module deliberately does NOT do: decide whether a control is safe
to click. That is `click_guard.FINAL_TERMS`, enforced twice — here at the
app, and again in the page by advancer.js.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# The hard cap on consecutive automated advances for one job. A wizard that
# keeps presenting steps is either a loop or a form the applicant should
# look at; either way, twelve is where we stop and ask.
MAX_ADVANCES_PER_JOB = 12

# How long a step must be quiet — no new fields arriving — before it counts
# as settled. A form that is still rendering is not a form that is complete.
QUIET_PERIOD_S = 2.0

# How long after issuing an advance a submit event is attributed to US
# rather than to the applicant.
ATTRIBUTION_WINDOW_S = 3.0

# Session states the panel and the app page render. `filling` and the 018
# values still mean what they meant.
STATE_ESCORTING = "escorting"
STATE_NEEDS_LOGIN = "needs_login"
STATE_CAPTCHA = "your_turn_captcha"
STATE_READY = "ready_for_review"
STATE_PAUSED_CAP = "paused_cap"


@dataclass
class StepView:
    """Everything the predicate is allowed to consider about one rendered
    step. Assembled by ext_backend from the scan it already performs."""
    doc: str = ""
    fieldset_hash: str = ""
    visible_required_pending: int = 0
    inflight: int = 0
    needs_you: int = 0
    focused: bool = False
    captcha: bool = False
    missing_login: bool = False
    quiet_for: float = 0.0
    seen: int = 0

    @property
    def key(self) -> str:
        return f"{self.doc}::{self.fieldset_hash}"


@dataclass
class Decision:
    """Why the escort did or did not act — the reason is user-facing."""
    advance: bool = False
    kind: str = ""          # "next"
    state: str = ""         # the session state to show
    reason: str = ""

    def __bool__(self) -> bool:  # `if decision:` reads naturally
        return self.advance


@dataclass
class Escort:
    """Per-session escort state. One per fill session; reset with it."""
    enabled: bool = True
    advances: int = 0
    acted: set[str] = field(default_factory=set)
    _windows: list[float] = field(default_factory=list)

    # -- the predicate ----------------------------------------------------

    def should_advance(self, step: StepView, *, now: float | None = None,
                       version_ok: bool = True,
                       clickable_host: bool = True) -> Decision:
        """The whole of the escort's judgment, in refusal order.

        Order matters: a bot check outranks completeness (a step can be
        "done" while a challenge sits unsolved beside it), and needs-you
        outranks everything else the applicant could be asked to fix.
        """
        if not self.enabled:
            return Decision(state="", reason="escort_off")
        if not version_ok:
            # FR-035: never act across a version mismatch — the page is
            # running code that does not match this app.
            return Decision(state="", reason="version_mismatch")
        if not clickable_host:
            # FR-033: LinkedIn and friends. Filling continues; clicking does
            # not happen here at all.
            return Decision(state="", reason="no_click_host")
        if step.captcha:
            return Decision(state=STATE_CAPTCHA, reason="captcha")
        if step.missing_login:
            return Decision(state=STATE_NEEDS_LOGIN, reason="no_saved_login")
        if step.needs_you > 0:
            return Decision(state=STATE_ESCORTING, reason="needs_you")
        if step.focused:
            # Typing always wins. Advancing out from under the applicant's
            # hands is the rudest thing this feature could do.
            return Decision(state=STATE_ESCORTING, reason="user_typing")
        if step.inflight > 0:
            return Decision(state=STATE_ESCORTING, reason="fill_in_flight")
        if step.visible_required_pending > 0:
            return Decision(state=STATE_ESCORTING, reason="required_pending")
        if step.seen <= 0:
            # Nothing on the page yet — there is no step to complete.
            return Decision(state=STATE_ESCORTING, reason="no_fields")
        if step.quiet_for < QUIET_PERIOD_S:
            return Decision(state=STATE_ESCORTING, reason="still_settling")
        if step.key in self.acted:
            return Decision(state=STATE_ESCORTING, reason="already_advanced")
        if self.advances >= MAX_ADVANCES_PER_JOB:
            return Decision(state=STATE_PAUSED_CAP, reason="cap_reached")
        return Decision(advance=True, kind="next", state=STATE_ESCORTING,
                        reason="step_complete")

    def note_advance(self, step_key: str, *, now: float | None = None) -> None:
        """Record that the click went out. Called only when the app actually
        issued it, so a refused/not-found advance never burns the budget."""
        self.acted.add(step_key)
        self.advances += 1
        self._windows.append(now if now is not None else time.monotonic())

    def note_ready(self) -> str:
        """The only progression control left is final-class: the door."""
        return STATE_READY

    def resume(self) -> None:
        """The applicant looked, and said carry on (clears only the cap)."""
        self.advances = 0

    # -- submission attribution -------------------------------------------

    def attribute_submit(self, *, now: float | None = None) -> str:
        """Was this submit event ours or the applicant's?

        A wizard step usually POSTs its form, so without this every escorted
        step would look like an application the applicant had submitted, and
        the did-you-apply follow-up would fill with noise.
        """
        moment = now if now is not None else time.monotonic()
        for issued in self._windows:
            if 0 <= moment - issued <= ATTRIBUTION_WINDOW_S:
                return "app"
        return "user"


def fieldset_hash(descriptors) -> str:
    """A stable fingerprint of the step's field set.

    The document token alone cannot separate two steps of an SPA wizard that
    swaps its contents without navigating — same document, different form.
    Hashing what is ON the page is what makes "one advance per rendered
    step" true in both shapes.
    """
    import hashlib

    parts = []
    for raw in descriptors or ():
        parts.append("|".join((
            str(raw.get("je_idx") or ""),
            str(raw.get("name") or ""),
            str(raw.get("label_text") or "")[:60],
        )))
    blob = "\n".join(sorted(parts))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
