// Field serialization + stamping — byte-for-byte the same descriptor shape
// as engine/autofill/watcher.py SERIALIZE_JS, so the app's fields.py +
// adapters.py classify companion output unchanged. Stamps live in DOM
// attributes (data-je-idx + a per-document token) so they survive
// content-script reloads.
//
// Classic script (not a module): exposes window.jeScanner.
"use strict";

window.jeScanner = (function () {
  // Same selector the app uses (mirrored; the app also re-exports it).
  // 011: also custom dropdowns (ARIA comboboxes/listboxes, React-Select).
  const FIELD_SELECTOR = [
    "input:not([type=hidden]):not([type=submit]):not([type=button])",
    "select",
    "textarea",
    "[role=combobox]",
    "[role=listbox]",
    "[aria-haspopup=listbox]",
    "[class*=select__control]",
  ].join(",");

  // 011: widget classification + displayed-value read — byte-parallel with
  // engine/autofill/watcher.py SERIALIZE_JS jeWidget/jeValue.
  function jeWidget(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === "select") { return "native_select"; }
    const role = (el.getAttribute("role") || "").toLowerCase();
    const ac = (el.getAttribute("aria-autocomplete") || "").toLowerCase();
    const isInput = tag === "input" || tag === "textarea";
    if (isInput && (ac === "list" || ac === "both")) { return "typeahead"; }
    if (role === "combobox" || role === "listbox" ||
        el.getAttribute("aria-haspopup") === "listbox" ||
        /select__control/.test(el.className || "")) {
      return (isInput && ac) ? "typeahead" : "custom_combobox";
    }
    return "";
  }

  function jeValue(el, widget) {
    const type = el.type || "";
    if (type === "checkbox" || type === "radio") {
      return el.checked ? "on" : "";
    }
    if (widget === "native_select") {
      return el.value ? ((el.options[el.selectedIndex] || {}).text || "") : "";
    }
    if (widget === "custom_combobox" || widget === "typeahead") {
      const sv = el.querySelector &&
        el.querySelector('[class*=singleValue],[class*="-value"]');
      if (sv) { return sv.textContent.trim(); }
      if (el.value) { return el.value; }
      const t = (el.textContent || "").trim();
      return /^(select|choose|--)/i.test(t) ? "" : t;
    }
    return el.value || "";
  }

  function docToken() {
    const root = document.documentElement;
    if (!root.dataset.jeDoc) {
      root.dataset.jeDoc = Math.random().toString(36).slice(2);
      root.dataset.jeNext = "1";
    }
    return root.dataset.jeDoc;
  }

  function stamp(el) {
    if (!el.dataset.jeIdx) {
      const root = document.documentElement;
      const n = parseInt(root.dataset.jeNext || "1", 10);
      el.dataset.jeIdx = String(n);
      root.dataset.jeNext = String(n + 1);
    }
    return el.dataset.jeIdx;
  }

  function labelText(el) {
    if (el.labels && el.labels[0]) { return el.labels[0].innerText || ""; }
    return el.getAttribute("aria-label") || "";
  }

  function describe(el) {
    const type = el.type || "";
    const widget = jeWidget(el);
    return {
      doc: docToken(),
      je_idx: stamp(el),
      tag: el.tagName.toLowerCase(),
      type: type,
      name: el.name || "",
      id: el.id || "",
      label_text: labelText(el),
      placeholder: el.placeholder || "",
      aria_label: el.getAttribute("aria-label") || "",
      autocomplete: el.autocomplete || "",
      value: jeValue(el, widget),
      options: el.tagName === "SELECT"
        ? Array.from(el.options).map((o) => o.text) : [],
      widget: widget,
      automation_id: el.getAttribute("data-automation-id") || "",
      maxlength: el.maxLength && el.maxLength > 0 ? el.maxLength : null,
      focused: el === document.activeElement,
      visible: !!(el.offsetParent || type === "file"),
    };
  }

  function serialize() {
    const els = document.querySelectorAll(FIELD_SELECTOR);
    return Array.from(els).map(describe);
  }

  function elementByIdx(jeIdx) {
    return document.querySelector(`[data-je-idx="${jeIdx}"]`);
  }

  return { serialize, elementByIdx, docToken };
})();
