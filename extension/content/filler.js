// Fill executor. Writes values into fields via the native prototype setter
// so React/Vue controlled inputs register the change, re-checks empty+
// unfocused immediately before writing (the user's typing always wins),
// attaches files via DataTransfer, and (011) operates custom dropdowns and
// typeaheads.
//
// SAFETY INVARIANT: the ONLY click path is safeClick(), which refuses any
// element the shared denylist (window.jeClickGuard) flags as a submit/apply/
// next/login control. The companion may click a field's OWN widget to set a
// value; the user performs every real submit/login themselves.
//
// Classic script: exposes window.jeFiller. Depends on window.jeClickGuard
// (loaded first per manifest order).
"use strict";

window.jeFiller = (function () {
  const OPTION_WAIT_MS = 1500; // clarify Q2: per-widget popup/suggestion budget

  const nativeInputSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, "value").set;
  const nativeTextareaSetter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype, "value").set;
  const nativeSelectSetter = Object.getOwnPropertyDescriptor(
    window.HTMLSelectElement.prototype, "value").set;

  function fireInput(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function setNativeValue(el, value) {
    const proto = el.tagName === "TEXTAREA" ? nativeTextareaSetter
      : el.tagName === "SELECT" ? nativeSelectSetter : nativeInputSetter;
    proto.call(el, value);
    fireInput(el);
  }

  function normText(s) {
    return (s || "").trim().toLowerCase().replace(/\s+/g, " ");
  }

  // The one and only click path. Refuses submit-class controls.
  function safeClick(el) {
    if (!el) { throw new Error("no element to click"); }
    if (window.jeClickGuard.isDenylisted(el)) {
      throw new Error("refused: submit-class control");
    }
    el.click();
  }

  // The value a field currently displays (native value, or a custom
  // widget's selected-value node) — for the non-empty-is-sacred check.
  function currentDisplayed(el) {
    if (el.type === "checkbox" || el.type === "radio") {
      return el.checked ? "on" : "";
    }
    const sv = el.querySelector &&
      el.querySelector('[class*=singleValue],[class*="-value"]');
    if (sv) { return sv.textContent.trim(); }
    if ("value" in el && el.value) { return el.value; }
    return "";
  }

  function fillable(el) {
    if (el === document.activeElement) { return false; }
    return !currentDisplayed(el).trim();
  }

  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

  async function waitFor(fn, budgetMs) {
    const deadline = Date.now() + budgetMs;
    while (Date.now() < deadline) {
      const r = fn();
      if (r) { return r; }
      await sleep(80);
    }
    return null;
  }

  function visibleOptions() {
    return Array.from(document.querySelectorAll('[role=option]'))
      .filter((o) => o.offsetParent !== null);
  }

  function findOption(target) {
    const opts = visibleOptions();
    return opts.find((o) => normText(o.textContent) === target)
      || opts.find((o) => normText(o.textContent).indexOf(target) !== -1)
      || null;
  }

  function closePopup(el) {
    el.dispatchEvent(new KeyboardEvent("keydown",
      { key: "Escape", bubbles: true }));
  }

  async function fillCombobox(el, optionLabel) {
    const target = normText(optionLabel);
    safeClick(el); // open the dropdown
    const opt = await waitFor(() => findOption(target), OPTION_WAIT_MS);
    if (!opt) { closePopup(el); throw new Error("no matching option"); }
    safeClick(opt);
    await sleep(60);
    if (!currentDisplayed(el).trim()) { throw new Error("value did not take"); }
  }

  async function fillTypeahead(el, value) {
    setNativeValue(el, value); // the site fetches suggestions on input
    const target = normText(value);
    const opt = await waitFor(() => findOption(target), OPTION_WAIT_MS);
    if (!opt) { throw new Error("no matching suggestion"); }
    safeClick(opt);
  }

  async function attachFile(el, fileUrl) {
    const resp = await fetch(fileUrl);
    const blob = await resp.blob();
    const name = (el.getAttribute("data-je-filename")) || "resume.pdf";
    const file = new File([blob], name, { type: blob.type || "application/pdf" });
    const dt = new DataTransfer();
    dt.items.add(file);
    el.files = dt.files;
    fireInput(el);
  }

  function selectByLabel(el, label) {
    const opt = Array.from(el.options).find((o) => o.text === label);
    if (!opt) { throw new Error("no matching option"); }
    el.value = opt.value;
    fireInput(el);
  }

  async function applyOne(item) {
    const el = window.jeScanner.elementByIdx(item.je_idx);
    if (!el) { return { je_idx: item.je_idx, outcome: "not_found" }; }
    if (item.kind !== "file" && !fillable(el)) {
      return { je_idx: item.je_idx,
               outcome: el === document.activeElement ? "focused"
                 : "skipped_existing" };
    }
    try {
      if (item.kind === "file") {
        await attachFile(el, item.file_url);
      } else if (item.kind === "select") {
        selectByLabel(el, item.option_label);
      } else if (item.kind === "combobox") {
        await fillCombobox(el, item.option_label || item.value);
      } else if (item.kind === "typeahead") {
        await fillTypeahead(el, item.value);
      } else if (item.kind === "checkbox") {
        if (!el.checked) { el.checked = true; fireInput(el); }
      } else {
        setNativeValue(el, item.value);
      }
      return { je_idx: item.je_idx, outcome: "filled" };
    } catch (_e) {
      return { je_idx: item.je_idx, outcome: "needs_manual" };
    }
  }

  async function apply(items) {
    const results = [];
    for (const item of items) {
      results.push(await applyOne(item));
    }
    return results;
  }

  return { apply };
})();
