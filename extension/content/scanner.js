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
      members: [],
      widget: widget,
      automation_id: el.getAttribute("data-automation-id") || "",
      maxlength: el.maxLength && el.maxLength > 0 ? el.maxLength : null,
      required: !!(el.required ||
                   el.getAttribute("aria-required") === "true"),
      focused: el === document.activeElement,
      visible: !!(el.offsetParent || type === "file"),
    };
  }

  // 016 (T011, R6): the question of a grouped control lives on its
  // fieldset legend / radiogroup label — never on the individual option.
  function groupQuestion(el) {
    const fieldset = el.closest("fieldset");
    if (fieldset) {
      const legend = fieldset.querySelector("legend");
      if (legend && legend.innerText.trim()) { return legend.innerText.trim(); }
    }
    const rg = el.closest("[role=radiogroup]");
    if (rg) {
      const aria = rg.getAttribute("aria-label");
      if (aria) { return aria; }
      const ids = rg.getAttribute("aria-labelledby");
      if (ids) {
        const texts = ids.split(/\s+/).map((id) => {
          const node = document.getElementById(id);
          return node ? node.innerText.trim() : "";
        }).filter(Boolean);
        if (texts.length) { return texts.join(" "); }
      }
    }
    return "";
  }

  // 016 (T011, R6): merge same-name radio sets into ONE logical field
  // (je_idx = FIRST member's — the stable ledger key). A lone radio keeps
  // today's shape. Checkbox sets are NEVER merged (multi-select is not
  // pick-one) — members just gain the group question as context.
  function groupControls(pairs) {
    const radios = new Map();
    const checks = new Map();
    pairs.forEach(function (pair, i) {
      const type = pair.el.type || "";
      if (type === "radio" && pair.el.name) {
        (radios.get(pair.el.name) || radios.set(pair.el.name, []).get(pair.el.name)).push(i);
      } else if (type === "checkbox" && pair.el.name) {
        (checks.get(pair.el.name) || checks.set(pair.el.name, []).get(pair.el.name)).push(i);
      }
    });
    const drop = new Set();
    for (const idxs of radios.values()) {
      if (idxs.length < 2) { continue; }
      const members = idxs.map(function (i) {
        return { je_idx: pairs[i].desc.je_idx,
                 label: pairs[i].desc.label_text || pairs[i].el.value || "" };
      });
      const first = pairs[idxs[0]];
      const checkedIdx = idxs.find(function (i) { return pairs[i].el.checked; });
      first.desc = Object.assign({}, first.desc, {
        type: "radio_group",
        label_text: groupQuestion(first.el),
        options: members.map(function (m) { return m.label; }),
        members: members,
        value: checkedIdx === undefined ? ""
          : (pairs[checkedIdx].desc.label_text || pairs[checkedIdx].el.value || ""),
        focused: idxs.some(function (i) { return pairs[i].desc.focused; }),
        visible: idxs.some(function (i) { return pairs[i].desc.visible; }),
        required: idxs.some(function (i) { return pairs[i].desc.required; }),
      });
      idxs.slice(1).forEach(function (i) { drop.add(i); });
    }
    for (const idxs of checks.values()) {
      if (idxs.length < 2) { continue; }
      const question = groupQuestion(pairs[idxs[0]].el);
      if (question) {
        idxs.forEach(function (i) {
          const own = pairs[i].desc.label_text;
          pairs[i].desc.label_text = own ? question + " — " + own : question;
        });
      }
    }
    return pairs
      .filter(function (_pair, i) { return !drop.has(i); })
      .map(function (pair) { return pair.desc; });
  }

  function serialize() {
    const els = document.querySelectorAll(FIELD_SELECTOR);
    const pairs = Array.from(els).map(function (el) {
      return { el: el, desc: describe(el) };
    });
    return groupControls(pairs);
  }

  function elementByIdx(jeIdx) {
    return document.querySelector(`[data-je-idx="${jeIdx}"]`);
  }

  return { serialize, elementByIdx, docToken };
})();
