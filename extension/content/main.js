// Content-script lifecycle: watches the page when told to, sends field
// scans to the app (via the service worker), applies fill instructions,
// and reports outcomes. One instance runs per frame (all_frames:true), so
// cross-origin iframes fill their own documents.
//
// Classic script: relies on window.jeScanner / window.jeFiller / window.jeOverlay
// (injected before this file per manifest order).
"use strict";

(function () {
  let watching = false;
  let observer = null;
  let debounceTimer = null;
  let safetyTimer = null;
  // 016 (T015): the apply-opener runs ONLY for queue-driven watches — a
  // popup "Fill this page" (adhoc) or a restored watch of unknown origin
  // must never auto-click anything. Conservative default: adhoc.
  let adhoc = true;
  const isTop = window === window.top;

  function toApp(payload) {
    // Route through the SW — content scripts must not hit loopback directly.
    try {
      chrome.runtime.sendMessage({ _je: true, payload });
    } catch (_e) {
      // extension reloaded/updated: this frame is orphaned — stop cleanly
      teardown();
    }
  }

  // 016 (T010): a scanner exception is REPORTED (once per document), not
  // swallowed — a silently-quiet tab was undiagnosable (RC4).
  let scanErrorSent = false;

  function scan() {
    if (!watching) { return; }
    let descriptors;
    try {
      descriptors = window.jeScanner.serialize();
    } catch (err) {
      if (!scanErrorSent) {
        scanErrorSent = true;
        toApp({ type: "scan_error", message: String(err).slice(0, 200) });
      }
      return;
    }
    toApp({
      type: "fields",
      url: location.href,
      doc: window.jeScanner.docToken(),
      descriptors,
      // 019 (FR-028): a bot check on this page. The app pauses the escort
      // and waits for the applicant; nothing is ever clicked near it.
      captcha: !!(window.jeScanner.captchaPresent
                  && window.jeScanner.captchaPresent()),
    });
    // 016 (T015): queue-driven watch on a recognized posting with no
    // fillable form → open the application ONCE; the observer/next scan
    // picks up the revealed fields.
    if (isTop && !adhoc && window.jeOpener
        && !descriptors.some((d) => d.visible)) {
      const opened = window.jeOpener.maybeOpen(function () {
        if (window.jeOverlay && window.jeOverlay.note) {
          window.jeOverlay.note("opened the application form");
        }
      });
      if (opened) { scheduleScan(); }
    }
  }

  function scheduleScan() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(scan, 500);
  }

  function startWatch() {
    if (watching) { return; }
    watching = true;
    // 019 (FR-014): a credential form is only a WALL when it stands between
    // the applicant and an application they are already pursuing. On an
    // ordinary page that merely has a login box — a blog, a docs site — an
    // offer to sign in is noise, so the sign-in state is gated on this.
    window.jeWatching = true;
    observer = new MutationObserver(scheduleScan);
    observer.observe(document.documentElement, {
      childList: true, subtree: true, attributes: true,
      attributeFilter: ["value", "style", "class", "hidden"],
    });
    // Safety poll covers observer blind spots (value mutations that change
    // no observed attribute).
    safetyTimer = setInterval(scan, 2000);
    if (isTop && window.jeOverlay) {
      window.jeOverlay.show();
      // 016 (T016): the panel's Fill again → app clears retryable state
      // and nudges a rescan (the page itself is never touched from here)
      if (window.jeOverlay.onFillAgain) {
        window.jeOverlay.onFillAgain(function () {
          toApp({ type: "fill_again" });
        });
      }
      // 017 (D7, FR-045): the applicant answered a question we declined to
      // answer. It is stored as THEIR answer and fills on the next scan.
      if (window.jeOverlay.onAnswer) {
        window.jeOverlay.onAnswer(function (question, answer, jeIdx) {
          toApp({ type: "answer_question", je_idx: jeIdx || "",
                  question: question, answer: answer });
        });
      }
      // 017 (FR-035): put ONE answer into the ONE field the applicant chose.
      if (window.jeOverlay.onInsert) {
        window.jeOverlay.onInsert(function (jeIdx, answer) {
          window.jeFiller.apply([{ je_idx: jeIdx, kind: "text",
                                   value: answer }]);
        });
      }
      // 019 (FR-017): a login saved from the wall. It goes to the app,
      // which is the only thing that ever touches the OS keychain — the
      // secret is never stored, echoed or logged on this side.
      if (window.jePanel && window.jePanel.onCredential) {
        window.jePanel.onCredential(function (identifier, password) {
          toApp({ type: "credential_save", domain: location.hostname,
                  email: identifier, password: password });
        });
      }
      // 017 (FR-036): scroll to a field that needs them.
      if (window.jeOverlay.onJump) {
        window.jeOverlay.onJump(function (jeIdx) {
          const el = window.jeScanner.elementByIdx(jeIdx);
          if (el && el.scrollIntoView) {
            el.scrollIntoView({ behavior: "smooth", block: "center" });
          }
        });
      }
    }
    // Detect the user's own submission — never our doing (we never click).
    document.addEventListener("submit", onSubmit, true);
    scan();
  }

  function teardown() {
    watching = false;
    window.jeWatching = false;
    if (observer) { observer.disconnect(); observer = null; }
    clearInterval(safetyTimer);
    clearTimeout(debounceTimer);
    document.removeEventListener("submit", onSubmit, true);
    if (isTop && window.jeOverlay) { window.jeOverlay.hide(); }
  }

  function onSubmit() {
    toApp({ type: "page_event", kind: "submit_detected", url: location.href });
  }

  async function onFill(message) {
    const results = await window.jeFiller.apply(message.items || []);
    toApp({ type: "fill_result", items: results });
    // a fill can reveal/alter fields — re-scan immediately
    scan();
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (!message || !message.type) { return; }
    switch (message.type) {
      case "watch":
        adhoc = !!message.adhoc;
        startWatch();
        break;
      case "watch_state":
        // reply to our own ready-probe: begin watching if the SW says so.
        // adhoc rides along (absent → conservative true: no auto-open).
        if (message.watched) {
          adhoc = message.adhoc !== false;
          startWatch();
        }
        break;
      case "unwatch": teardown(); break;
      case "fill":
        // only the addressed frame applies (frame_id is the app's routing;
        // Chrome already delivered this to the right frame via sendMessage)
        onFill(message);
        break;
      // 017 (C12, FR-037): a background draft landed, or the applicant asked
      // for a re-scan. Scan NOW instead of waiting for the 2 s poll. It only
      // re-reads the page — it never resets any app-side state.
      case "rescan":
        scan();
        break;
      // 017 (FR-034): the full answer text for this job. The panel is where
      // the applicant reads, copies and corrects them.
      case "answers":
        if (isTop && window.jeOverlay && window.jeOverlay.setAnswers) {
          window.jeOverlay.setAnswers(message.items, message.truncated);
        }
        break;
      // 019 (T007, FR-001): the app and this companion disagree on their
      // version. Chrome keeps running the OLD bundle until the user presses
      // ↻, and until they do some fills are withheld — so the page itself
      // has to say it. Pinned above every other notice.
      case "version_state":
        if (isTop && message.mismatch && window.jePanel) {
          window.jePanel.notice(
            "Reload the companion at chrome://extensions (↻) — the app is "
            + "v" + (message.appVersion || "?") + " and this companion is v"
            + (message.companionVersion || "?")
            + ". Until you do, some answers can't be filled.");
          window.jePanel.show();
        }
        break;
      // 019 (FR-016): the app says the credentials it filled have landed
      // and the one permitted sign-in click may go out. The engine decided
      // this — the page never infers it from a button's text.
      case "advance_step":
        if (window.jeAdvancer) { window.jeAdvancer.perform(message); }
        break;
      // 019 (FR-017): the app saved the login; the wall gets another go.
      case "credential_saved":
        if (isTop && window.jePanel) {
          window.jePanel.setCredentialNeeded(false);
          window.jePanel.notice("Login saved. Signing you in…");
        }
        break;
      case "overlay_state":
        if (isTop && window.jeOverlay) { window.jeOverlay.update(message.summary); }
        // 019 (FR-017): the app knows whether a saved login exists for this
        // domain; the panel offers the inline save form only when it does not.
        if (isTop && window.jePanel && message.summary
            && window.jePanel.setCredentialNeeded) {
          window.jePanel.setCredentialNeeded(!!message.summary.needs_login);
        }
        // 016 (T017): highlight the fields the human must answer
        if (message.summary && message.summary.needs_you_idx
            && window.jeFiller.annotateNeedsYou) {
          window.jeFiller.annotateNeedsYou(message.summary.needs_you_idx);
        }
        break;
      default: break;
    }
  });

  // On load, ask the SW whether this tab is already being watched — closes
  // the race where watch_start fired before this content script existed
  // (tab just opened, or an SPA nav swapped documents).
  try {
    chrome.runtime.sendMessage({ _je_ready: true });
  } catch (_e) { /* orphaned frame */ }
})();
