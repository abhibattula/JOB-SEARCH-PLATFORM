// The submit denylist, mirrored from engine/autofill/click_guard.py.
// tests/test_extension_assets.py asserts DENY_TERMS here is term-for-term
// identical to DENY_TERMS there, so the two can never drift.
//
// The companion may click a field's own widget to set a value, but NEVER a
// control that submits/applies/advances/logs in. Every click in filler.js
// goes through jeClickGuard.isDenylisted first.
//
// Scope: judge the clicked element's OWN text/type/role + its DESCENDANTS,
// never its ancestors (so an option inside a form with a Submit is allowed,
// but a real submit button — or a wrapper containing one — is refused).
//
// Classic script: exposes window.jeClickGuard.
"use strict";

window.jeClickGuard = (function () {
  // Keep this list identical to click_guard.py DENY_TERMS (order-free).
  const DENY_TERMS = [
    "submit", "apply", "next", "continue", "save", "finish",
    "review and submit", "log in", "login", "sign in", "sign up",
    "register", "create account", "pay", "checkout", "proceed",
  ];

  function normalize(text) {
    return (text || "").trim().toLowerCase().replace(/\s+/g, " ");
  }

  // 019: the FINAL-class layer, mirrored from click_guard.py FINAL_TERMS
  // (parity-tested). A wizard's Continue is clickable under constitution
  // v1.2.0; the Submit at the end of it never is.
  const FINAL_TERMS = [
    "submit application", "submit my application", "review and submit",
    "submit", "create account", "create an account", "register",
    "sign up", "signup", "pay", "checkout", "place order",
    "confirm and submit",
  ];

  function isProgressionSafe(name) {
    const norm = normalize(name);
    if (!norm) { return false; }  // unnamed is not identifiably safe
    for (const term of FINAL_TERMS) {
      const re = new RegExp("(?<![a-z])"
        + term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?![a-z])");
      if (re.test(norm)) { return false; }
    }
    return true;
  }

  function isDenylistedSignal(text, type, role) {
    if ((type || "").trim().toLowerCase() === "submit") { return true; }
    const norm = normalize(text);
    if (!norm) { return false; }
    for (const term of DENY_TERMS) {
      const re = new RegExp("(?<![a-z])" + term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?![a-z])");
      if (re.test(norm)) { return true; }
    }
    return false;
  }

  // 019 (T036, FR-012): may the filler OPERATE this control to set a value?
  // Mirrors engine/autofill/click_guard.is_widget_operable. Text is judged
  // on the element's own accessible name — folding descendant text (the 011
  // rule, right for buttons) refused an ordinary dropdown whose surrounding
  // card contained the word "Next" or "Save". Descendant TYPES are still
  // folded: a wrapper containing a real submit control would submit the
  // form, and that is the danger the fold existed for.
  function ownName(el) {
    const aria = el.getAttribute && el.getAttribute("aria-label");
    if (aria) { return aria; }
    const labelled = el.getAttribute && el.getAttribute("aria-labelledby");
    if (labelled && window.jeScanner) {
      // reuse the scanner's resolver so both agree on what the name IS
      const root = el.getRootNode ? el.getRootNode() : document;
      const parts = labelled.split(/\s+/).map(function (id) {
        const node = (root.getElementById && root.getElementById(id))
          || document.getElementById(id);
        return node ? (node.innerText || node.textContent || "").trim() : "";
      }).filter(Boolean);
      if (parts.length) { return parts.join(" "); }
    }
    if (el.value) { return String(el.value); }
    // Own text only: direct text nodes, not descendants' text.
    let own = "";
    Array.prototype.forEach.call(el.childNodes || [], function (node) {
      if (node.nodeType === 3) { own += node.nodeValue; }
    });
    own = own.trim();
    if (own) { return own; }
    // A leaf element (an option row) has no element children — its
    // textContent IS its own name.
    return el.children && el.children.length === 0
      ? (el.textContent || "").trim() : "";
  }

  function isWidgetOperable(el) {
    if (!el) { return false; }
    const ownType = (el.getAttribute && el.getAttribute("type")) || el.type || "";
    if ((ownType || "").trim().toLowerCase() === "submit") { return false; }
    if (el.querySelector &&
        el.querySelector('button[type=submit], input[type=submit], [type=submit]')) {
      return false;
    }
    const role = ((el.getAttribute && el.getAttribute("role")) || "")
      .trim().toLowerCase();
    // An element the page declares an OPTION is a value, not a control:
    // "Next year" in a date menu is an answer. A submit dressed as an option
    // was already refused above, by type.
    if (role === "option") { return true; }
    return !isDenylistedSignal(ownName(el), ownType, role);
  }

  // Public: judge a DOM element (self + descendants).
  function isDenylisted(el) {
    if (!el) { return false; }
    const ownType = (el.getAttribute && el.getAttribute("type")) || el.type || "";
    const ownRole = (el.getAttribute && el.getAttribute("role")) || "";
    // own text + descendant text (textContent already includes descendants);
    // a descendant <button type=submit> makes the folded type "submit".
    let foldedType = ownType;
    if (el.querySelector) {
      const sub = el.querySelector('button[type=submit], input[type=submit], [type=submit]');
      if (sub) { foldedType = "submit"; }
    }
    const text = (el.textContent || el.value || el.getAttribute && el.getAttribute("aria-label") || "");
    return isDenylistedSignal(text, foldedType, ownRole);
  }

  return { DENY_TERMS, FINAL_TERMS, isDenylisted, isDenylistedSignal,
           isWidgetOperable, isProgressionSafe };
})();
