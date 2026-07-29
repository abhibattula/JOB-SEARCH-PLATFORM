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
  // 018 (D1): no host of its own — rendering belongs to window.jePanel.
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

  // 018 (FR-006): an orphaned frame tears down instead of throwing on every
  // tick. When the extension is reloaded or updated, this content script's
  // context is invalidated and every sendMessage throws — the old code
  // swallowed that and kept polling forever behind a widget whose controls
  // could no longer reach the app. Take the widget down; a fresh content
  // script is already running in its place.
  let orphaned = false;

  function toApp(payload) {
    if (orphaned) { return; }
    try { chrome.runtime.sendMessage({ _je: true, payload }); }
    catch (_e) { teardown(); }
  }

  function teardown() {
    orphaned = true;
    clearInterval(pollTimer);
    clearTimeout(startTimer);
    if (window.jePanel) { window.jePanel.hide(); }
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

  // ---------- rendering: delegated to the ONE companion widget ----------
  //
  // 018 (D1): this script no longer owns a host. It kept all of its detection
  // and scoring logic — that part was never the problem — and now feeds
  // window.jePanel, so the match score and the fill progress share one card
  // instead of sitting in two disconnected widgets in two corners.

  function removeBadge() {
    if (window.jePanel) { window.jePanel.hide(); }
  }

  // FR-005: render on ANY qualifying page — a scored posting, a bare
  // application form, or both. The score block appears once a score exists;
  // the primary action's label follows what we actually found.
  function render() {
    if (dismissedFor === location.href || !window.jePanel) { return; }
    window.jePanel.setPosting(current);
    window.jePanel.setDetection(detection, formFields);
  }

  function renderScore(r) {
    if (dismissedFor === location.href || !window.jePanel) { return; }
    render();
    let sponsorText = "H-1B: unknown", sponsorClass = "chip";
    if (r.sponsor_grade) {
      sponsorText = "H-1B sponsor: " + r.sponsor_grade;
      sponsorClass = "chip grade";
    } else if (r.cap_exempt) {
      sponsorText = "Cap-exempt likely";
      sponsorClass = "chip exempt";
    }
    window.jePanel.setScore({
      score: r.needs_resume ? null : Math.round(r.match_score),
      band: r.band || "fair",
      needs_resume: !!r.needs_resume,
      sponsorText: sponsorText,
      sponsorClass: sponsorClass,
      sponsorKey: r.sponsor_grade || (r.cap_exempt ? "cap-exempt" : "unknown"),
    });
    if (r.needs_resume) {
      window.jePanel.notice("Add your resume in Job Engine to see your match.");
    }
    setSaved(!!r.already_saved);
  }

  function setSaved(saved) {
    if (window.jePanel) { window.jePanel.setSaved(saved); }
  }

  // 017 (FR-038/FR-039) / 018 (R2): start Apply Assist for whatever this page
  // is. Sends a MESSAGE to the local app — it clicks nothing on the page and
  // mutates nothing, exactly as the badge has always behaved.
  //
  // 018: the apply action was a DEAD BUTTON for the whole of v1.7.0. It began
  //
  //     const p = current && current.posting;
  //     if (!p) { return; }
  //
  // but `requestScore` sets `current = { ...p, url }` — keys title, company,
  // description, location, url. There is no `posting` key, so `p` was always
  // undefined and the handler returned before sending anything. The applicant
  // clicked "Apply with Apply Assist" and nothing whatsoever happened. It
  // passed CI because the only coverage was `assert "apply_here" in source`.
  function onAction(action) {
    if (action === "apply" && current) {
      startSession({ type: "apply_here", url: current.url,
                     title: current.title || "", company: current.company || "",
                     description: (current.description || "").slice(0, DESC_MAX) });
    } else if (action === "fill_here") {
      // No posting to record — fill the page the applicant is already on.
      startSession({ type: "fill_here", url: location.href,
                     title: document.title || "" });
    } else if (action === "stop") {
      // 018 (FR-030): stopping a run no longer means abandoning the
      // application you are filling to go and find the app window.
      toApp({ type: "session_control", action: "stop" });
      window.jePanel.setSession("stopped");
      window.jePanel.notice("Stopped. Nothing was submitted.");
    } else if (action === "next") {
      toApp({ type: "session_control", action: "next" });
      window.jePanel.notice("Moving to the next job…");
    } else if (action === "fill_again") {
      // 016 (T016) kept working: main.js registers the handler, we route the
      // click to it so there is still only one primary action on screen.
      if (window.jeFillAgainHandler) { window.jeFillAgainHandler(); }
      else { toApp({ type: "fill_again" }); }
    }
  }

  function startSession(payload) {
    window.jePanel.setSession("starting");
    window.jePanel.notice("");
    toApp(payload);
    armOutcome();
  }

  // 018 (FR-010): a control must never appear to have done nothing. The app
  // may refuse (a session is already running) or be unreachable; either way
  // the primary action comes back and says why, rather than sitting on
  // "Starting…" forever.
  function armOutcome() {
    clearTimeout(startTimer);
    startTimer = setTimeout(function () {
      startTimer = null;
      window.jePanel.setSession("idle");
      window.jePanel.notice(
        "Couldn't start — open Job Engine and check Apply Assist.");
    }, 8000);
  }

  function onSessionStarted() {
    clearTimeout(startTimer);
    startTimer = null;
    window.jePanel.setSession("filling");
  }

  function onAppError(message) {
    clearTimeout(startTimer);
    startTimer = null;
    window.jePanel.setSession("idle");
    window.jePanel.notice(
      message || "The app refused that — check Job Engine.");
  }

  if (window.jePanel) {
    window.jePanel.onAction(onAction);
    window.jePanel.onSave(requestSave);
    window.jePanel.onDismiss(function () { dismissedFor = location.href; });
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
    else if (m.type === "unwatch") { window.jePanel.setSession("done"); }
    // 018 (FR-033): an app-side refusal reaches the page, not just the popup.
    else if (m.type === "app_error") { onAppError(m.message || m.code); }
    // 018 (FR-035): keyboard shortcuts, handled where the widget lives.
    else if (m.type === "toggle_companion") { window.jePanel.toggle(); }
    else if (m.type === "fill_this_page") {
      if (detection !== "none") { onAction(current ? "apply" : "fill_here"); }
    }
  });

  // ---------- lifecycle: detect on load + in-place (SPA) navigation ----------

  let lastHref = location.href;
  let pollTimer = null;
  function tick() {
    if (orphaned) { return; }
    if (location.href !== lastHref) {   // SPA nav → new posting, reset dismiss
      lastHref = location.href;
      dismissedFor = null;
      scoredFor = null;                 // 016: new page state → new score
      lastRequestAt = 0;
      // A new posting is a new session context — a finished fill on the
      // previous page must not leave "Fill again" pointing at this one.
      if (window.jePanel) { window.jePanel.setSession("idle"); }
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
  pollTimer = setInterval(tick, POLL_MS);
  // first pass after the page settles
  if (document.readyState === "complete") { tick(); }
  else { window.addEventListener("load", tick, { once: true }); }
})();
