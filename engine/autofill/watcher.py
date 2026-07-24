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
from . import click_guard
from . import field_core
from . import fields as fields_mod

log = logging.getLogger(__name__)

MAX_FRAMES = 15

# 011: the ~1.5s per-widget budget for a custom dropdown's options or a
# typeahead's suggestions to appear (clarify Q2). Playwright wants ms.
OPTION_WAIT_MS = 1500

# Reads an element's own text/type/role + a descendant submit signal, so the
# Playwright path consults the SAME click_guard denylist the extension does.
CLICK_SIGNAL_JS = """
el => {
  let type = (el.getAttribute && el.getAttribute('type')) || el.type || '';
  if (el.querySelector && el.querySelector('[type=submit]')) { type = 'submit'; }
  return {
    text: el.textContent || el.value
      || (el.getAttribute && el.getAttribute('aria-label')) || '',
    type: type,
    role: (el.getAttribute && el.getAttribute('role')) || '',
  };
}
"""


class _DenylistedClick(Exception):
    """A locator the click_guard refused (a submit-class control)."""


def _guarded_click(locator) -> None:
    """The ONLY click the Playwright fill path makes. Refuses submit-class
    controls exactly as the extension's safeClick does."""
    sig = locator.evaluate(CLICK_SIGNAL_JS)
    if click_guard.is_denylisted(text=sig.get("text", ""),
                                 type=sig.get("type", ""),
                                 role=sig.get("role", "")):
        raise _DenylistedClick()
    locator.click()


def _fill_widget(frame, locator, decision) -> None:
    """Set a custom dropdown or typeahead: open/type → wait ≤1.5s for the
    matching option → guarded-click it → verify. Raises on miss/timeout so
    the caller reports needs_manual and closes the popup."""
    target = decision.option_label or str(decision.value)
    if decision.kind == "typeahead":
        locator.fill(str(decision.value))  # the site fetches suggestions
    else:
        _guarded_click(locator)  # open the dropdown
    option = frame.get_by_role("option", name=target, exact=False).first
    option.wait_for(timeout=OPTION_WAIT_MS)  # raises TimeoutError on no match
    _guarded_click(option)

# Re-exported for existing tests/consumers; the vocabulary now lives in
# field_core, shared with the extension backend (010).
_TERMINAL_OUTCOMES = field_core.TERMINAL_OUTCOMES

# Serializes AND stamps in one pass. __jeDoc is a per-document token: it
# survives SPA re-renders (same window) but resets on real navigation, so
# (doc, je_idx) uniquely names an element for idempotency bookkeeping.
SERIALIZE_JS = r"""
(selector) => {
  window.__jeDoc = window.__jeDoc || Math.random().toString(36).slice(2);
  window.__jeNext = window.__jeNext || 1;
  // 011: widget classification + displayed-value read, kept byte-parallel
  // with the extension's content/scanner.js jeWidget/jeValue helpers.
  function jeWidget(el) {
    var tag = el.tagName.toLowerCase();
    if (tag === 'select') return 'native_select';
    var role = (el.getAttribute('role') || '').toLowerCase();
    var ac = (el.getAttribute('aria-autocomplete') || '').toLowerCase();
    var isInput = tag === 'input' || tag === 'textarea';
    if (isInput && (ac === 'list' || ac === 'both')) return 'typeahead';
    if (role === 'combobox' || role === 'listbox' ||
        el.getAttribute('aria-haspopup') === 'listbox' ||
        /select__control/.test(el.className || '')) {
      return (isInput && ac) ? 'typeahead' : 'custom_combobox';
    }
    return '';
  }
  function jeValue(el, widget) {
    if (el.type === 'checkbox' || el.type === 'radio') {
      return el.checked ? 'on' : '';
    }
    if (widget === 'native_select') {
      return el.value ? ((el.options[el.selectedIndex] || {}).text || '') : '';
    }
    if (widget === 'custom_combobox' || widget === 'typeahead') {
      var sv = el.querySelector &&
        el.querySelector('[class*=singleValue],[class*="-value"]');
      if (sv) { return sv.textContent.trim(); }
      if (el.value) { return el.value; }
      var t = (el.textContent || '').trim();
      return /^(select|choose|--)/i.test(t) ? '' : t;
    }
    return el.value || '';
  }
  const els = document.querySelectorAll(selector);
  return Array.from(els).map(el => {
    if (!el.dataset.jeIdx) { el.dataset.jeIdx = String(window.__jeNext++); }
    const widget = jeWidget(el);
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
      value: jeValue(el, widget),
      options: el.tagName === 'SELECT'
        ? Array.from(el.options).map(o => o.text)
        : null,
      widget: widget,
      automation_id: el.getAttribute('data-automation-id') || '',
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

        # 011: custom dropdown / typeahead — parity with the extension.
        # Every click is guarded; a miss/timeout closes the popup and
        # reports needs_manual (never a stuck-open widget, never a wrong pick).
        if decision.kind in ("combobox", "typeahead"):
            try:
                _fill_widget(frame, locator, decision)
            except _DenylistedClick:
                record(descriptor, decision.tag, "", "needs_manual")
                handled[key] = "needs_manual"
                return
            except Exception as exc:
                if _is_closed_error(exc):
                    raise
                try:
                    locator.press("Escape")
                except Exception:
                    pass
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
        record(descriptor, decision.tag, decision.preview, "filled",
               decision.ai_draft)
        handled[key] = "filled"
        result.filled_now += 1
    except Exception as exc:
        if _is_closed_error(exc):
            raise
        log.debug("could not fill field %s", descriptor.get("je_idx"), exc_info=True)
