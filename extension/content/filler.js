// Fill executor. Writes values into fields via the native prototype setter
// so React/Vue controlled inputs register the change, re-checks empty+
// unfocused immediately before writing (the user's typing always wins),
// and attaches files via DataTransfer.
//
// SAFETY INVARIANT: there is NO .click() call anywhere in this file. The
// user performs every apply/submit/login action themselves (constitution).
// The integration suite asserts this.
//
// Classic script: exposes window.jeFiller.
"use strict";

window.jeFiller = (function () {
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

  // Only fill when still empty and unfocused — the scan is up to a beat old.
  function fillable(el) {
    if (el === document.activeElement) { return false; }
    const isCheck = el.type === "checkbox" || el.type === "radio";
    const current = isCheck ? (el.checked ? "on" : "") : (el.value || "");
    return !current.trim();
  }

  async function attachFile(el, fileUrl) {
    // fileUrl is a one-time tokened endpoint on the local app; the SW fetch
    // avoids page-context loopback (Chrome 142 LNA). We fetch here because
    // the content script needs the bytes to build a File; the URL is
    // same-machine loopback and single-use.
    const resp = await fetch(fileUrl);
    const blob = await resp.blob();
    const name = (el.getAttribute("data-je-filename")) || "resume.pdf";
    const file = new File([blob], name, { type: blob.type || "application/pdf" });
    const dt = new DataTransfer();
    dt.items.add(file);
    el.files = dt.files;
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
      } else if (item.kind === "checkbox") {
        if (!el.checked) { el.checked = true; fireInput(el); }
      } else {
        // text and secret both write the raw value; the app already
        // decided masking for its own report — the DOM needs the real value
        setNativeValue(el, item.value);
      }
      return { je_idx: item.je_idx, outcome: "filled" };
    } catch (_e) {
      return { je_idx: item.je_idx, outcome: "needs_manual" };
    }
  }

  function selectByLabel(el, label) {
    const opt = Array.from(el.options).find((o) => o.text === label);
    if (!opt) { throw new Error("no matching option"); }
    el.value = opt.value;
    fireInput(el);
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
