// 019 (T050/T062, constitution v1.2.0): the progression clicker.
//
// It performs exactly two kinds of click, and only when the APP tells it to:
//   sign_in — immediately after the app filled saved credentials into THIS
//             frame. Never inferred from a button's text; the app's state is
//             the whole authority.
//   next    — advance a wizard step the app has judged complete (every
//             visible required field decided, nothing in flight, nothing
//             waiting on the applicant, and a quiet moment elapsed).
//
// It NEVER clicks a final-class control: submitting an application in any
// phrasing, creating an account, registering, paying, or anything inside a
// bot check. Those refusals are computed here AND in the app; this is the
// second of the two locks.
//
// Structure mirrors opener.js deliberately: an allowlist mirrored from
// engine/autofill/adapters.py (asset-parity-tested), one guarded click
// site, one shot per rendered step. filler.js is untouched — its
// single-raw-click pin stays exactly as it was.
//
// Classic script: exposes window.jeAdvancer.
"use strict";

window.jeAdvancer = (function () {
  // Mirrored from engine/autofill/adapters.py ADVANCE_ALLOWLIST.
  const ADVANCE = [
    { ats: "workday",
      selector: "[data-automation-id='bottom-navigation-next-button'], "
                + "[data-automation-id='next'], "
                + "[data-automation-id='wd-CommandButton_uic_okButton']" },
    { ats: "greenhouse",
      selector: "#btn-next, button[data-source='save_and_continue']" },
    { ats: "lever", selector: "button.template-btn-continue" },
    { ats: "ashby", selector: "button[data-testid*='continue']" },
    { ats: "icims", selector: "#quickApplyNextButton, .iCIMS_nextButton" },
  ];

  const SIGN_IN = "button[type=submit], input[type=submit], "
                  + "button[data-automation-id*='signIn'], "
                  + "button[data-automation-id*='signin'], "
                  + "#signin, #login, button";

  // A conservative generic fallback for wizards we have no adapter for: the
  // control's WHOLE accessible name must mean "go to the next step". A
  // button merely containing the word (e.g. "Save and continue later") is
  // not matched, and a final-class name is refused outright below.
  const GENERIC_NEXT = /^(next|continue|save and continue|save & continue|next step|continue application)$/i;
  const SIGN_IN_NAME = /^(sign in|log in|login|signin|submit|continue)$/i;

  // Automation-hostile domains: LinkedIn restricts accounts that show
  // automated behaviour, and the account at risk is the applicant's. We
  // fill there; we never click.
  const NO_CLICK_HOSTS = /(^|\.)linkedin\.com$/i;

  const done = new Set();  // step_key -> already acted on

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

  function accessibleName(el) {
    const aria = el.getAttribute("aria-label");
    if (aria) { return aria.trim(); }
    if (el.value && el.tagName === "INPUT") { return String(el.value).trim(); }
    return (el.textContent || "").trim();
  }

  function hash(text) {
    let h = 0;
    for (let i = 0; i < text.length; i += 1) {
      h = ((h << 5) - h + text.charCodeAt(i)) | 0;
    }
    return String(h);
  }

  // The one refusal that matters. Anything final-class is never clicked, no
  // matter which allowlist matched it.
  function finalClass(el) {
    return !window.jeClickGuard.isProgressionSafe(accessibleName(el));
  }

  function inCaptcha(el) {
    let node = el;
    while (node) {
      const id = (node.id || "") + " " + (node.className || "");
      if (/captcha|turnstile|challenge/i.test(String(id))) { return true; }
      node = node.parentElement;
    }
    return false;
  }

  function findNext() {
    for (const entry of ADVANCE) {
      const el = query(entry.selector).find(visible);
      if (el) { return { el: el, kind: entry.ats + "_next" }; }
    }
    const generic = query("button, input[type=submit], a[role=button]")
      .filter(visible)
      .find((el) => GENERIC_NEXT.test(accessibleName(el)));
    return generic ? { el: generic, kind: "generic_next" } : null;
  }

  function findSignIn() {
    const candidate = query(SIGN_IN).filter(visible)
      .find((el) => SIGN_IN_NAME.test(accessibleName(el)));
    return candidate ? { el: candidate, kind: "sign_in_button" } : null;
  }

  function report(kind, status, selectorKind, controlHash) {
    try {
      chrome.runtime.sendMessage({ _je: true, payload: {
        type: "advance_result", kind: kind, status: status,
        selector_kind: selectorKind || "", control_hash: controlHash || "",
      } });
    } catch (_e) { /* orphaned frame — the outcome is still what it is */ }
  }

  // The app asked for one click. Everything below is a reason to refuse it.
  function perform(message) {
    const kind = message && message.kind;
    if (kind !== "sign_in" && kind !== "next") { return false; }
    const stepKey = (message.step_key || "") + "::" + kind;
    if (done.has(stepKey)) { report(kind, "refused", "already_acted", ""); return false; }
    if (NO_CLICK_HOSTS.test(location.hostname)) {
      report(kind, "refused", "no_click_host", "");
      return false;
    }
    if (window.jeScanner && window.jeScanner.captchaPresent
        && window.jeScanner.captchaPresent()) {
      // FR-028: a bot check is always the applicant's to clear.
      report(kind, "refused", "captcha_present", "");
      return false;
    }
    const found = kind === "sign_in" ? findSignIn() : findNext();
    if (!found) { report(kind, "not_found", "", ""); return false; }
    if (finalClass(found.el) || inCaptcha(found.el)) {
      report(kind, "refused", "final_class", "");
      return false;
    }
    done.add(stepKey);
    const controlHash = hash(accessibleName(found.el) + "|" + found.kind);
    found.el.click();
    report(kind, "clicked", found.kind, controlHash);
    return true;
  }

  return { perform, findNext, findSignIn, accessibleName };
})();
