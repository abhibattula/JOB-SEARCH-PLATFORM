"""One watch tick of the live fill engine (feature 009, FR-003..FR-006).

Called only from the worker thread. Walks every frame of the open page,
serializes AND stamps all form fields in a single JS evaluation, then
idempotently fills empty, unfocused, recognized fields. Runs every ~2s
while a job is current — late renders, user-revealed forms, next pages,
and iframes all fill through this one mechanism (no navigation events).

Safety invariants (regression-tested in tests/test_watcher.py):
- elements are addressed ONLY via scan-time stamps `[data-je-idx]` inside
  their own frame — never by raw name/id selectors (root cause A8);
- a non-empty field is sacred; a focused field is never touched; every
  write re-checks value+focus immediately before writing;
- NOTHING is ever clicked (the field query excludes clickables and the
  fill path has no click call — FakeLocator.click raises in tests);
- passwords are masked at record time; report rows never repeat for the
  same element.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from . import adapters
from . import field_core
from . import fields as fields_mod

log = logging.getLogger(__name__)

MAX_FRAMES = 15

# Re-exported for existing tests/consumers; the vocabulary now lives in
# field_core, shared with the extension backend (010).
_TERMINAL_OUTCOMES = field_core.TERMINAL_OUTCOMES

# Serializes AND stamps in one pass. __jeDoc is a per-document token: it
# survives SPA re-renders (same window) but resets on real navigation, so
# (doc, je_idx) uniquely names an element for idempotency bookkeeping.
SERIALIZE_JS = """
(selector) => {
  window.__jeDoc = window.__jeDoc || Math.random().toString(36).slice(2);
  window.__jeNext = window.__jeNext || 1;
  const els = document.querySelectorAll(selector);
  return Array.from(els).map(el => {
    if (!el.dataset.jeIdx) { el.dataset.jeIdx = String(window.__jeNext++); }
    return {
      doc: window.__jeDoc,
      je_idx: el.dataset.jeIdx,
      tag: el.tagName.toLowerCase(),
      type: el.type || '',
      name: el.name || '',
      id: el.id || '',
      label_text: (el.labels && el.labels[0] ? el.labels[0].innerText : '')
        || el.getAttribute('aria-label') || '',
      placeholder: el.placeholder || '',
      aria_label: el.getAttribute('aria-label') || '',
      autocomplete: el.autocomplete || '',
      value: (el.type === 'checkbox' || el.type === 'radio')
        ? (el.checked ? 'on' : '')
        : (el.value || ''),
      options: el.tagName === 'SELECT'
        ? Array.from(el.options).map(o => o.text)
        : null,
      focused: el === document.activeElement,
      visible: !!(el.offsetParent || el.type === 'file'),
    };
  });
}
"""

RECHECK_JS = """
el => ({
  value: (el.type === 'checkbox' || el.type === 'radio')
    ? (el.checked ? 'on' : '')
    : (el.value || ''),
  focused: el === document.activeElement,
})
"""


@dataclass
class TickResult:
    fields_seen: int = 0
    filled_now: int = 0
    scan_error: str | None = None


def _is_closed_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "targetclosed" in text or "has been closed" in text


def _key(descriptor: dict) -> tuple:
    return (descriptor.get("doc"), descriptor.get("je_idx"))


def tick(page, *, get_value, record, handled: dict) -> TickResult:
    """One fill pass over every frame of `page`.

    get_value(tag, descriptor) -> value|None  (browser_controller wraps
        profile/credentials/answer-bank/pending logic there)
    record(descriptor, tag, preview, outcome) -> None
    handled: (doc, je_idx) -> outcome — the per-job idempotency ledger,
        owned by the caller and carried across ticks.
    """
    result = TickResult()
    frames = [f for f in page.frames if f.url and f.url != "about:blank"]
    frames = frames[:MAX_FRAMES]
    serialize_errors: list[str] = []
    any_frame_ok = False

    for frame in frames:
        try:
            descriptors = frame.evaluate(SERIALIZE_JS, fields_mod.FIELD_QUERY_SELECTOR)
        except Exception as exc:
            if _is_closed_error(exc):
                raise
            serialize_errors.append(f"{type(exc).__name__}: {exc}")
            continue
        any_frame_ok = True
        ats = adapters.ats_from_url(frame.url)
        for descriptor in descriptors:
            _process_field(frame, ats, descriptor, get_value, record, handled, result)

    if frames and not any_frame_ok:
        result.scan_error = (serialize_errors or ["no frame could be read"])[-1][:300]
    return result


def _process_field(frame, ats, descriptor, get_value, record, handled, result) -> None:
    """Apply one field_core decision via Playwright locators. The decision
    rules live in field_core (shared with the extension backend); this
    function only executes them and records outcomes."""
    decision = field_core.decide(ats, descriptor, handled, get_value)
    if decision.action == "ignore":
        return
    result.fields_seen += 1
    key = _key(descriptor)
    if decision.action == "skip":
        return
    if decision.action == "settle":
        record(descriptor, decision.tag, "", decision.outcome)
        handled[key] = decision.outcome
        return

    try:
        locator = frame.locator(f'[data-je-idx="{descriptor["je_idx"]}"]')

        if decision.kind == "file":
            try:
                locator.set_input_files(decision.value)
            except Exception as exc:
                if _is_closed_error(exc):
                    raise
                # custom widgets rejecting programmatic attachment are
                # reported, never fatal (007 edge case, preserved)
                record(descriptor, decision.tag, "", "needs_manual")
                handled[key] = "needs_manual"
                return
            record(descriptor, decision.tag, decision.preview, "filled")
            handled[key] = "filled"
            result.filled_now += 1
            return

        # just-before-write re-check: the scan is up to a tick old
        state = locator.evaluate(RECHECK_JS)
        if (state.get("value") or "").strip() or state.get("focused"):
            return
        if decision.kind == "select":
            locator.select_option(label=decision.option_label)
        elif decision.kind == "checkbox":
            locator.check()
        else:
            locator.fill(str(decision.value))
        record(descriptor, decision.tag, decision.preview, "filled")
        handled[key] = "filled"
        result.filled_now += 1
    except Exception as exc:
        if _is_closed_error(exc):
            raise
        log.debug("could not fill field %s", descriptor.get("je_idx"), exc_info=True)
