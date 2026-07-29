// On-page review panel. Lives in a shadow root so page CSS can't reach in
// and our styles can't leak out.
//
// It has ZERO controls that act on the page by themselves. It never clicks
// anything on the site. Its buttons only: copy text to the clipboard, ask
// the app to re-scan, insert an answer into the ONE field the applicant
// chose, or send back an answer the applicant typed.
//
// 017: this became the review surface. It used to show a COUNT ("N AI
// draft(s) — review in the app"), so an answer that was drafted but not
// filled could not be read without leaving the tab — the report was simply
// "i am unable to see the drafted responses". It now lists every question
// with its full answer, offers Copy and Insert, and gives each refused
// question an input so it can be answered once and remembered (D7).
//
// The shadow root is OPEN (016 used closed). discovery.js already made that
// choice so integration tests can drive its controls; this panel now has
// controls worth asserting too. CSS isolation is unaffected.
//
// Classic script: exposes window.jeOverlay (top frame only uses it).
"use strict";

window.jeOverlay = (function () {
  let host = null;
  let root = null;
  let fillAgainHandler = null;
  let answerHandler = null;
  let insertHandler = null;
  let jumpHandler = null;

  function build() {
    if (host) { return; }
    host = document.createElement("div");
    host.id = "je-companion-overlay-host";
    host.style.cssText = "position:fixed;z-index:2147483647;top:16px;" +
      "right:16px;all:initial;";
    root = host.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        .panel{font:13px/1.4 system-ui,sans-serif;background:#0d1117;
          color:#e6edf3;border:1px solid #30363d;border-radius:10px;
          width:320px;max-height:72vh;display:flex;flex-direction:column;
          box-shadow:0 8px 24px rgba(0,0,0,.4);overflow:hidden}
        .hd{display:flex;align-items:center;gap:8px;padding:10px 12px;
          background:#161b22;border-bottom:1px solid #30363d;font-weight:600}
        .dot{width:8px;height:8px;border-radius:50%;background:#1a7f37}
        .bd{padding:10px 12px;overflow-y:auto}
        .row{display:flex;justify-content:space-between;margin:3px 0}
        .muted{color:#8b949e}
        .reminder{margin-top:8px;padding:6px 8px;background:#1f2937;
          border-radius:6px;color:#f0b429;font-size:12px}
        .drafts{margin-top:6px;color:#a371f7;font-size:12px}
        .attn{margin-top:6px;color:#f0b429;font-size:12px}
        .attn li{margin-left:14px;list-style:disc}
        .note{margin-top:6px;color:#8b949e;font-size:12px}
        .again{margin-top:8px;width:100%;padding:6px 8px;font:12px system-ui;
          background:#21262d;color:#e6edf3;border:1px solid #30363d;
          border-radius:6px;cursor:pointer}
        .again:hover{background:#30363d}
        .answers{margin-top:10px;border-top:1px solid #30363d;padding-top:8px}
        .answers h4{margin:0 0 6px;font-size:11px;color:#8b949e;
          font-weight:600;text-transform:uppercase;letter-spacing:.04em}
        .qa{margin:0 0 10px;padding-bottom:8px;border-bottom:1px solid #21262d}
        .qa .q{font-size:12px;color:#c9d1d9;margin-bottom:3px}
        .qa .a{font-size:12px;color:#e6edf3;white-space:pre-wrap;
          word-break:break-word}
        .qa .a.drafted{color:#a371f7}
        .qa .why{font-size:11px;color:#f0b429;margin-top:2px}
        .qa .acts{display:flex;gap:6px;margin-top:5px}
        .qa button{padding:3px 8px;font:11px system-ui;background:#21262d;
          color:#e6edf3;border:1px solid #30363d;border-radius:5px;
          cursor:pointer}
        .qa button:hover{background:#30363d}
        .qa input{width:100%;margin-top:4px;padding:4px 6px;
          font:12px system-ui;background:#0d1117;color:#e6edf3;
          border:1px solid #30363d;border-radius:5px}
      </style>
      <div class="panel">
        <div class="hd"><span class="dot"></span><span>Job Engine — filling</span></div>
        <div class="bd">
          <div class="row"><span class="muted">Fields seen</span><span id="seen">0</span></div>
          <div class="row"><span class="muted">Filled</span><span id="filled">0</span></div>
          <div class="row"><span class="muted">Need you</span><span id="needs">0</span></div>
          <div class="drafts" id="drafts" hidden></div>
          <div class="attn" id="attn" hidden></div>
          <div class="note" id="note" hidden></div>
          <button class="again" id="again">Fill again</button>
          <div class="answers" id="answers" hidden>
            <h4>Answers</h4>
            <div id="answer-list"></div>
          </div>
          <div class="reminder" id="msg">You click apply / submit — never us.</div>
        </div>
      </div>`;
    root.getElementById("again").addEventListener("click", function () {
      if (fillAgainHandler) { fillAgainHandler(); }
    });
    document.body.appendChild(host);
  }

  function onFillAgain(handler) { fillAgainHandler = handler; }
  function onAnswer(handler) { answerHandler = handler; }
  function onInsert(handler) { insertHandler = handler; }
  function onJump(handler) { jumpHandler = handler; }

  function note(text) {
    build();
    const el = root.getElementById("note");
    el.textContent = text;
    el.hidden = !text;
  }

  function show() {
    build();
    host.style.display = "block";
  }

  function hide() {
    if (host) { host.remove(); }
    host = null;
    root = null;
  }

  function update(summary) {
    build();
    if (!summary) { return; }
    root.getElementById("seen").textContent = summary.seen || 0;
    root.getElementById("filled").textContent = summary.filled || 0;
    root.getElementById("needs").textContent = summary.needs_you || 0;
    host.dataset.jeSeen = String(summary.seen || 0);
    host.dataset.jeFilled = String(summary.filled || 0);
    host.dataset.jeNeedsYou = String(summary.needs_you || 0);

    const drafts = root.getElementById("drafts");
    if (summary.drafts) {
      drafts.textContent = summary.drafts +
        " AI draft(s) — read them below before submitting";
      drafts.hidden = false;
    } else {
      drafts.hidden = true;
    }
    if (summary.message) {
      root.getElementById("msg").textContent =
        "You click apply / submit — never us. " + summary.message;
    }
    const attn = root.getElementById("attn");
    const labels = summary.attention || [];
    if (labels.length) {
      const list = document.createElement("ul");
      labels.forEach(function (label) {
        const li = document.createElement("li");
        li.textContent = label;
        list.appendChild(li);
      });
      attn.textContent = "Needs you:";
      attn.appendChild(list);
      attn.hidden = false;
    } else {
      attn.textContent = "";
      attn.hidden = true;
    }
  }

  // 017 (FR-034/FR-035/FR-045): every question with its FULL answer, plus
  // Copy, Insert, and — for anything we declined to answer — an input that
  // fills the field now and is remembered for future applications.
  function setAnswers(items, truncated) {
    build();
    const box = root.getElementById("answers");
    const list = root.getElementById("answer-list");
    const rows = items || [];
    host.dataset.jeAnswers = String(rows.length);
    list.textContent = "";
    if (!rows.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    rows.forEach(function (item) {
      list.appendChild(renderRow(item));
    });
    if (truncated) {
      const more = document.createElement("div");
      more.className = "muted";
      more.textContent = "Not every answer fits here — the app's Apply " +
        "Assist page has the full list.";
      list.appendChild(more);
    }
  }

  function renderRow(item) {
    const wrap = document.createElement("div");
    wrap.className = "qa";
    wrap.dataset.jeState = item.state || "";

    const q = document.createElement("div");
    q.className = "q";
    q.textContent = item.question || "";
    wrap.appendChild(q);

    if (item.answer) {
      const a = document.createElement("div");
      a.className = "a" + (item.state === "drafted" ? " drafted" : "");
      a.textContent = item.answer;
      wrap.appendChild(a);
      wrap.appendChild(answerActions(item));
    } else if (item.state === "drafting") {
      const a = document.createElement("div");
      a.className = "a muted";
      a.textContent = "drafting…";
      wrap.appendChild(a);
    }

    if (item.askable) {
      const why = document.createElement("div");
      why.className = "why";
      why.textContent = reasonText(item.reason);
      wrap.appendChild(why);

      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = "Your answer — saved for next time";
      input.addEventListener("keydown", function (evt) {
        if (evt.key !== "Enter") { return; }
        const typed = input.value.trim();
        if (!typed || !answerHandler) { return; }
        answerHandler(item.question, typed, item.je_idx || "");
        input.disabled = true;
        why.textContent = "Saved — it fills on the next scan.";
      });
      wrap.appendChild(input);
    }
    return wrap;
  }

  function answerActions(item) {
    const acts = document.createElement("div");
    acts.className = "acts";

    const copy = document.createElement("button");
    copy.textContent = "Copy";
    copy.addEventListener("click", function () {
      navigator.clipboard.writeText(item.answer).then(function () {
        copy.textContent = "Copied";
      }, function () { copy.textContent = "Copy failed"; });
    });
    acts.appendChild(copy);

    if (item.je_idx) {
      const insert = document.createElement("button");
      insert.textContent = "Insert";
      insert.addEventListener("click", function () {
        if (insertHandler) { insertHandler(item.je_idx, item.answer); }
      });
      acts.appendChild(insert);

      const jump = document.createElement("button");
      jump.textContent = "Show me";
      jump.addEventListener("click", function () {
        if (jumpHandler) { jumpHandler(item.je_idx); }
      });
      acts.appendChild(jump);
    }
    return acts;
  }

  function reasonText(reason) {
    switch (reason) {
      case "binding_commitment":
        return "This one commits you to something — your call, not ours.";
      case "never_generated":
      case "cannot_answer":
        return "Only you know this one.";
      case "profile_fact_missing":
        return "Add it to your profile and it fills automatically next time.";
      case "no_valid_option":
      case "not_an_option_label":
        return "No option here matched your stored answer.";
      default:
        return "Needs you.";
    }
  }

  return { show, hide, update, note, onFillAgain, setAnswers, onAnswer,
           onInsert, onJump };
})();
