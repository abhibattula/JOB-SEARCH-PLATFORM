// 016 (T015, constitution v1.1.4): the apply-opener — clicks a control
// that ONLY opens or reveals the application form (a job posting's own
// "Apply" button), so filling can begin without the user hunting for it.
//
// This is a SEPARATE, allowlisted, one-shot step. It is NOT the fill
// path: window.jeClickGuard still denies every "apply"-labeled control
// during filling, and nothing here can reach a submit — the allowlist is
// per-ATS selectors, a control of type=submit is always refused, and a
// form that already holds typed values is never touched.
//
// Classic script: exposes window.jeOpener. Selector registry mirrors
// engine/autofill/adapters.py APPLY_OPENERS (asset-parity-tested).
"use strict";

window.jeOpener = (function () {
  const OPENERS = [
    // greenhouse — 019: modern job-boards.greenhouse.io NAVIGATES to a
    // separate application page instead of revealing an embedded form.
    { ats: "greenhouse",
      selector: "#apply_button, a[href='#application'], a[href*='#app'], "
                + "a.apply-button, a[href$='/application'], "
                + "a[href*='/application?']" },
    // lever
    { ats: "lever",
      selector: "a.postings-btn[href*='/apply'], a[href$='/apply']" },
    // ashby
    { ats: "ashby",
      selector: "a[href*='/application'], button[data-testid*='apply']" },
  ];

  // 019 (T038): one-shot per RENDERED STEP, not per href. An SPA wizard
  // keeps the same address while swapping the document's contents, so an
  // href key either dead-locks the opener or lets it fire twice on the same
  // control. The document token + the control's own fingerprint is the
  // step; it is the same key shape the advancer uses.
  const attempted = new Set();

  function query(selector) {
    return (window.jeScanner && window.jeScanner.deepQueryAll)
      ? window.jeScanner.deepQueryAll(selector)
      : Array.prototype.slice.call(document.querySelectorAll(selector));
  }

  function visible(el) {
    return (window.jeScanner && window.jeScanner.isVisible)
      ? window.jeScanner.isVisible(el)
      : el.offsetParent !== null;
  }

  function stepKey(el) {
    const doc = (document.documentElement.dataset || {}).jeDoc || location.href;
    const name = (el.getAttribute("id") || "") + "|"
      + (el.getAttribute("href") || "") + "|"
      + (el.textContent || "").trim().slice(0, 40);
    return doc + "::" + name;
  }

  function hasFillableForm() {
    const els = query(
      "input:not([type=hidden]):not([type=submit]):not([type=button]), "
      + "select, textarea");
    return els.some(visible);
  }

  function findOpener() {
    for (const entry of OPENERS) {
      const el = query(entry.selector).find(visible);
      if (el) { return el; }
    }
    return null;
  }

  function structurallySafe(el) {
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (type === "submit") { return false; }
    const form = el.closest("form");
    if (form) {
      const anyFilled = Array.from(
        form.querySelectorAll("input, textarea, select"))
        .some((field) => ((field.value || "") + "").trim());
      if (anyFilled) { return false; }  // a filled form is being SUBMITTED, not opened
    }
    return true;
  }

  // Returns true when an opener was clicked (exactly once per page state).
  function maybeOpen(onOpened) {
    if (hasFillableForm()) { return false; }
    const el = findOpener();
    if (!el || !structurallySafe(el)) { return false; }
    const key = stepKey(el);
    if (attempted.has(key)) { return false; }
    attempted.add(key);
    el.click();
    // 019 (FR-031): the click joins the session's activity trail. The
    // opener owns open_apply (constitution v1.2.0 keeps form-opening a
    // separate, allowlisted step) but reports through the same channel as
    // every other progression click, so the trail is complete.
    try {
      chrome.runtime.sendMessage({ _je: true, payload: {
        type: "advance_result", frame_id: 0, kind: "open_apply",
        status: "clicked", selector_kind: "apply_opener",
        control_hash: key.slice(-40),
      } });
    } catch (_e) { /* orphaned frame — the click still happened */ }
    if (onOpened) { try { onOpened(); } catch (_e) { /* overlay optional */ } }
    return true;
  }

  return { maybeOpen };
})();
