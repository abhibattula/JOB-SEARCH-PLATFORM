/* Job Engine shared UI module (feature 007).
   Vendored-vanilla: no framework, no build step.
   - toast(): visible confirmation for every action (FR-023)
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
