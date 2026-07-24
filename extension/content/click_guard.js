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

  return { DENY_TERMS, isDenylisted, isDenylistedSignal };
})();
