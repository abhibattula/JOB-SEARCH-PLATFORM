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
  //
  // 019 (T036, FR-012): judged by `isWidgetOperable`, which reads the
  // element's OWN accessible name for the text verdict while still folding
  // descendant TYPES. Folding descendant TEXT (the 011 behavior) refused an
  // ordinary dropdown whenever the card around it happened to contain the
  // word "Next" or "Save" — the widget became needs_manual for a reason
  // that had nothing to do with it. A real submit control is still refused,
  // by type, which is the danger that mattered.
  function safeClick(el) {
    if (!el) { throw new Error("no element to click"); }
    if (!window.jeClickGuard.isWidgetOperable(el)) {
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
    // 019 (FR-010): a control resting on its placeholder has no value —
    // treating "Select…" as the applicant's choice is what made those
    // dropdowns permanently skipped_existing.
    const placeholder = window.jeScanner && window.jeScanner.isPlaceholderValue;
    const sv = el.querySelector &&
      el.querySelector('[class*=singleValue],[class*="-value"]');
    if (sv) {
      const text = sv.textContent.trim();
      return (placeholder && placeholder(text)) ? "" : text;
    }
    if ("value" in el && el.value) {
      if (el.tagName === "SELECT") {
        const text = (el.options[el.selectedIndex] || {}).text || "";
        return (placeholder && placeholder(text)) ? "" : el.value;
      }
      return el.value;
    }
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

  // 016 (T013): harvest widened beyond [role=option] — react-select uses
  // it, but plenty of menus render plain <li> under a listbox or
  // *select__option* classes without the role.
  // 019 (T030, FR-009): Workday renders its menu rows as
  // [data-automation-id=promptOption] divs — no role, no listbox li, no
  // select__option class — so every Workday dropdown matched nothing here
  // and became needs_manual. 019 (FR-008) also routes the lookup through
  // deepQueryAll so options inside an open shadow root are found.
  function visibleOptions() {
    const query = window.jeScanner && window.jeScanner.deepQueryAll
      ? window.jeScanner.deepQueryAll
      : (sel) => Array.from(document.querySelectorAll(sel));
    const visible = window.jeScanner && window.jeScanner.isVisible
      ? window.jeScanner.isVisible
      : (o) => o.offsetParent !== null;
    return query(
      '[role=option], [role=listbox] li, [class*="select__option"],'
      + ' [data-automation-id="promptOption"],'
      + ' [data-automation-id*="menuItem"]')
      .filter(visible);
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

  // 017 (C9, FR-029/FR-030): fetch the file through the SERVICE WORKER.
  //
  // This used to be a direct `fetch(fileUrl)` from the content script with
  // the app's RELATIVE url, so it resolved against the job board. Greenhouse
  // answers unknown paths with its SPA's HTML and status 200, which meant a
  // `File` named resume.pdf containing an HTML page was attached and
  // reported as filled. Making the url absolute does not help either: MV3
  // content-script fetches carry the page's origin and the app sets no CORS
  // headers. The service worker holds host_permissions for 127.0.0.1, and
  // main.js has always stated that content scripts must not hit loopback.
  //
  // Nothing is attached unless the bytes look like the document we asked for.
  function decodeBase64(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) { bytes[i] = binary.charCodeAt(i); }
    return bytes;
  }

  function looksLikeExpectedDocument(bytes, mime) {
    if (!bytes || !bytes.length) { return false; }
    if ((mime || "").indexOf("pdf") === -1) { return true; }
    // "%PDF" — an HTML error body fails here, which is the whole point.
    return bytes[0] === 0x25 && bytes[1] === 0x50 &&
      bytes[2] === 0x44 && bytes[3] === 0x46;
  }

  async function attachFile(el, fileUrl, filename, mime) {
    const reply = await chrome.runtime.sendMessage(
      { _je_file: true, path: fileUrl });
    if (!reply || !reply.ok) {
      throw new Error("file unavailable: " + ((reply && reply.error) || "no reply"));
    }
    const bytes = decodeBase64(reply.bytes);
    const type = mime || reply.mime || "application/pdf";
    if (!looksLikeExpectedDocument(bytes, type)) {
      throw new Error("fetched content is not the expected document");
    }
    const name = filename || reply.name || "resume.pdf";
    const file = new File([bytes], name, { type: type });
    const dt = new DataTransfer();
    dt.items.add(file);
    el.files = dt.files;
    fireInput(el);
  }

  // 016 (T013): NORMALIZED matching — strict `o.text === label` broke on
  // whitespace/case differences between the canonical answer and the DOM.
  function selectByLabel(el, label) {
    const target = normText(label);
    const options = Array.from(el.options);
    const opt = options.find((o) => normText(o.text) === target)
      || (target && options.find(
        (o) => normText(o.text).indexOf(target) !== -1));
    if (!opt) { throw new Error("no matching option"); }
    el.value = opt.value;
    fireInput(el);
  }

  // 016 (T013): grouped radios — the item's element is the group's FIRST
  // member; the member whose label matches the answer gets checked.
  function radioGroupMembers(el) {
    if (!el.name) { return [el]; }
    const scope = el.form || document;
    return Array.from(scope.querySelectorAll("input[type=radio]"))
      .filter((member) => member.name === el.name);
  }

  function radioLabel(member) {
    return (member.labels && member.labels[0]
      ? member.labels[0].innerText : "") || member.value || "";
  }

  function findRadioMember(el, label) {
    const target = normText(label);
    return radioGroupMembers(el)
      .find((member) => normText(radioLabel(member)) === target) || null;
  }

  async function applyOne(item) {
    const el = window.jeScanner.elementByIdx(item.je_idx);
    if (!el) { return { je_idx: item.je_idx, outcome: "not_found" }; }
    if (item.kind === "radio") {
      // Honest outcomes only: an unset radio is NEVER reported filled
      // (the old fallthrough text-set the element and lied — RC2).
      if (radioGroupMembers(el).some((member) => member.checked)) {
        return { je_idx: item.je_idx, outcome: "skipped_existing" };
      }
      const member = findRadioMember(el, item.value);
      if (!member) { return { je_idx: item.je_idx, outcome: "needs_manual" }; }
      member.checked = true;
      fireInput(member);
      return { je_idx: item.je_idx,
               outcome: member.checked ? "filled" : "needs_manual" };
    }
    if (item.kind !== "file" && !fillable(el)) {
      return { je_idx: item.je_idx,
               outcome: el === document.activeElement ? "focused"
                 : "skipped_existing" };
    }
    try {
      if (item.kind === "file") {
        await attachFile(el, item.file_url, item.filename, item.mime);
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
      const result = await applyOne(item);
      // 016 (T017): a drafted answer stays visibly highlighted until the
      // USER edits the field — their edit clears it (D2).
      if (result.outcome === "filled" && item.flag) {
        const el = window.jeScanner.elementByIdx(item.je_idx);
        if (el) { annotate(el, item.flag); }
      }
      results.push(result);
    }
    return results;
  }

  function annotate(el, flag) {
    try {
      if (el.dataset.jeFlag === flag) { return; }
      el.dataset.jeFlag = flag;
      el.style.outline = flag === "ai_draft"
        ? "2px solid #a371f7" : "2px solid #f0b429";
      el.style.outlineOffset = "2px";
      const clear = function () {
        delete el.dataset.jeFlag;
        el.style.outline = "";
        el.style.outlineOffset = "";
        el.removeEventListener("input", clear);
        el.removeEventListener("change", clear);
      };
      el.addEventListener("input", clear);
      el.addEventListener("change", clear);
    } catch (_e) { /* highlighting is best-effort, never fatal */ }
  }

  // 016 (T017): fields the human must answer (sensitive/no-match/missing
  // fact) — flagged even though nothing was filled.
  function annotateNeedsYou(jeIdxList) {
    for (const jeIdx of jeIdxList || []) {
      const el = window.jeScanner.elementByIdx(jeIdx);
      if (el) { annotate(el, "needs_you"); }
    }
  }

  return { apply, annotateNeedsYou };
})();
