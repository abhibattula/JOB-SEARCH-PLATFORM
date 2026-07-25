/* 014 (US3): command palette (Ctrl/Cmd-K) + feed keyboard navigation.
   Vanilla, no dependency. Navigation + global actions only. ARIA dialog with a
   focus trap while open; Escape closes. Progressive — the app is fully usable
   without it. */
"use strict";

(function () {
  var NAV = [
    ["Feed", "/"],
    ["New today", "/?seen=24h&sort=score"],
    ["Best matches", "/?min_score=70&sort=score"],
    ["Ineligible jobs", "/?ineligible=1"],
    ["Saved", "/?status=saved"],
    ["Applied", "/?status=applied"],
    ["Hidden", "/?status=hidden"],
    ["Analytics", "/analytics"],
    ["Apply Assist", "/autofill"],
    ["Companion", "/companion"],
    ["Profile", "/profile"],
    ["Settings", "/settings"],
    ["Diagnostics", "/diagnostics"],
  ];

  function toast(m, kind) { if (window.toast) { window.toast(m, kind); } }

  function refreshNow() {
    fetch("/api/refresh?force=1", { method: "POST" })
      .then(function () { toast("Refreshing…"); setTimeout(function () {
        location.reload();
      }, 900); })
      .catch(function () { toast("Refresh failed", "error"); });
  }

  function toggleTheme() {
    var root = document.documentElement;
    var cur = root.dataset.theme;
    // if unset (OS-driven), flip to the opposite of what's shown
    var next = cur === "dark" ? "light"
      : cur === "light" ? "dark"
      : (matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark");
    root.dataset.theme = next;
    fetch("/api/theme", {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "theme=" + next,
    }).catch(function () {});
    toast(next === "dark" ? "Dark theme" : "Light theme");
  }

  function commands() {
    var cmds = NAV.map(function (n) {
      return { kind: "go", label: n[0], hint: n[1], run: function () { navTo(n[1]); } };
    });
    cmds.push({ kind: "do", label: "Refresh now", hint: "fetch new jobs", run: refreshNow });
    cmds.push({ kind: "do", label: "Toggle light / dark theme", hint: "appearance", run: toggleTheme });
    cmds.push({ kind: "do", label: "Start Apply Assist", hint: "autofill", run: function () { navTo("/autofill"); } });
    return cmds;
  }

  function navTo(url) {
    // let HTMX/View-Transitions handle same-origin nav if boosted; else assign
    window.location.href = url;
  }

  // ---- palette UI ----
  var backdrop, input, list, all = [], filtered = [], sel = 0, lastFocus = null;

  function build() {
    backdrop = document.createElement("div");
    backdrop.className = "cmdk-backdrop";
    backdrop.setAttribute("role", "dialog");
    backdrop.setAttribute("aria-modal", "true");
    backdrop.setAttribute("aria-label", "Command palette");
    backdrop.innerHTML =
      '<div class="cmdk"><input type="text" placeholder="Jump to a page or run an action…" ' +
      'aria-label="Command palette" autocomplete="off" spellcheck="false">' +
      '<ul role="listbox"></ul></div>';
    input = backdrop.querySelector("input");
    list = backdrop.querySelector("ul");
    backdrop.addEventListener("click", function (e) { if (e.target === backdrop) { close(); } });
    input.addEventListener("input", function () { render(input.value); });
    input.addEventListener("keydown", onKey);
    document.body.appendChild(backdrop);
  }

  function open() {
    if (backdrop) { return; }
    lastFocus = document.activeElement;
    all = commands();
    build();
    render("");
    input.focus();
  }

  function close() {
    if (!backdrop) { return; }
    backdrop.remove(); backdrop = null;
    if (lastFocus && lastFocus.focus) { lastFocus.focus(); }
  }

  function render(q) {
    q = (q || "").toLowerCase().trim();
    filtered = all.filter(function (c) { return !q || c.label.toLowerCase().indexOf(q) >= 0; });
    sel = 0;
    if (!filtered.length) {
      list.innerHTML = '<div class="cmdk-empty">No matches.</div>';
      return;
    }
    list.innerHTML = filtered.map(function (c, i) {
      return '<li role="option" data-i="' + i + '" aria-selected="' + (i === 0) + '">' +
        '<span class="kind">' + c.kind + '</span>' + escapeHtml(c.label) +
        '<span class="k">' + escapeHtml(c.hint) + '</span></li>';
    }).join("");
    Array.prototype.forEach.call(list.querySelectorAll("li"), function (li) {
      li.addEventListener("click", function () { run(parseInt(li.dataset.i, 10)); });
    });
  }

  function move(d) {
    var items = list.querySelectorAll("li");
    if (!items.length) { return; }
    items[sel].setAttribute("aria-selected", "false");
    sel = (sel + d + items.length) % items.length;
    items[sel].setAttribute("aria-selected", "true");
    items[sel].scrollIntoView({ block: "nearest" });
  }

  function run(i) {
    var c = filtered[i];
    close();
    if (c) { c.run(); }
  }

  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") { e.preventDefault(); run(sel); }
    else if (e.key === "Tab") { e.preventDefault(); }  // trap focus in the input
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // ---- global shortcuts ----
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      if (backdrop) { close(); } else { open(); }
      return;
    }
    if (backdrop) { return; }
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    var typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    if (typing) { return; }
    // "/" focuses the feed search
    if (e.key === "/") {
      var search = document.querySelector('input[type="search"]');
      if (search) { e.preventDefault(); search.focus(); }
      return;
    }
    // j/k move through feed rows
    if (e.key === "j" || e.key === "k") { feedNav(e.key === "j" ? 1 : -1); }
    if (e.key === "Enter") { openFocusedRow(); }
  });

  function rows() { return Array.prototype.slice.call(document.querySelectorAll(".feed tbody tr")); }
  var rowIdx = -1;
  function feedNav(d) {
    var r = rows(); if (!r.length) { return; }
    if (rowIdx >= 0 && r[rowIdx]) { r[rowIdx].classList.remove("kbd-focus"); }
    rowIdx = Math.max(0, Math.min(r.length - 1, rowIdx + d));
    var el = r[rowIdx];
    el.classList.add("kbd-focus");
    el.scrollIntoView({ block: "nearest" });
  }
  function openFocusedRow() {
    var r = rows();
    if (rowIdx >= 0 && r[rowIdx]) {
      var a = r[rowIdx].querySelector(".role a, a");
      if (a) { a.click(); }
    }
  }
})();
