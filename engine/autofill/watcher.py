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
  function jeIsRichText(el) {
    var editable = el.getAttribute && el.getAttribute('contenteditable');
    var r = (el.getAttribute && el.getAttribute('role') || '').toLowerCase();
    if (editable === 'false') { return false; }
    if (editable === '' || editable === 'true') { return true; }
    var t = el.tagName.toLowerCase();
    return r === 'textbox' && t !== 'input' && t !== 'textarea';
  }
  function jeRichTextWritable(el) {
    if ((el.getAttribute('aria-readonly') || '').toLowerCase() === 'true') {
      return false;
    }
    return (el.getAttribute('contenteditable') || '').toLowerCase() !== 'false';
  }
  function jeWidget(el) {
    var tag = el.tagName.toLowerCase();
    if (tag === 'select') return 'native_select';
    if (jeIsRichText(el)) return 'richtext';
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
  // 019 (T032, FR-010): mirrors field_core.is_placeholder_value and
  // content/scanner.js isPlaceholderValue. A control resting on "Select…"
  // displays text but holds no answer.
  var JE_PLACEHOLDER =
    /^\s*(?:[-–—•*\s]*)?(?:select|choose|please\s+select|pick|--+|—+|none|n\/?a)\b/i;
  function jeIsPlaceholder(text) {
    var value = (text || '').trim();
    if (!value) { return true; }
    return JE_PLACEHOLDER.test(value);
  }
  function jeValue(el, widget) {
    if (el.type === 'checkbox' || el.type === 'radio') {
      return el.checked ? 'on' : '';
    }
    if (widget === 'richtext') {
      var ph = el.querySelector && el.querySelector('[data-placeholder]');
      var text = (el.innerText || el.textContent || '').trim();
      if (ph) {
        var phText = (ph.innerText || ph.textContent || '').trim();
        if (phText && text.indexOf(phText) === 0) {
          text = text.slice(phText.length).trim();
        }
      }
      return jeIsPlaceholder(text) ? '' : text;
    }
    if (widget === 'native_select') {
      if (!el.value) { return ''; }
      var selected = (el.options[el.selectedIndex] || {}).text || '';
      return jeIsPlaceholder(selected) ? '' : selected;
    }
    if (widget === 'custom_combobox' || widget === 'typeahead') {
      var sv = el.querySelector &&
        el.querySelector('[class*=singleValue],[class*="-value"]');
      if (sv) {
        var svText = sv.textContent.trim();
        return jeIsPlaceholder(svText) ? '' : svText;
      }
      if (el.value) { return jeIsPlaceholder(el.value) ? '' : el.value; }
      var t = (el.textContent || '').trim();
      return jeIsPlaceholder(t) ? '' : t;
    }
    return el.value || '';
  }
  // 016 (T011, R6): group question helper + radio-set merging, kept
  // logically parallel with content/scanner.js groupQuestion/groupControls.
  function groupQuestion(el) {
    var fieldset = el.closest('fieldset');
    if (fieldset) {
      var legend = fieldset.querySelector('legend');
      if (legend && legend.innerText.trim()) { return legend.innerText.trim(); }
    }
    var rg = el.closest('[role=radiogroup]');
    if (rg) {
      var aria = rg.getAttribute('aria-label');
      if (aria) { return aria; }
      var ids = rg.getAttribute('aria-labelledby');
      if (ids) {
        var texts = ids.split(/\s+/).map(function (id) {
          var node = document.getElementById(id);
          return node ? node.innerText.trim() : '';
        }).filter(Boolean);
        if (texts.length) { return texts.join(' '); }
      }
    }
    return '';
  }
  function jeIsChoiceWidget(el) {
    const role = (el.getAttribute('role') || '').toLowerCase();
    return role === 'combobox' || role === 'listbox' ||
      el.getAttribute('aria-haspopup') === 'listbox' ||
      /select__control/.test(el.className || '');
  }
  function jeChoiceAncestor(el) {
    let node = el.parentElement;
    while (node) {
      if (jeIsChoiceWidget(node)) { return node; }
      node = node.parentElement;
    }
    return null;
  }
  // 019 (T026, FR-007): the full labelling ladder, byte-parallel with
  // content/scanner.js labelText. Reading only labels[0]/aria-label left
  // every aria-labelledby-labelled field (the Workday/React standard) with
  // no question at all.
  function jeReferencedText(el) {
    const ids = el.getAttribute && el.getAttribute('aria-labelledby');
    if (!ids) { return ''; }
    const parts = ids.split(/\s+/).map(function (id) {
      const node = document.getElementById(id);
      return node ? (node.innerText || node.textContent || '').trim() : '';
    }).filter(Boolean);
    return parts.join(' ');
  }
  function jeNearbyLabel(el) {
    const wrapping = el.closest && el.closest('label');
    if (wrapping) {
      const text = jeStripControls(wrapping);
      if (text) { return text; }
    }
    let prev = el.previousElementSibling;
    let hops = 0;
    while (prev && hops < 3) {
      const tag = prev.tagName.toLowerCase();
      if (tag === 'label' || /^h[1-6]$/.test(tag) || tag === 'legend') {
        const text = (prev.innerText || prev.textContent || '').trim();
        if (text) { return text; }
      }
      prev = prev.previousElementSibling;
      hops += 1;
    }
    return '';
  }
  function jeStripControls(node) {
    const clone = node.cloneNode(true);
    // 020: rich-text editors belong here too — a wrapping label's innerText
    // includes the control's OWN rendered text, so a cover-letter editor
    // made the question read "Why do you want to work here? Tell us why..."
    // and no stored answer could match. The 019 <select> bug, new element.
    Array.prototype.forEach.call(
      clone.querySelectorAll(
        'input,select,textarea,button,' +
        '[contenteditable=""],[contenteditable="true"],[role=textbox]'),
      function (child) { child.remove(); });
    return (clone.innerText || clone.textContent || '').trim();
  }
  function jeLabelText(el) {
    if (el.labels && el.labels[0]) {
      // A wrapping label's innerText includes the control's own text — for
      // a <select> that is the selected option, so the question changed
      // whenever the answer did.
      const label = el.labels[0];
      const text = label.contains(el) ? jeStripControls(label)
                                      : (label.innerText || '').trim();
      if (text) { return text; }
    }
    const aria = el.getAttribute('aria-label');
    if (aria) { return aria; }
    const referenced = jeReferencedText(el);
    if (referenced) { return referenced; }
    return jeNearbyLabel(el);
  }
  // 019 (T034, FR-011): offsetParent is null for an element that is ITSELF
  // position:fixed (modal fields vanished), while visibility:hidden ones
  // have a non-null offsetParent and counted as visible.
  function jeVisible(el) {
    if ((el.type || '') === 'file') { return true; }
    const rect = el.getClientRects && el.getClientRects()[0];
    if (!rect || rect.width <= 0 || rect.height <= 0) { return false; }
    // left:-9999px and friends: a real box, parked off the document.
    if (rect.right <= 0 || rect.bottom <= 0) { return false; }
    const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    if (style && (style.visibility === 'hidden' ||
                  style.visibility === 'collapse' ||
                  style.display === 'none')) { return false; }
    return true;
  }
  const els = Array.from(document.querySelectorAll(selector)).filter(el => {
    return !jeIsRichText(el) || jeRichTextWritable(el);
  });
  const pairs = Array.from(els).map(el => {
    if (!el.dataset.jeIdx) { el.dataset.jeIdx = String(window.__jeNext++); }
    const widget = jeWidget(el);
    return { el: el, desc: {
      doc: window.__jeDoc,
      je_idx: el.dataset.jeIdx,
      tag: el.tagName.toLowerCase(),
      type: widget === 'richtext' ? 'richtext' : (el.type || ''),
      name: el.name || '',
      id: el.id || '',
      label_text: jeLabelText(el),
      placeholder: el.placeholder || '',
      aria_label: el.getAttribute('aria-label') || '',
      autocomplete: el.autocomplete || '',
      value: jeValue(el, widget),
      options: el.tagName === 'SELECT'
        ? Array.from(el.options).map(o => o.text)
        : null,
      members: [],
      widget: widget,
      automation_id: el.getAttribute('data-automation-id') || '',
      maxlength: el.maxLength && el.maxLength > 0 ? el.maxLength : null,
      required: !!(el.required ||
                   el.getAttribute('aria-required') === 'true'),
      focused: el === document.activeElement,
      visible: jeVisible(el),
    } };
  });
  const radios = new Map();
  const checks = new Map();
  pairs.forEach(function (pair, i) {
    var type = pair.el.type || '';
    if (type === 'radio' && pair.el.name) {
      if (!radios.has(pair.el.name)) { radios.set(pair.el.name, []); }
      radios.get(pair.el.name).push(i);
    } else if (type === 'checkbox' && pair.el.name) {
      if (!checks.has(pair.el.name)) { checks.set(pair.el.name, []); }
      checks.get(pair.el.name).push(i);
    }
  });
  const drop = new Set();
  for (const idxs of radios.values()) {
    if (idxs.length < 2) { continue; }
    const members = idxs.map(function (i) {
      return { je_idx: pairs[i].desc.je_idx,
               label: pairs[i].desc.label_text || pairs[i].el.value || '' };
    });
    const first = pairs[idxs[0]];
    const checkedIdx = idxs.find(function (i) { return pairs[i].el.checked; });
    first.desc = Object.assign({}, first.desc, {
      type: 'radio_group',
      label_text: groupQuestion(first.el),
      options: members.map(function (m) { return m.label; }),
      members: members,
      value: checkedIdx === undefined ? ''
        : (pairs[checkedIdx].desc.label_text || pairs[checkedIdx].el.value || ''),
      focused: idxs.some(function (i) { return pairs[i].desc.focused; }),
      visible: idxs.some(function (i) { return pairs[i].desc.visible; }),
      required: idxs.some(function (i) { return pairs[i].desc.required; }),
    });
    idxs.slice(1).forEach(function (i) { drop.add(i); });
  }
  // 017 (C8): merge a checkbox set sharing one group question into ONE
  // logical field — mirrors content/scanner.js groupControls.
  for (const idxs of checks.values()) {
    if (idxs.length < 2) { continue; }
    const question = groupQuestion(pairs[idxs[0]].el);
    if (!question) { continue; }
    const members = idxs.map(function (i) {
      return { je_idx: pairs[i].desc.je_idx,
               label: pairs[i].desc.label_text || pairs[i].el.value || '' };
    });
    const first = pairs[idxs[0]];
    const checkedLabels = idxs
      .filter(function (i) { return pairs[i].el.checked; })
      .map(function (i) {
        return pairs[i].desc.label_text || pairs[i].el.value || '';
      });
    first.desc = Object.assign({}, first.desc, {
      type: 'checkbox_group',
      label_text: question,
      options: members.map(function (m) { return m.label; }),
      members: members,
      value: checkedLabels.join(', '),
      focused: idxs.some(function (i) { return pairs[i].desc.focused; }),
      visible: idxs.some(function (i) { return pairs[i].desc.visible; }),
      required: idxs.some(function (i) { return pairs[i].desc.required; }),
    });
    idxs.slice(1).forEach(function (i) { drop.add(i); });
  }
  // 017 (C6): a nested search input inside a captured choice widget is part
  // of that widget, not a second question — mirrors scanner.js
  // dropNestedChoiceControls.
  const kept = pairs.filter(function (_pair, i) { return !drop.has(i); });
  const capturedEls = new Set(kept.map(function (p) { return p.el; }));
  return kept
    .filter(function (pair) {
      const ancestor = jeChoiceAncestor(pair.el);
      if (!ancestor) { return true; }
      if (capturedEls.has(ancestor)) { return false; }
      pair.desc.nested_in_choice = true;
      if (!pair.desc.widget) { pair.desc.widget = 'custom_combobox'; }
      return true;
    })
    .map(function (pair) { return pair.desc; });
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
        # 017 (FR-017): resolve first-vs-full name across the whole document
        # before deciding any single field.
        name_overrides = field_core.name_layout(descriptors, ats)
        for descriptor in descriptors:
            override = name_overrides.get(descriptor.get("je_idx"))
            if override:
                descriptor["tag_override"] = override
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
        handled[key] = field_core.settle_entry(decision.outcome)
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
                handled[key] = field_core.settle_entry("needs_manual")
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
                handled[key] = field_core.settle_entry("needs_manual")
                return
            except Exception as exc:
                if _is_closed_error(exc):
                    raise
                try:
                    locator.press("Escape")
                except Exception:
                    pass
                record(descriptor, decision.tag, "", "needs_manual")
                handled[key] = field_core.settle_entry("needs_manual")
                return
            record(descriptor, decision.tag, decision.preview, "filled")
            handled[key] = "filled"
            result.filled_now += 1
            return

        # 016 (T013): grouped radios — check the MATCHED member's own
        # element (the group's je_idx is only its first member).
        # 017 (C8): a merged checkbox group ticks a MEMBER, exactly like a
        # radio group — same member lookup, same honest outcome.
        if decision.kind == "radio" or (
                decision.kind == "checkbox"
                and (descriptor.get("type") or "") == "checkbox_group"):
            member = next((m for m in descriptor.get("members") or []
                           if m.get("label") == decision.option_label), None)
            if member is None:
                record(descriptor, decision.tag, "", "needs_manual")
                handled[key] = field_core.settle_entry("needs_manual")
                return
            frame.locator(f'[data-je-idx="{member["je_idx"]}"]').check()
            record(descriptor, decision.tag, decision.preview, "filled",
                   decision.ai_draft)
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
