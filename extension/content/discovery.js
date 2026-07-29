// 012 Discovery Copilot — the browse-time badge.
//
// READ-ONLY on the page: this script only READS visible job metadata and
// renders its OWN shadow-DOM badge. It never clicks, types into, submits, or
// mutates any page element. Detection: schema.org JobPosting JSON-LD (primary,
// site-agnostic) + LinkedIn/Indeed DOM extractors (by specific selectors, so
// they also work behind proxies/subdomains). Scoring happens in the local app
// over the companion bridge; the badge renders only when a score comes back.
//
// Runs top-frame only. Independent of Apply Assist's fill flow.
"use strict";

(function () {
  if (window !== window.top) { return; }

  const DESC_MAX = 20000;
  const POLL_MS = 1500;
  // Host affinity is a hint only — detection is by selector so fixtures/proxies
  // still resolve. LinkedIn: linkedin.com/jobs/view; Indeed: indeed.* /viewjob.
  const LINKEDIN_HOST = /(^|\.)linkedin\.com$/i;
  const INDEED_HOST = /(^|\.)indeed\.[a-z.]+$/i;

  let current = null;       // last detected posting {title,company,description,location}
  let dismissedFor = null;  // href the user dismissed the badge for
  let host = null, root = null, els = {}, collapsed = false;
  // 018 (R7): what this page is. `posting` comes from job metadata, `form`
  // from the read-only field probe. Either one is enough to show the widget —
  // through v1.7.0 only the first was, so a bare ATS application page (which
  // routinely carries no metadata at all) showed nothing.
  let detection = "none";   // none | form | posting | posting+form
  let formFields = 0;
  let startTimer = null;    // outcome watchdog for the primary action

  // ---------- detection (read-only) ----------

  function stripTags(s) {
    if (!s) { return ""; }
    const d = document.createElement("div");   // detached; never inserted
    d.innerHTML = String(s);
    return (d.textContent || "").replace(/\s+/g, " ").trim();
  }

  function orgName(org) {
    if (!org) { return ""; }
    if (typeof org === "string") { return org; }
    if (Array.isArray(org)) { return orgName(org[0]); }
    return org.name || "";
  }

  function locName(loc) {
    if (!loc) { return ""; }
    if (Array.isArray(loc)) { return locName(loc[0]); }
    const a = loc.address || loc;
    if (typeof a === "string") { return a; }
    return [a.addressLocality, a.addressRegion].filter(Boolean).join(", ");
  }

  function fromJsonLd() {
    const scripts = document.querySelectorAll(
      'script[type="application/ld+json"]');
    for (const s of scripts) {
      let data;
      try { data = JSON.parse(s.textContent); } catch (_e) { continue; }
      const nodes = [];
      const push = (x) => { if (x && typeof x === "object") { nodes.push(x); } };
      if (Array.isArray(data)) { data.forEach(push); }
      else { push(data); if (Array.isArray(data["@graph"])) { data["@graph"].forEach(push); } }
      for (const n of nodes) {
        const t = n["@type"];
        const isJob = t === "JobPosting"
          || (Array.isArray(t) && t.includes("JobPosting"));
        if (!isJob) { continue; }
        const title = stripTags(n.title);
        if (!title) { continue; }
        return {
          title,
          company: stripTags(orgName(n.hiringOrganization)),
          description: stripTags(n.description),
          location: locName(n.jobLocation),
        };
      }
    }
    return null;
  }

  function firstText(selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent && el.textContent.trim()) {
        return el.textContent.replace(/\s+/g, " ").trim();
      }
    }
    return "";
  }

  function fromLinkedIn() {
    const title = firstText([
      ".job-details-jobs-unified-top-card__job-title",
      ".top-card-layout__title",
      ".topcard__title",
    ]);
    if (!title) { return null; }
    return {
      title,
      company: firstText([
        ".job-details-jobs-unified-top-card__company-name a",
        ".job-details-jobs-unified-top-card__company-name",
        ".topcard__org-name-link",
        ".topcard__flavor--black-link",
      ]),
      description: (firstText([".jobs-description__content", ".description__text"])
        || "").slice(0, DESC_MAX),
      location: firstText([".job-details-jobs-unified-top-card__bullet",
        ".topcard__flavor--bullet"]),
    };
  }

  function fromIndeed() {
    const title = firstText([
      "h1.jobsearch-JobInfoHeader-title",
      ".jobsearch-JobInfoHeader-title",
      '[data-testid="jobsearch-JobInfoHeader-title"]',
    ]);
    if (!title) { return null; }
    return {
      title,
      company: firstText([
        '[data-testid="inlineHeader-companyName"]',
        '[data-company-name="true"]',
        ".jobsearch-CompanyInfoContainer a",
      ]),
      description: (firstText(["#jobDescriptionText"]) || "").slice(0, DESC_MAX),
      location: firstText(['[data-testid="inlineHeader-companyLocation"]',
        '[data-testid="jobsearch-JobInfoHeader-companyLocation"]']),
    };
  }

  function detect() {
    let p = fromJsonLd();
    if (!p) { p = fromLinkedIn(); }
    if (!p) { p = fromIndeed(); }
    return (p && p.title) ? p : null;
  }

  // ---------- bridge ----------

  function toApp(payload) {
    try { chrome.runtime.sendMessage({ _je: true, payload }); }
    catch (_e) { /* extension reloaded — orphaned frame */ }
  }

  // 016 (T009, R5): score ONCE per page state — but cache only when a
  // RESULT arrives (a request that races a cold socket would otherwise
  // leave the page permanently badgeless; caught by the Windows CI
  // runner). Until a result lands, retry slowly (7.5 s), never the old
  // 1.5 s flood that head-of-line blocked the fill path (RC1 evidence).
  let scoredFor = null;      // href whose score RESULT arrived
  let lastRequestAt = 0;     // pending-request backoff
  const RETRY_MS = 7500;

  function requestScore() {
    if (!current) { return; }
    if (scoredFor === location.href) { return; }  // result cached — done
    if (Date.now() - lastRequestAt < RETRY_MS) { return; }  // one in flight
    lastRequestAt = Date.now();
    toApp({
      type: "score_request", url: current.url, title: current.title,
      company: current.company,
      description: (current.description || "").slice(0, DESC_MAX),
    });
  }

  // 018 (R7): read-only page classification. `detect()` reads metadata the
  // applicant is already looking at; `probe()` counts form fields without
  // stamping anything. Neither sends anything anywhere — the result decides
  // local rendering only.
  function classify() {
    const p = detect();
    current = p ? { ...p, url: location.href } : null;
    let form = null;
    try {
      form = window.jeScanner ? window.jeScanner.probe() : null;
    } catch (_e) { form = null; }
    const hasForm = !!(form && window.jeScanner
                       && window.jeScanner.looksLikeApplicationForm(form));
    formFields = form ? form.fields : 0;
    detection = current ? (hasForm ? "posting+form" : "posting")
      : (hasForm ? "form" : "none");
    return detection;
  }

  function requestSave() {
    if (!current) { return; }
    toApp({
      type: "save_job", url: current.url, title: current.title,
      company: current.company,
      description: (current.description || "").slice(0, DESC_MAX),
      location: current.location || "",
    });
  }

  // ---------- badge (our own DOM only) ----------

  // 018 (R1): pin the host to the VIEWPORT — and keep it pinned.
  //
  // Every version since v1.0.0 did this:
  //
  //   host.style.cssText = "position:fixed;…;bottom:16px;all:initial;"
  //
  // `all` is a shorthand for EVERY CSS property, and it was declared LAST, so
  // it reset `position` straight back to `static`, `inset` to `auto`,
  // `z-index` to `auto` and `display` to `inline`. The host is appended as the
  // last child of <body>, so a static host renders at the END of the document
  // flow — the bottom of the page. Measured on the 5000px test fixture, the
  // badge sat at y=5181. That is the whole of "the extension is going to
  // bottom of the page where i cannot see".
  //
  // So: reset FIRST, then position. And position with `!important`, because a
  // plain inline declaration sits in the author-normal cascade layer and loses
  // to a page rule like `div { position: static !important }` — which the
  // hostile-CSS fixture ships precisely because real reset stylesheets do.
  function pinToViewport(el, zIndex) {
    el.style.cssText = "all:initial";
    el.style.setProperty("position", "fixed", "important");
    el.style.setProperty("inset", "auto 16px 16px auto", "important");
    el.style.setProperty("z-index", zIndex, "important");
    el.style.setProperty("display", "block", "important");
  }

  function build() {
    if (host) { return; }
    host = document.createElement("div");
    host.id = "je-discovery-badge-host";
    pinToViewport(host, "2147483646");
    // open root: CSS is still fully isolated by shadow DOM; open lets the
    // integration test drive the Save button (a closed root is unreachable).
    root = host.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        *{box-sizing:border-box}
        .card{font:13px/1.4 system-ui,-apple-system,sans-serif;width:264px;
          background:#0d1117;color:#e6edf3;border:1px solid #30363d;
          border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.45);overflow:hidden}
        .hd{display:flex;align-items:center;gap:8px;padding:9px 11px;
          background:#161b22;border-bottom:1px solid #30363d}
        .hd .tag{font-weight:700;letter-spacing:.2px}
        .hd .sp{flex:1}
        .icon{cursor:pointer;color:#8b949e;font-size:14px;line-height:1;
          padding:2px 4px;border-radius:4px;user-select:none}
        .icon:hover{background:#21262d;color:#e6edf3}
        .bd{padding:11px}
        .co{color:#8b949e;font-size:12px;white-space:nowrap;overflow:hidden;
          text-overflow:ellipsis}
        .ti{font-weight:600;margin:1px 0 9px;white-space:nowrap;overflow:hidden;
          text-overflow:ellipsis}
        .row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
        .score{width:46px;height:46px;border-radius:50%;display:flex;
          align-items:center;justify-content:center;font-weight:700;font-size:16px;
          border:2px solid #30363d;flex:none}
        .score.strong{color:#3fb950;border-color:#238636}
        .score.good{color:#d29922;border-color:#9e6a03}
        .score.fair{color:#8b949e}
        .score.none{font-size:11px;font-weight:600;color:#8b949e}
        .meta{min-width:0}
        .band{font-weight:600;text-transform:capitalize}
        .band.strong{color:#3fb950}.band.good{color:#d29922}.band.fair{color:#8b949e}
        .pill{display:inline-block;margin-top:2px;padding:1px 7px;border-radius:999px;
          font-size:11px;font-weight:600;background:#21262d;color:#8b949e}
        .pill.grade{background:#132a17;color:#3fb950}
        .pill.exempt{background:#132033;color:#58a6ff}
        button.save{width:100%;padding:8px;border:0;border-radius:8px;
          background:#238636;color:#fff;font-weight:600;font-size:13px;cursor:pointer}
        button.save:hover{background:#2ea043}
        button.save[disabled]{background:#21262d;color:#8b949e;cursor:default}
        .note{color:#8b949e;font-size:11px;margin-top:7px}
        .formnote{color:#8b949e;font-size:12px;margin-bottom:9px}
        .collapsed .bd{display:none}
        .collapsed .card{width:auto}
      </style>
      <div class="card" id="card">
        <div class="hd">
          <span class="tag">Job Engine</span><span class="sp"></span>
          <span class="icon" id="collapse" title="Collapse">▁</span>
          <span class="icon" id="dismiss" title="Dismiss">✕</span>
        </div>
        <div class="bd">
          <div class="co" id="co"></div>
          <div class="ti" id="ti"></div>
          <div class="row" id="scorerow">
            <div class="score" id="score">–</div>
            <div class="meta">
              <div class="band" id="band"></div>
              <span class="pill" id="sponsor">H-1B: unknown</span>
            </div>
          </div>
          <div class="formnote" id="formnote" style="display:none"></div>
          <button class="save" id="apply">Apply with Apply Assist</button>
          <button class="save ghost" id="save">Save to Job Engine</button>
          <div class="note" id="note" style="display:none"></div>
        </div>
      </div>`;
    els = {
      card: root.getElementById("card"), co: root.getElementById("co"),
      ti: root.getElementById("ti"), score: root.getElementById("score"),
      band: root.getElementById("band"), sponsor: root.getElementById("sponsor"),
      save: root.getElementById("save"), note: root.getElementById("note"),
      apply: root.getElementById("apply"),
      scorerow: root.getElementById("scorerow"),
      formnote: root.getElementById("formnote"),
    };
    root.getElementById("dismiss").addEventListener("click", onDismiss);
    root.getElementById("collapse").addEventListener("click", onCollapse);
    els.save.addEventListener("click", onSave);
    els.apply.addEventListener("click", onApply);
    (document.body || document.documentElement).appendChild(host);
  }

  function removeBadge() {
    if (host) { host.remove(); host = null; root = null; els = {}; collapsed = false; }
  }

  // 018 (FR-005): render on ANY qualifying page — a scored posting, a bare
  // application form, or both. The score block only appears once a score
  // exists; the primary action's label follows what we actually found.
  function render() {
    if (dismissedFor === location.href) { return; }
    build();
    els.co.textContent = current ? (current.company || "—") : "";
    els.ti.textContent = current ? current.title : (document.title || "");
    host.dataset.jeCompany = current ? (current.company || "") : "";
    host.dataset.jeDetection = detection;

    const posting = !!current;
    // Nothing to save when there is no posting to identify.
    els.save.style.display = posting ? "" : "none";
    els.scorerow.style.display = (posting && scoredFor === location.href)
      ? "" : "none";
    if (!posting) {
      els.formnote.textContent = "Application form found — " + formFields +
        " field" + (formFields === 1 ? "" : "s") + ".";
      els.formnote.style.display = "";
    } else {
      els.formnote.style.display = "none";
    }
    if (!els.apply.disabled) { els.apply.textContent = primaryLabel(); }
  }

  function primaryLabel() {
    return current ? "Apply with Apply Assist" : "Fill this page";
  }

  function renderScore(r) {
    if (dismissedFor === location.href) { return; }
    render();
    els.scorerow.style.display = "";

    if (r.needs_resume) {
      els.score.className = "score none";
      els.score.textContent = "—";
      els.band.textContent = "";
      els.note.style.display = "block";
      els.note.textContent = "Add your resume in Job Engine to see your match.";
      host.dataset.jeScore = "";
      host.dataset.jeBand = "none";
    } else {
      const band = r.band || "fair";
      els.score.className = "score " + band;
      els.score.textContent = String(Math.round(r.match_score));
      els.band.className = "band " + band;
      els.band.textContent = band + " match";
      els.note.style.display = "none";
      host.dataset.jeScore = String(Math.round(r.match_score));
      host.dataset.jeBand = band;
    }

    let sp = "H-1B: unknown", cls = "pill";
    if (r.sponsor_grade) { sp = "H-1B sponsor: " + r.sponsor_grade; cls = "pill grade"; }
    else if (r.cap_exempt) { sp = "Cap-exempt likely"; cls = "pill exempt"; }
    els.sponsor.textContent = sp;
    els.sponsor.className = cls;
    host.dataset.jeSponsor = r.sponsor_grade || (r.cap_exempt ? "cap-exempt" : "unknown");

    setSaved(!!r.already_saved);
  }

  function setSaved(saved) {
    if (!els.save) { return; }
    els.save.disabled = saved;
    els.save.textContent = saved ? "Saved ✓" : "Save to Job Engine";
    if (host) { host.dataset.jeSaved = saved ? "1" : "0"; }
  }

  function onSave() { if (els.save && !els.save.disabled) { requestSave(); } }

  // 017 (FR-038/FR-039) / 018 (R2): start Apply Assist for whatever this page
  // is. Sends a MESSAGE to the local app and opens our own panel — it clicks
  // nothing on the page and mutates nothing, exactly as the badge has always
  // behaved.
  //
  // 018: this was a DEAD BUTTON for the whole of v1.7.0. It opened with
  //
  //     const p = current && current.posting;
  //     if (!p) { return; }
  //
  // but `requestScore` sets `current = { ...p, url }` — keys title, company,
  // description, location, url. There is no `posting` key, so `p` was always
  // undefined and the handler returned before sending anything. The applicant
  // clicked "Apply with Apply Assist" and nothing whatsoever happened. It
  // passed CI because the only coverage was `assert "apply_here" in source`.
  function onApply() {
    if (!els.apply || els.apply.disabled) { return; }
    const restore = primaryLabel();
    els.apply.disabled = true;
    els.apply.textContent = "Starting…";
    showNote("");
    if (current) {
      toApp({ type: "apply_here", url: current.url, title: current.title || "",
              company: current.company || "",
              description: (current.description || "").slice(0, DESC_MAX) });
    } else {
      // No posting to record — fill the page the applicant is already on.
      toApp({ type: "fill_here", url: location.href,
              title: document.title || "" });
    }
    armOutcome(restore);
    // Both content scripts share one isolated world, so the fill panel is
    // directly reachable — no second floating widget, per D4.
    if (window.jeOverlay && window.jeOverlay.show) { window.jeOverlay.show(); }
  }

  // 018 (FR-010): a control must never appear to have done nothing. The app
  // may refuse (a session is already running) or be unreachable; either way
  // the button comes back and says why, rather than sitting on "Starting…".
  function armOutcome(restoreLabel) {
    clearTimeout(startTimer);
    startTimer = setTimeout(function () {
      startTimer = null;
      if (!els.apply) { return; }
      els.apply.disabled = false;
      els.apply.textContent = restoreLabel;
      showNote("Couldn't start — open Job Engine and check Apply Assist.");
    }, 8000);
  }

  function onSessionStarted() {
    clearTimeout(startTimer);
    startTimer = null;
    if (host) { host.dataset.jeSession = "filling"; }
    if (els.apply) {
      els.apply.disabled = true;
      els.apply.textContent = "Filling…";
    }
  }

  function onAppError(message) {
    clearTimeout(startTimer);
    startTimer = null;
    if (els.apply) {
      els.apply.disabled = false;
      els.apply.textContent = primaryLabel();
    }
    showNote(message || "The app refused that — check Job Engine.");
  }

  function showNote(text) {
    if (!els.note) { return; }
    els.note.textContent = text || "";
    els.note.style.display = text ? "block" : "none";
  }
  function onDismiss() { dismissedFor = location.href; removeBadge(); }
  function onCollapse() {
    collapsed = !collapsed;
    if (els.card) { els.card.classList.toggle("collapsed", collapsed); }
    if (host) { host.dataset.jeCollapsed = collapsed ? "1" : "0"; }
  }

  // ---------- messages from the app (via the SW) ----------

  chrome.runtime.onMessage.addListener((m) => {
    if (!m || !m.type) { return; }
    if (m.type === "score_result") {
      scoredFor = location.href;  // 016 (T009): NOW the page is scored
      renderScore(m);
    }
    else if (m.type === "save_result") { setSaved(true); }
    // 018 (FR-010): the app confirmed the session — the primary action's
    // watchdog stands down.
    else if (m.type === "watch") { onSessionStarted(); }
    else if (m.type === "unwatch") {
      if (host) { host.dataset.jeSession = "idle"; }
      if (els.apply) {
        els.apply.disabled = false;
        els.apply.textContent = primaryLabel();
      }
    }
    // 018 (FR-033): an app-side refusal reaches the page, not just the popup.
    else if (m.type === "app_error") { onAppError(m.message || m.code); }
  });

  // ---------- lifecycle: detect on load + in-place (SPA) navigation ----------

  let lastHref = location.href;
  function tick() {
    if (location.href !== lastHref) {   // SPA nav → new posting, reset dismiss
      lastHref = location.href;
      dismissedFor = null;
      scoredFor = null;                 // 016: new page state → new score
      lastRequestAt = 0;
      removeBadge();
    }
    // 018: classify FIRST, then decide. A page with no posting metadata but a
    // real application form now qualifies — that is the Greenhouse
    // `…/application` case where the applicant previously saw nothing at all.
    if (classify() === "none") { scoredFor = null; removeBadge(); return; }
    if (dismissedFor === location.href) { return; }
    if (current) { requestScore(); }
    render();
  }
  setInterval(tick, POLL_MS);
  // first pass after the page settles
  if (document.readyState === "complete") { tick(); }
  else { window.addEventListener("load", tick, { once: true }); }
})();
