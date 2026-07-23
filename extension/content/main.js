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

  function scan() {
    if (!watching) { return; }
    let descriptors;
    try { descriptors = window.jeScanner.serialize(); } catch (_e) { return; }
    toApp({
      type: "fields",
      url: location.href,
      doc: window.jeScanner.docToken(),
      descriptors,
    });
  }

  function scheduleScan() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(scan, 500);
  }

  function startWatch() {
    if (watching) { return; }
    watching = true;
    observer = new MutationObserver(scheduleScan);
    observer.observe(document.documentElement, {
      childList: true, subtree: true, attributes: true,
      attributeFilter: ["value", "style", "class", "hidden"],
    });
    // Safety poll covers observer blind spots (value mutations that change
    // no observed attribute).
    safetyTimer = setInterval(scan, 2000);
    if (isTop && window.jeOverlay) { window.jeOverlay.show(); }
    // Detect the user's own submission — never our doing (we never click).
    document.addEventListener("submit", onSubmit, true);
    scan();
  }

  function teardown() {
    watching = false;
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
      case "watch": startWatch(); break;
      case "unwatch": teardown(); break;
      case "fill":
        // only the addressed frame applies (frame_id is the app's routing;
        // Chrome already delivered this to the right frame via sendMessage)
        onFill(message);
        break;
      case "overlay_state":
        if (isTop && window.jeOverlay) { window.jeOverlay.update(message.summary); }
        break;
      default: break;
    }
  });
})();
