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
    // greenhouse
    { ats: "greenhouse",
      selector: "#apply_button, a[href='#application'], a[href*='#app']" },
    // lever
    { ats: "lever",
      selector: "a.postings-btn[href*='/apply'], a[href$='/apply']" },
    // ashby
    { ats: "ashby",
      selector: "a[href*='/application'], button[data-testid*='apply']" },
  ];

  let attemptedFor = null; // one-shot per (document, href) — SPA navs re-arm

  function hasFillableForm() {
    const els = document.querySelectorAll(
      "input:not([type=hidden]):not([type=submit]):not([type=button]), " +
      "select, textarea");
    return Array.from(els).some((el) => el.offsetParent !== null);
  }

  function findOpener() {
    for (const entry of OPENERS) {
      const el = document.querySelector(entry.selector);
      if (el && el.offsetParent !== null) { return el; }
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
    const key = location.href;
    if (attemptedFor === key) { return false; }
    if (hasFillableForm()) { return false; }
    const el = findOpener();
    if (!el || !structurallySafe(el)) { return false; }
    attemptedFor = key;
    el.click();
    if (onOpened) { try { onOpened(); } catch (_e) { /* overlay optional */ } }
    return true;
  }

  return { maybeOpen };
})();
