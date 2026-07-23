// On-page progress panel. Lives in a CLOSED shadow root so page CSS can't
// reach in and our styles can't leak out. Shows what the app reports —
// fields seen/filled, AI-draft flags, and the "you click submit" reminder.
//
// It has ZERO controls that touch the page. It never clicks anything.
//
// Classic script: exposes window.jeOverlay (top frame only uses it).
"use strict";

window.jeOverlay = (function () {
  let host = null;
  let root = null;
  let els = {};

  function build() {
    if (host) { return; }
    host = document.createElement("div");
    host.id = "je-companion-overlay-host";
    host.style.cssText = "position:fixed;z-index:2147483647;top:16px;" +
      "right:16px;all:initial;";
    root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `
      <style>
        .panel{font:13px/1.4 system-ui,sans-serif;background:#0d1117;
          color:#e6edf3;border:1px solid #30363d;border-radius:10px;
          width:250px;box-shadow:0 8px 24px rgba(0,0,0,.4);overflow:hidden}
        .hd{display:flex;align-items:center;gap:8px;padding:10px 12px;
          background:#161b22;border-bottom:1px solid #30363d;font-weight:600}
        .dot{width:8px;height:8px;border-radius:50%;background:#1a7f37}
        .bd{padding:10px 12px}
        .row{display:flex;justify-content:space-between;margin:3px 0}
        .muted{color:#8b949e}
        .reminder{margin-top:8px;padding:6px 8px;background:#1f2937;
          border-radius:6px;color:#f0b429;font-size:12px}
        .drafts{margin-top:6px;color:#a371f7;font-size:12px}
      </style>
      <div class="panel">
        <div class="hd"><span class="dot"></span><span>Job Engine — filling</span></div>
        <div class="bd">
          <div class="row"><span class="muted">Fields seen</span><span id="seen">0</span></div>
          <div class="row"><span class="muted">Filled</span><span id="filled">0</span></div>
          <div class="drafts" id="drafts" style="display:none"></div>
          <div class="reminder" id="msg">You click apply / submit — never us.</div>
        </div>
      </div>`;
    els = {
      seen: root.getElementById("seen"),
      filled: root.getElementById("filled"),
      drafts: root.getElementById("drafts"),
      msg: root.getElementById("msg"),
    };
    (document.body || document.documentElement).appendChild(host);
  }

  function show() { build(); if (host) { host.style.display = "block"; } }
  function hide() { if (host) { host.remove(); host = null; root = null; } }

  function update(summary) {
    if (!host) { build(); }
    if (!summary) { return; }
    els.seen.textContent = summary.seen ?? 0;
    els.filled.textContent = summary.filled ?? 0;
    if (summary.drafts) {
      els.drafts.style.display = "block";
      els.drafts.textContent =
        `${summary.drafts} AI draft(s) — review in the app before submitting`;
    } else {
      els.drafts.style.display = "none";
    }
    if (summary.message) { els.msg.textContent = summary.message; }
  }

  return { show, hide, update };
})();
