/* Job Engine shared UI module (features 007/008).
   Vendored-vanilla: no framework, no build step.
   - toast(): visible confirmation for every action (FR-023)
   - copyText(): the ONE copy path — works inside the WebView2 shell where
     navigator.clipboard is permission-gated (008 FR-002)
   - external-link delegation: every target=_blank opens via the host so no
     link is ever a silent no-op in the shell (008 FR-004)
   - pollingAllowed(): gates HTMX polling so background refreshes never
     clobber an in-progress edit (FR-024)
   - theme toggle helper (FR-021)
   - automatic loading state on htmx-triggering buttons */
(function () {
  "use strict";

  /* ---------- toasts ---------- */
  let stack = null;
  function ensureStack() {
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      stack.setAttribute("aria-live", "polite");
      document.body.appendChild(stack);
    }
    return stack;
  }

  window.toast = function (message, kind) {
    const el = document.createElement("div");
    el.className = "toast" + (kind === "error" ? " error" : "");
    el.textContent = message;
    ensureStack().appendChild(el);
    setTimeout(function () { el.remove(); }, 3200);
  };

  /* ---------- copy (008 FR-002) ----------
     Three-step fallback, always toasting the real outcome:
     navigator.clipboard (normal browsers) -> hidden-textarea execCommand
     (WebView2/WKWebView without async-clipboard permission) -> host-side
     /api/clipboard (guaranteed: the server runs on this machine). */
  function copyViaExecCommand(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    area.remove();
    return ok;
  }

  window.copyText = function (text) {
    function done() { window.toast("Copied"); }
    function hostFallback() {
      fetch("/api/clipboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text }),
      }).then(function (r) {
        if (r.ok) { done(); } else { window.toast("Copy failed", "error"); }
      }).catch(function () { window.toast("Copy failed", "error"); });
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        if (copyViaExecCommand(text)) { done(); } else { hostFallback(); }
      });
    } else if (copyViaExecCommand(text)) {
      done();
    } else {
      hostFallback();
    }
  };

  /* ---------- external links (008 FR-004) ----------
     Delegated: catches template anchors AND server-generated fragments
     (e.g. the update link HTMX swaps into Settings). */
  document.addEventListener("click", function (evt) {
    const anchor = evt.target.closest ? evt.target.closest("a[target=_blank]") : null;
    if (!anchor || !anchor.href || anchor.href.indexOf("http") !== 0) { return; }
    evt.preventDefault();
    fetch("/api/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: anchor.href }),
    }).catch(function () {
      /* server unreachable — fall back to the browser's own handling */
      window.open(anchor.href, "_blank", "noopener");
    });
  });

  /* ---------- attention (009 FR-011) ----------
     Anything needing the user's eyes scrolls into view and flashes —
     review screens, conflicts, pending answers were historically easy
     to miss mid-page. */
  window.reveal = function (el) {
    if (!el || el.dataset.revealed) { return; }
    el.dataset.revealed = "1";
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("flash-attention");
    setTimeout(function () { el.classList.remove("flash-attention"); }, 2400);
  };

  /* ---------- in-app update (008 FR-030) ---------- */
  window.runUpdate = async function (btn) {
    btn.disabled = true;
    const bar = document.getElementById("update-progress");
    function status(text) { if (bar) { bar.textContent = text; } }
    try {
      const resp = await fetch("/api/updates/download", { method: "POST" });
      if (!resp.ok && resp.status !== 409) {
        throw new Error((await resp.json()).detail || "download failed");
      }
      for (;;) {
        const p = await (await fetch("/api/updates/progress")).json();
        if (p.state === "downloading") { status("downloading " + p.pct + "%"); }
        else if (p.state === "verifying") { status("verifying…"); }
        else if (p.state === "ready") { break; }
        else if (p.state === "failed" || p.state === "blocked") {
          throw new Error(p.error || p.state);
        }
        await new Promise(function (r) { setTimeout(r, 700); });
      }
      status("installing — the app will close and restart itself…");
      const inst = await fetch("/api/updates/install", { method: "POST" });
      if (!inst.ok) { throw new Error((await inst.json()).detail || "install refused"); }
    } catch (err) {
      status("✕ " + err.message + " — use the manual download link instead");
      btn.disabled = false;
    }
  };

  /* ---------- polling gate (FR-024) ----------
     Polling is paused while the user is mid-edit inside the region:
     any focused input/textarea/select, or an open notes <details>. */
  window.pollingAllowed = function () {
    const active = document.activeElement;
    if (
      active &&
      (active.tagName === "TEXTAREA" ||
        active.tagName === "INPUT" ||
        active.tagName === "SELECT")
    ) {
      return false;
    }
    return !document.querySelector(".notes-cell details[open]");
  };

  /* ---------- theme toggle (FR-021) ---------- */
  window.setTheme = function (value) {
    document.documentElement.setAttribute("data-theme", value);
    const body = new FormData();
    body.append("theme", value);
    fetch("/api/settings", { method: "POST", body: body }).then(function (r) {
      if (r.ok) { window.toast("Theme: " + value); }
    });
  };

  /* ---------- htmx feedback hooks ---------- */
  document.addEventListener("htmx:beforeRequest", function (evt) {
    const el = evt.detail.elt;
    if (el && el.tagName === "BUTTON") { el.classList.add("is-loading"); }
  });
  document.addEventListener("htmx:afterRequest", function (evt) {
    const el = evt.detail.elt;
    if (el && el.tagName === "BUTTON") { el.classList.remove("is-loading"); }
    // Visible confirmation for fire-and-forget actions (hx-swap="none")
    if (el && el.getAttribute && el.getAttribute("hx-swap") === "none") {
      if (evt.detail.successful) {
        window.toast(el.getAttribute("data-toast") || "Saved");
      } else {
        window.toast("Action failed", "error");
      }
    }
  });
})();
