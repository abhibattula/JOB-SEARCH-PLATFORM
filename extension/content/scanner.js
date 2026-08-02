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
    // 020 (FR-016): rich-text editors. A cover letter written in one of these
    // used to be invisible — not filled, not counted, not flagged, no reason
    // shown. `contenteditable=false` is display, not input, so only the
    // editable forms are matched here and aria-readonly is filtered below.
    '[contenteditable=""]',
    '[contenteditable="true"]',
    "[role=textbox]",
  ].join(",");

  // 020: an editable region is not a form control — no .value, no .labels,
  // no .name. Everything downstream keys off this one predicate.
  function isRichText(el) {
    const editable = el.getAttribute && el.getAttribute("contenteditable");
    const role = (el.getAttribute && el.getAttribute("role") || "").toLowerCase();
    if (editable === "false") { return false; }
    if (editable === "" || editable === "true") { return true; }
    // role=textbox on a real <input>/<textarea> is just an ARIA restatement
    const tag = el.tagName.toLowerCase();
    return role === "textbox" && tag !== "input" && tag !== "textarea";
  }

  function isRichTextWritable(el) {
    if ((el.getAttribute("aria-readonly") || "").toLowerCase() === "true") {
      return false;
    }
    return (el.getAttribute("contenteditable") || "").toLowerCase() !== "false";
  }

  // 011: widget classification + displayed-value read — byte-parallel with
  // engine/autofill/watcher.py SERIALIZE_JS jeWidget/jeValue.
  function jeWidget(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === "select") { return "native_select"; }
    if (isRichText(el)) { return "richtext"; }
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

  // 019 (T032, FR-010): mirrors engine/autofill/field_core.is_placeholder_value
  // (kept in step by tests/test_extension_assets.py). A control resting on
  // "Select…" DISPLAYS text but the applicant has chosen nothing — reading
  // it back as a real value is why those dropdowns were skipped_existing
  // forever and never filled.
  const _PLACEHOLDER_VALUE =
    /^\s*(?:[-–—•*\s]*)?(?:select|choose|please\s+select|pick|--+|—+|none|n\/?a)\b/i;

  function isPlaceholderValue(text) {
    const value = (text || "").trim();
    if (!value) { return true; }
    return _PLACEHOLDER_VALUE.test(value);
  }

  function jeValue(el, widget) {
    const type = el.type || "";
    if (type === "checkbox" || type === "radio") {
      return el.checked ? "on" : "";
    }
    if (widget === "richtext") {
      // 020: no .value on an editable region. Editors also render their own
      // placeholder as a CHILD node, so a naive innerText read sees "Tell us
      // why…" and concludes the box is already answered — the 019
      // placeholder trap in a new place.
      const ph = el.querySelector && el.querySelector("[data-placeholder]");
      let text = (el.innerText || el.textContent || "").trim();
      if (ph) {
        const phText = (ph.innerText || ph.textContent || "").trim();
        if (phText && text.indexOf(phText) === 0) {
          text = text.slice(phText.length).trim();
        }
      }
      return isPlaceholderValue(text) ? "" : text;
    }
    if (widget === "native_select") {
      if (!el.value) { return ""; }
      const text = (el.options[el.selectedIndex] || {}).text || "";
      return isPlaceholderValue(text) ? "" : text;
    }
    if (widget === "custom_combobox" || widget === "typeahead") {
      const sv = el.querySelector &&
        el.querySelector('[class*=singleValue],[class*="-value"]');
      if (sv) { return isPlaceholderValue(sv.textContent) ? ""
                                                         : sv.textContent.trim(); }
      if (el.value) { return isPlaceholderValue(el.value) ? "" : el.value; }
      const t = (el.textContent || "").trim();
      return isPlaceholderValue(t) ? "" : t;
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

  // 019 (T026, FR-007): the full labelling ladder. This read only
  // `el.labels[0]` then `aria-label`, so a field labelled by REFERENCE
  // (aria-labelledby — the Workday/React standard) carried no question at
  // all, and a div[role=combobox] never has `.labels`. Byte-parallel with
  // watcher.py SERIALIZE_JS.
  function referencedText(el) {
    const ids = el.getAttribute && el.getAttribute("aria-labelledby");
    if (!ids) { return ""; }
    const root = el.getRootNode ? el.getRootNode() : document;
    const parts = ids.split(/\s+/).map(function (id) {
      const node = (root.getElementById && root.getElementById(id))
        || document.getElementById(id);
      return node ? (node.innerText || node.textContent || "").trim() : "";
    }).filter(Boolean);
    return parts.join(" ");
  }

  function nearbyLabel(el) {
    const wrapping = el.closest && el.closest("label");
    if (wrapping) {
      const text = stripControls(wrapping);
      if (text) { return text; }
    }
    let prev = el.previousElementSibling;
    let hops = 0;
    while (prev && hops < 3) {
      const tag = prev.tagName.toLowerCase();
      if (tag === "label" || /^h[1-6]$/.test(tag) || tag === "legend") {
        const text = (prev.innerText || prev.textContent || "").trim();
        if (text) { return text; }
      }
      prev = prev.previousElementSibling;
      hops += 1;
    }
    return "";
  }

  function stripControls(node) {
    const clone = node.cloneNode(true);
    Array.prototype.forEach.call(
      clone.querySelectorAll("input,select,textarea,button"),
      function (child) { child.remove(); });
    return (clone.innerText || clone.textContent || "").trim();
  }

  function labelText(el) {
    if (el.labels && el.labels[0]) {
      const label = el.labels[0];
      // A WRAPPING label's innerText includes the control's own rendered
      // text — for a <select> that is the selected option. Reading it raw
      // made the question change the moment the answer did ("Authorized to
      // work? Yes"), which is both wrong in the panel and enough to keep a
      // step looking like it was still changing, forever.
      const text = label.contains(el) ? stripControls(label)
                                      : (label.innerText || "").trim();
      if (text) { return text; }
    }
    const aria = el.getAttribute("aria-label");
    if (aria) { return aria; }
    const referenced = referencedText(el);
    if (referenced) { return referenced; }
    return nearbyLabel(el);
  }

  // 019 (T028, FR-008): every lookup in this file used
  // `document.querySelectorAll`, which never enters a shadow root — so a
  // form inside one was invisible to the scan AND to the probe, and no
  // widget rendered at all. Open roots only; closed roots stay private by
  // design. Depth-capped so a pathological page cannot hang the scan.
  const _MAX_SHADOW_DEPTH = 10;

  function deepQueryAll(selector, root, depth) {
    const scope = root || document;
    const out = Array.prototype.slice.call(scope.querySelectorAll(selector));
    const level = depth || 0;
    if (level >= _MAX_SHADOW_DEPTH) { return out; }
    const all = scope.querySelectorAll("*");
    Array.prototype.forEach.call(all, function (el) {
      if (el.shadowRoot) {
        Array.prototype.push.apply(
          out, deepQueryAll(selector, el.shadowRoot, level + 1));
      }
    });
    return out;
  }

  // 019 (T034, FR-011): `offsetParent` is null for an element that is
  // ITSELF position:fixed — modal-dialog fields were reported invisible and
  // silently ignored — while `visibility:hidden` elements have a non-null
  // offsetParent and were counted visible. Judge by what the user can
  // actually see: a real box, not hidden, not collapsed.
  function isVisible(el) {
    const type = (el.type || "").toLowerCase();
    if (type === "file") { return true; }  // often deliberately off-screen
    const rect = el.getClientRects && el.getClientRects()[0];
    if (!rect || rect.width <= 0 || rect.height <= 0) { return false; }
    // `left:-9999px` is the oldest hide-it-anyway idiom on the web, and it
    // has a real box, so a rect test alone calls it visible. A field parked
    // entirely off the left/top of the document is not something the
    // applicant can see or answer — counting it costs a drafter call and
    // stalls anything waiting for the page to be complete. Below the fold
    // is NOT this: that field is visible, just scrolled.
    if (rect.right <= 0 || rect.bottom <= 0) { return false; }
    const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    if (style && (style.visibility === "hidden" ||
                  style.visibility === "collapse" ||
                  style.display === "none")) {
      return false;
    }
    return true;
  }

  function describe(el) {
    const widget = jeWidget(el);
    // 020: an editable region has no el.type, so it reports "richtext" —
    // the one token the classifier and the filler both key off.
    const type = widget === "richtext" ? "richtext" : (el.type || "");
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
      visible: isVisible(el),
      // 019 (FR-014): additive — old app versions ignore it.
      form_context: formContext(el),
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
  // 017 (C6): a React-select style dropdown is captured TWICE — the
  // div.select__control wrapper AND the search <input> nested inside it. The
  // inner input carries no role and no aria-autocomplete, so jeWidget scored
  // it "" and it became a plain text field with options: [] — while still
  // owning the <label for=...>, so it inherited the question. That is how a
  // 450-character acknowledgement got a multi-sentence answer typed into a
  // yes/no dropdown. The wrapper is the field; its search box is part of the
  // widget, and fillCombobox already drives it through the wrapper.
  function isChoiceWidget(el) {
    const role = (el.getAttribute("role") || "").toLowerCase();
    return role === "combobox" || role === "listbox" ||
      el.getAttribute("aria-haspopup") === "listbox" ||
      /select__control/.test(el.className || "");
  }

  function choiceAncestor(el) {
    let node = el.parentElement;
    while (node) {
      if (isChoiceWidget(node)) { return node; }
      node = node.parentElement;
    }
    return null;
  }

  function dropNestedChoiceControls(pairs) {
    const captured = new Set(pairs.map(function (p) { return p.el; }));
    return pairs.filter(function (pair) {
      const ancestor = choiceAncestor(pair.el);
      if (!ancestor) { return true; }
      // The wrapper is captured too: it is the field, drop this one.
      if (captured.has(ancestor)) { return false; }
      // Nested in a widget we did not capture — keep it, but judge it as the
      // choice control it really is.
      pair.desc.nested_in_choice = true;
      if (!pair.desc.widget) { pair.desc.widget = "custom_combobox"; }
      return true;
    });
  }

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
    // 017 (C8): merge a checkbox set that shares one group question into ONE
    // logical field. 016 deliberately left them separate, so the Akuna
    // pronoun group became five independent essay questions and each got its
    // own paragraph. Multi-select is preserved: `options` lists every member
    // and the app emits one ordinary kind:"checkbox" fill per member it
    // wants ticked, so no new wire kind and no version gate.
    for (const idxs of checks.values()) {
      if (idxs.length < 2) { continue; }
      const question = groupQuestion(pairs[idxs[0]].el);
      if (!question) { continue; }  // no shared question: leave them alone
      const members = idxs.map(function (i) {
        return { je_idx: pairs[i].desc.je_idx,
                 label: pairs[i].desc.label_text || pairs[i].el.value || "" };
      });
      const first = pairs[idxs[0]];
      const checkedLabels = idxs
        .filter(function (i) { return pairs[i].el.checked; })
        .map(function (i) {
          return pairs[i].desc.label_text || pairs[i].el.value || "";
        });
      first.desc = Object.assign({}, first.desc, {
        type: "checkbox_group",
        label_text: question,
        options: members.map(function (m) { return m.label; }),
        members: members,
        value: checkedLabels.join(", "),
        focused: idxs.some(function (i) { return pairs[i].desc.focused; }),
        visible: idxs.some(function (i) { return pairs[i].desc.visible; }),
        required: idxs.some(function (i) { return pairs[i].desc.required; }),
      });
      idxs.slice(1).forEach(function (i) { drop.add(i); });
    }
    return pairs
      .filter(function (_pair, i) { return !drop.has(i); })
      .map(function (pair) { return pair.desc; });
  }

  function serialize() {
    const els = deepQueryAll(FIELD_SELECTOR).filter(function (el) {
      // 020: readonly editors are never fields — filtered here as well as in
      // probe() so the two never disagree about what is on the page.
      return !isRichText(el) || isRichTextWritable(el);
    });
    const pairs = els.map(function (el) {
      return { el: el, desc: describe(el) };
    });
    return groupControls(dropNestedChoiceControls(pairs));
  }

  function elementByIdx(jeIdx) {
    const found = deepQueryAll(`[data-je-idx="${jeIdx}"]`);
    return found.length ? found[0] : null;
  }

  // 018 (R7, FR-005): a READ-ONLY answer to "does this page have an
  // application form on it?".
  //
  // It must NOT be `serialize()`. That function stamps: `stamp()` writes
  // data-je-idx onto every field and `docToken()` writes data-je-doc onto
  // <html>. Calling it merely to decide whether to render a widget would
  // mutate every page the applicant browses, before they have asked for
  // anything — breaking the read-only guarantee the discovery path has held
  // since 012. So this walks the same selector and counts, and touches
  // nothing.
  //
  // The heuristic is deliberately conservative: a false positive puts a
  // widget on every page with a search box, which is worse than the bug it
  // fixes. Exclusions, in order:
  //   1. every field inside a form containing a password — a credential form
  //      is not an application, and we never fill credentials. This one is
  //      load-bearing: dropping the password field alone still leaves
  //      `username`, which together with a newsletter email reaches three
  //      controls on an entirely ordinary page.
  //   2. type=search and type=password
  //   3. name/id that looks like a site search box
  const _SEARCHY_NAME = /^(q|s|search|query|keyword)$/i;
  const _TEXTISH = ["text", "email", "tel", "url", "number", ""];

  function inCredentialForm(el) {
    const form = el.closest && el.closest("form");
    return !!(form && form.querySelector("input[type=password]"));
  }

  // 019 (T044, FR-014): a credential wall is now a FIRST-CLASS state, not a
  // page to hide on. The application-form counts still exclude credential
  // fields (a login box plus a newsletter email is not an application), but
  // the wall itself is reported so the companion can offer to sign in — the
  // page where the applicant most needed it used to show nothing at all.
  //
  // 019 (FR-028): a bot check is reported the same way and always pauses to
  // the human. Detection reads the frame's src attribute; nothing is ever
  // clicked, focused, or read from inside it.
  const _CAPTCHA_SRC = /recaptcha|hcaptcha|challenges\.cloudflare\.com|turnstile|funcaptcha|arkoselabs/i;

  function captchaPresent() {
    const frames = deepQueryAll("iframe");
    for (let i = 0; i < frames.length; i += 1) {
      const src = frames[i].getAttribute("src") || "";
      if (_CAPTCHA_SRC.test(src)) { return true; }
    }
    return !!(document.querySelector(".g-recaptcha, .h-captcha, .cf-turnstile"));
  }

  function credentialWall() {
    const passwords = deepQueryAll("input[type=password]").filter(isVisible);
    if (!passwords.length) { return null; }
    // Two password boxes (or an explicit new-password) means the applicant
    // is CREATING the account, which is a different offer: we prepare the
    // form, they press Create account.
    const newPassword = passwords.some(function (el) {
      return (el.getAttribute("autocomplete") || "") === "new-password";
    });
    return {
      kind: passwords.length > 1 || newPassword ? "registration" : "login",
      domain: location.hostname,
    };
  }

  function probe() {
    const els = deepQueryAll(FIELD_SELECTOR);
    let fields = 0, textish = 0, hasFile = false;
    Array.prototype.forEach.call(els, function (el) {
      const type = (el.type || "").toLowerCase();
      const rich = isRichText(el);
      // 020: a rich-text editor that cannot be written is display, not input
      if (rich && !isRichTextWritable(el)) { return; }
      if (!isVisible(el)) { return; }
      if (type === "search" || type === "password") { return; }
      if (_SEARCHY_NAME.test(el.name || "") ||
          _SEARCHY_NAME.test(el.id || "")) { return; }
      if (inCredentialForm(el)) { return; }
      fields += 1;
      if (type === "file") { hasFile = true; }
      const tag = el.tagName.toLowerCase();
      // 020 (guarantee S2): rich text is text-ish, so a form whose only long
      // answer is a rich-text cover letter still clears the two-text floor.
      if (rich || tag === "textarea" ||
          (tag === "input" && _TEXTISH.indexOf(type) !== -1)) {
        textish += 1;
      }
    });
    const wall = credentialWall();
    return { fields: fields, textish: textish, hasFile: hasFile,
             wall: wall ? wall.kind : "", domain: wall ? wall.domain : "",
             captcha: captchaPresent() };
  }

  // A form worth offering to fill. Two text-ish fields is the floor: it keeps
  // a newsletter box plus a cookie checkbox below the bar while admitting a
  // minimal name/email/resume application.
  function looksLikeApplicationForm(p) {
    if (!p || p.textish < 2) { return false; }
    return p.fields >= 3 || (p.hasFile && p.fields >= 2);
  }

  // 019 (T042, FR-014): which kind of credential form this field sits in —
  // the signal that finally makes login_email/login_username reachable. It
  // is computed from the FORM the serializer can see, which is exactly why
  // it has to live here and not in the classifier.
  function formContext(el) {
    const form = el.closest && el.closest("form");
    const scope = form || document;
    const passwords = (form
      ? Array.prototype.slice.call(form.querySelectorAll("input[type=password]"))
      : deepQueryAll("input[type=password]")).filter(isVisible);
    if (!passwords.length) { return ""; }
    const newPassword = passwords.some(function (p) {
      return (p.getAttribute("autocomplete") || "") === "new-password";
    });
    if (passwords.length > 1 || newPassword) { return "registration"; }
    const text = ((scope.innerText || scope.textContent || "")
      .slice(0, 400)).toLowerCase();
    if (/create (an )?account|sign up|register/.test(text)
        && !/sign in|log in/.test(text)) {
      return "registration";
    }
    return "login";
  }

  // 020: richTextValue mirrors jeValue's richtext branch so the filler reads
  // an editor exactly the way the scan does — one placeholder rule, one
  // reader, no chance of the two disagreeing about whether a cover letter is
  // already answered.
  function richTextValue(el) {
    return jeValue(el, "richtext");
  }

  return { serialize, elementByIdx, docToken, probe, looksLikeApplicationForm,
           deepQueryAll, isVisible, isPlaceholderValue, formContext,
           captchaPresent, credentialWall, isRichText, richTextValue };
})();
