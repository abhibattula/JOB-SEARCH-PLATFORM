// The companion: ONE floating widget, top frame only.
//
// 017 decided (D4) that the match-score badge and the fill panel should be a
// single thing. The code shipped two: `je-discovery-badge-host` bottom-right
// and `je-companion-overlay-host` top-right, separate shadow roots, no shared
// state, each unaware of the other. 018 merges them here.
//
// Two states:
//   - collapsed: a small pill carrying the one number that matters right now
//     (match score when idle, filled/seen while filling, a count when
//     something needs the applicant)
//   - expanded: the full card — score, one primary action, progress, answers
//
// It rests collapsed and opens on click, and opens ITSELF when a fill starts
// or when a question first needs an answer, so an action is never missed.
//
// SAFETY: this module renders its own shadow DOM and nothing else. It never
// clicks, types into, submits or mutates any element belonging to the page.
// Insert — the one control that writes to a field — is delegated to the
// filler, which the applicant invoked for that one field. Answer and question
// text always goes in via textContent, never innerHTML: it comes from a model
// and from page labels.
//
// Classic script: exposes window.jePanel, plus window.jeOverlay as the 017
// facade main.js already drives.
"use strict";

window.jePanel = (function () {
  const IS_TOP = window === window.top;

  let host = null;
  let root = null;
  let els = {};
  const handlers = {
    action: null, save: null, dismiss: null,
    answer: null, insert: null, jump: null,
    // 019: (identifier, password) -> void — routed to the app, which is the
    // only thing that ever touches the OS keychain.
    credential: null,
  };

  const state = {
    collapsed: true,
    detection: "none",       // none | form | posting | posting+form
    // 019: "" | "login" | "registration" — a credential wall is a state of
    // its own, not a page to hide on.
    wall: "",
    // 019: the app told us there is no saved login for this domain, so the
    // inline save form is the useful thing to show.
    credentialNeeded: false,
    // 019 adds: your_turn_captcha | ready_for_review | paused_cap
    session: "idle",         // idle | starting | filling | stopped | done
    formFields: 0,
    posting: null,
    score: null,
    saved: false,
    counts: { seen: 0, filled: 0, needs_you: 0, drafts: 0 },
    // 016 sent `attention` — up to five bare LABELS of fields needing the
    // applicant. 018's needs-you group carries the same fields with their
    // full question, the reason, and a box to answer them, so the label list
    // is strictly redundant and is no longer stored or rendered.
    remaining: 0,
    currentJobId: null,
    answers: [],
    truncated: false,
    notice: "",
    // Auto-expand fires ONCE per condition. After the applicant collapses the
    // card we do not keep re-opening it at them.
    autoExpanded: { session: false, needs: false },
  };

  // ---------- the primary-action state machine (pure, exported) ----------

  // FR-007: exactly one primary action. Its label and meaning follow the
  // state, so there is never a row of buttons to choose between.
  function primaryFor(session, detection, wall) {
    if (session === "starting") {
      return { action: "", label: "Starting…", disabled: true };
    }
    // 019 (FR-028): a bot check outranks everything. Nothing is clicked on
    // or near it, and the session waits for the human.
    if (session === "your_turn_captcha") {
      return { action: "", label: "Waiting for you", disabled: true };
    }
    // 019 (FR-030): the door. Everything fillable is in; the Submit is the
    // applicant's, and the button never offers to press it.
    if (session === "ready_for_review") {
      return { action: "", label: "Your turn to submit", disabled: true };
    }
    if (session === "paused_cap") {
      return { action: "resume_escort", label: "Continue", disabled: false };
    }
    // `escorting` IS filling — with the escort advancing steps as well.
    // Anything that is not one of the explicit pause states must still
    // offer Stop, or the applicant loses it exactly when they want it.
    if (session === "filling" || session === "escorting") {
      return { action: "stop", label: "Stop", disabled: false };
    }
    if (session === "stopped" || session === "done") {
      return { action: "fill_again", label: "Fill again", disabled: false };
    }
    // 019 (FR-014): a credential wall. Signing in is the only useful thing
    // to offer here — this page used to render nothing at all.
    if (wall === "login") {
      return { action: "fill_here", label: "Sign in with my saved login",
               disabled: false };
    }
    if (wall === "registration") {
      return { action: "fill_here", label: "Prepare my account details",
               disabled: false };
    }
    if (detection === "posting" || detection === "posting+form") {
      return { action: "apply", label: "Apply with Apply Assist",
               disabled: false };
    }
    if (detection === "form") {
      return { action: "fill_here", label: "Fill this page", disabled: false };
    }
    return { action: "", label: "Fill this page", disabled: true };
  }

  // ---------- mounting ----------

  // 018 (R1): reset FIRST, then pin — `all` is a shorthand for every CSS
  // property, so declaring it after `position:fixed` (as every version from
  // v1.0.0 to v1.7.0 did) reset the widget to `position:static` and it
  // rendered at the bottom of the document instead of the corner of the
  // screen. `!important` because a plain inline declaration loses to a page
  // rule like `div { position: static !important }`.
  function pin(el) {
    el.style.cssText = "all:initial";
    el.style.setProperty("position", "fixed", "important");
    el.style.setProperty("inset", "auto 16px 16px auto", "important");
    el.style.setProperty("z-index", "2147483647", "important");
    el.style.setProperty("display", "block", "important");
  }

  const STYLE = `
    *{box-sizing:border-box}
    :host{contain:layout style}
    /* The UA rule for [hidden] is display:none, but an AUTHOR rule such as
       .card{display:flex} outranks it, so el.hidden = true would leave the
       card on screen. Restate it here, in the author layer, where it wins.
       (No backticks in this block: it lives inside a template literal.) */
    [hidden]{display:none!important}
    .pill{display:flex;align-items:center;gap:7px;cursor:pointer;
      font:600 13px/1 system-ui,-apple-system,sans-serif;
      background:#0d1117;color:#e6edf3;border:1px solid #30363d;
      border-radius:999px;padding:9px 14px;
      box-shadow:0 6px 20px rgba(0,0,0,.4)}
    .pill:hover{background:#161b22}
    .pill .mark{width:8px;height:8px;border-radius:50%;background:#3fb950;
      flex:none}
    .pill .mark.idle{background:#8b949e}
    .pill .mark.warn{background:#d29922}
    .card{font:13px/1.45 system-ui,-apple-system,sans-serif;width:340px;
      max-height:calc(100vh - 32px);display:flex;flex-direction:column;
      background:#0d1117;color:#e6edf3;border:1px solid #30363d;
      border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.45);
      overflow:hidden}
    .hd{display:flex;align-items:center;gap:8px;padding:9px 11px;
      background:#161b22;border-bottom:1px solid #30363d;flex:none}
    .hd .tag{font-weight:700;letter-spacing:.2px}
    .hd .sp{flex:1}
    .dot{width:8px;height:8px;border-radius:50%;background:#3fb950;flex:none}
    .dot.idle{background:#8b949e}
    .icon{cursor:pointer;color:#8b949e;font-size:14px;line-height:1;
      padding:3px 5px;border-radius:5px;user-select:none;background:none;
      border:0}
    .icon:hover{background:#21262d;color:#e6edf3}
    .bd{padding:11px;overflow-y:auto;flex:1;min-height:0}
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
    .chip{display:inline-block;margin-top:2px;padding:1px 7px;
      border-radius:999px;font-size:11px;font-weight:600;background:#21262d;
      color:#8b949e}
    .chip.grade{background:#132a17;color:#3fb950}
    .chip.exempt{background:#132033;color:#58a6ff}
    button.act{width:100%;padding:9px;border:0;border-radius:8px;
      background:#238636;color:#fff;font-weight:600;font-size:13px;
      cursor:pointer;margin-bottom:6px}
    button.act:hover{background:#2ea043}
    button.act[disabled]{background:#21262d;color:#8b949e;cursor:default}
    button.act.ghost{background:#21262d;color:#e6edf3;
      border:1px solid #30363d}
    button.act.ghost:hover{background:#30363d}
    button.act.danger{background:#9e2f24}
    button.act.danger:hover{background:#c03a2c}
    .formnote{color:#8b949e;font-size:12px;margin-bottom:9px}
    .wallnote{color:#e6edf3;font-size:12px;margin-bottom:9px;
      background:#161b22;border:1px solid #30363d;border-left:3px solid #58a6ff;
      border-radius:6px;padding:8px 10px}
    .loginform{display:flex;flex-direction:column;gap:6px;margin:8px 0}
    .loginform input{font:13px system-ui,-apple-system,sans-serif;
      background:#0d1117;color:#e6edf3;border:1px solid #30363d;
      border-radius:6px;padding:7px 9px}
    .loginform input:focus-visible{outline:2px solid #58a6ff;outline-offset:1px}
    .credhint{color:#8b949e;font-size:11px;line-height:1.35}
    .prog{display:flex;gap:10px;font-size:12px;color:#8b949e;margin:8px 0 4px;
      flex-wrap:wrap}
    .prog b{color:#e6edf3;font-weight:600}
    .prog .warn b{color:#d29922}
    .notice{margin-top:7px;padding:6px 8px;background:#21262d;
      border-radius:6px;color:#d29922;font-size:12px}
    .foot{padding:8px 11px;border-top:1px solid #30363d;color:#8b949e;
      font-size:11px;flex:none;background:#0d1117}
    .muted{color:#8b949e;font-size:12px}
    /* answer groups */
    .grp{margin-top:9px;border-top:1px solid #21262d;padding-top:7px}
    .grph{width:100%;text-align:left;background:none;border:0;cursor:pointer;
      color:#8b949e;font:600 11px system-ui;text-transform:uppercase;
      letter-spacing:.04em;padding:3px 0}
    .grph:hover{color:#e6edf3}
    .grph[aria-expanded="true"]{color:#e6edf3}
    .grpn{color:#8b949e;font-weight:600}
    .grpb{margin-top:5px}
    .qa{margin:0 0 9px;padding-bottom:7px;border-bottom:1px solid #21262d}
    .qa:last-child{border-bottom:0;margin-bottom:0}
    .q{font-size:12px;color:#c9d1d9;margin-bottom:3px}
    .a{font-size:12px;color:#e6edf3;white-space:pre-wrap;word-break:break-word}
    .a.drafted{color:#a371f7}
    .a.muted{color:#8b949e}
    .acts{display:flex;gap:6px;margin-top:5px}
    .sm{padding:3px 8px;font:11px system-ui;background:#21262d;color:#e6edf3;
      border:1px solid #30363d;border-radius:5px;cursor:pointer}
    .sm:hover{background:#30363d}
    .why{font-size:11px;color:#d29922;margin-top:3px}
    .ask{width:100%;margin-top:4px;padding:5px 7px;font:12px system-ui;
      background:#0d1117;color:#e6edf3;border:1px solid #30363d;
      border-radius:5px}
    .ask:disabled{opacity:.6}
    :focus-visible{outline:2px solid #58a6ff;outline-offset:2px}
    @media (prefers-reduced-motion: reduce){*{transition:none!important}}
  `;

  const MARKUP = `
    <style>${STYLE}</style>
    <div class="pill" id="pill" role="button" tabindex="0"
         aria-label="Open Job Engine companion">
      <span class="mark" id="pill-mark"></span>
      <span id="pill-text">Job Engine</span>
    </div>
    <div class="card" id="card" hidden>
      <div class="hd">
        <span class="dot" id="dot"></span>
        <span class="tag">Job Engine</span><span class="sp"></span>
        <button class="icon" id="collapse" title="Collapse"
                aria-label="Collapse">▁</button>
        <button class="icon" id="dismiss" title="Dismiss"
                aria-label="Dismiss">✕</button>
      </div>
      <div class="bd">
        <div class="co" id="co"></div>
        <div class="ti" id="ti"></div>
        <div class="row" id="scorerow" hidden>
          <div class="score" id="score">–</div>
          <div class="meta">
            <div class="band" id="band"></div>
            <span class="chip" id="sponsor">H-1B: unknown</span>
          </div>
        </div>
        <div class="formnote" id="formnote" hidden></div>
        <div class="wallnote" id="wallnote" hidden></div>
        <button class="act" id="primary">Fill this page</button>
        <!-- 019 (FR-017): saving a login used to mean leaving the wall,
             finding the app, and finding Settings. The password goes
             straight to the OS keychain and is cleared from this form the
             moment it is sent. -->
        <form class="loginform" id="loginform" hidden>
          <input id="cred-id" type="text" autocomplete="off"
                 placeholder="Email or username" aria-label="Email or username">
          <input id="cred-pw" type="password" autocomplete="off"
                 placeholder="Password" aria-label="Password">
          <button class="act ghost" id="cred-save" type="submit">
            Save this login
          </button>
          <div class="credhint">Stored in Windows Credential Manager /
            macOS Keychain — never in the app's database, never shown again.
          </div>
        </form>
        <button class="act ghost" id="next" hidden>Next job</button>
        <button class="act ghost" id="save" hidden>Save to Job Engine</button>
        <div class="prog" id="prog" hidden>
          <span>Filled <b id="p-filled">0</b></span>
          <span class="warn">Needs you <b id="p-needs">0</b></span>
          <span>Seen <b id="p-seen">0</b></span>
        </div>
        <div class="notice" id="notice" hidden role="status"></div>
        <div id="answers"></div>
      </div>
      <div class="foot">You press the final Submit — never us.</div>
    </div>
  `;

  function build() {
    if (host || !IS_TOP) { return !!host; }
    host = document.createElement("div");
    host.id = "je-companion-host";
    pin(host);
    root = host.attachShadow({ mode: "open" });
    root.innerHTML = MARKUP;
    els = {
      pill: root.getElementById("pill"),
      pillMark: root.getElementById("pill-mark"),
      pillText: root.getElementById("pill-text"),
      card: root.getElementById("card"),
      dot: root.getElementById("dot"),
      co: root.getElementById("co"),
      ti: root.getElementById("ti"),
      scorerow: root.getElementById("scorerow"),
      score: root.getElementById("score"),
      band: root.getElementById("band"),
      sponsor: root.getElementById("sponsor"),
      formnote: root.getElementById("formnote"),
      wallnote: root.getElementById("wallnote"),
      loginform: root.getElementById("loginform"),
      credId: root.getElementById("cred-id"),
      credPw: root.getElementById("cred-pw"),
      primary: root.getElementById("primary"),
      next: root.getElementById("next"),
      save: root.getElementById("save"),
      prog: root.getElementById("prog"),
      pFilled: root.getElementById("p-filled"),
      pNeeds: root.getElementById("p-needs"),
      pSeen: root.getElementById("p-seen"),
      notice: root.getElementById("notice"),
      answers: root.getElementById("answers"),
    };
    els.pill.addEventListener("click", function () { setCollapsed(false); });
    els.pill.addEventListener("keydown", function (evt) {
      if (evt.key === "Enter" || evt.key === " ") {
        evt.preventDefault();
        setCollapsed(false);
      }
    });
    root.getElementById("collapse").addEventListener(
      "click", function () { setCollapsed(true); });
    root.getElementById("dismiss").addEventListener("click", onDismiss);
    els.primary.addEventListener("click", onPrimary);
    els.next.addEventListener("click", function () {
      if (handlers.action) { handlers.action("next"); }
    });
    els.save.addEventListener("click", function () {
      if (handlers.save) { handlers.save(); }
    });
    // 019 (FR-017/FR-018): the login goes to the app, which puts it in the
    // OS keychain. The password is cleared from the DOM on the next line —
    // it never sits in a form waiting to be read by anything else.
    els.loginform.addEventListener("submit", function (e) {
      e.preventDefault();
      const identifier = els.credId.value.trim();
      const password = els.credPw.value;
      els.credPw.value = "";
      if (!identifier || !password) {
        setNotice("Enter both the email/username and the password.");
        return;
      }
      if (handlers.credential) { handlers.credential(identifier, password); }
      els.credId.value = "";
      setNotice("Saved. Signing you in…");
    });
    (document.body || document.documentElement).appendChild(host);
    paint();
    return true;
  }

  // ---------- interaction ----------

  function onPrimary() {
    const p = primaryFor(state.session, state.detection, state.wall);
    if (p.disabled || !p.action) { return; }
    state.notice = "";
    if (handlers.action) { handlers.action(p.action); }
  }

  function onDismiss() {
    if (handlers.dismiss) { handlers.dismiss(); }
    hide();
  }

  function setCollapsed(collapsed) {
    state.collapsed = !!collapsed;
    paint();
  }

  // ---------- inbound state ----------

  function setDetection(detection, formFields, wall) {
    state.detection = detection || "none";
    state.formFields = formFields || 0;
    // 019 (FR-014): "" | "login" | "registration". A wall is reason enough
    // to render the widget even when the page has no application form —
    // it is the page the applicant most needed us on, and it showed nothing.
    state.wall = wall || "";
    if (state.detection !== "none" || state.wall) { build(); }
    paint();
  }

  function setPosting(posting) {
    state.posting = posting || null;
    paint();
  }

  function setScore(result) {
    state.score = result || null;
    paint();
  }

  function setSaved(saved) {
    state.saved = !!saved;
    paint();
  }

  // FR-013: the card opens itself the moment a session starts, so the
  // applicant is never left watching a pill while the form fills behind it.
  function setSession(session) {
    const before = state.session;
    state.session = session || "idle";
    if (state.session === "idle") {
      state.autoExpanded.session = false;
      state.autoExpanded.needs = false;
    }
    const started = before === "idle" && state.session !== "idle";
    if (started && !state.autoExpanded.session) {
      state.autoExpanded.session = true;
      state.collapsed = false;
    }
    if (state.session !== "idle") { build(); }
    paint();
  }

  function setCounts(summary) {
    if (!summary) { return; }
    build();
    state.counts = {
      seen: summary.seen || 0,
      filled: summary.filled || 0,
      needs_you: summary.needs_you || 0,
      drafts: summary.drafts || 0,
    };
    // 018 (FR-032): session context, so Stop and Next can live here.
    state.remaining = summary.remaining || 0;
    state.currentJobId = summary.current_job_id || null;
    if (summary.session) { state.session = summary.session; }
    else if (state.session === "idle" || state.session === "starting") {
      state.session = "filling";
    }
    // FR-013: also open for the FIRST question that needs an answer — that is
    // the moment the applicant has something to do.
    if (state.counts.needs_you > 0 && !state.autoExpanded.needs) {
      state.autoExpanded.needs = true;
      state.collapsed = false;
    }
    paint();
  }

  function setNotice(text) {
    state.notice = text || "";
    paint();
  }

  // ---------- painting ----------

  function pillText() {
    const c = state.counts;
    if (state.session !== "idle" && c.seen > 0) {
      const warn = c.needs_you > 0 ? "⚠ " + c.needs_you + " · " : "";
      return warn + c.filled + "/" + c.seen;
    }
    if (state.session === "starting") { return "Starting…"; }
    if (state.score && state.score.score !== null
        && state.score.score !== undefined) {
      return String(state.score.score);
    }
    return "Job Engine";
  }

  function paint() {
    if (!host) { return; }
    const hasPosting = state.detection === "posting"
      || state.detection === "posting+form";
    const busy = state.session === "filling" || state.session === "starting";

    // pill / card
    els.card.hidden = state.collapsed;
    els.pill.hidden = !state.collapsed;
    els.pillText.textContent = pillText();
    els.pillMark.className = "mark" +
      (state.counts.needs_you > 0 ? " warn" : (busy ? "" : " idle"));
    els.dot.className = "dot" + (busy ? "" : " idle");

    // posting header
    els.co.textContent = hasPosting && state.posting
      ? (state.posting.company || "—") : "";
    els.ti.textContent = hasPosting && state.posting
      ? (state.posting.title || "") : (document.title || "");

    // score block
    const s = state.score;
    els.scorerow.hidden = !s;
    if (s) {
      if (s.needs_resume) {
        els.score.className = "score none";
        els.score.textContent = "—";
        els.band.textContent = "";
      } else {
        const band = s.band || "fair";
        els.score.className = "score " + band;
        els.score.textContent = String(s.score);
        els.band.className = "band " + band;
        els.band.textContent = band + " match";
      }
      els.sponsor.textContent = s.sponsorText || "H-1B: unknown";
      els.sponsor.className = s.sponsorClass || "chip";
    }

    // 019 (FR-014/FR-017): the credential wall. Either we have a saved
    // login for this site (and are using it), or we ask for one here rather
    // than sending the applicant to Settings mid-application.
    els.wallnote.hidden = !state.wall;
    els.loginform.hidden = !(state.wall && state.credentialNeeded);
    if (state.wall) {
      els.wallnote.textContent = state.wall === "registration"
        ? "This site wants a new account. I'll fill it in with a strong "
          + "password saved to your OS keychain — you press Create account."
        : (state.credentialNeeded
           ? "No saved login for " + (location.hostname || "this site")
             + ". Save one and I'll sign you in."
           : "Signing you in with your saved login.");
    }

    // form-only note
    els.formnote.hidden = hasPosting || state.detection === "none";
    if (!els.formnote.hidden) {
      els.formnote.textContent = "Application form found — " +
        state.formFields + " field" + (state.formFields === 1 ? "" : "s") + ".";
    }

    // primary + save
    const p = primaryFor(state.session, state.detection, state.wall);
    els.primary.textContent = p.label;
    els.primary.disabled = p.disabled;
    els.primary.className = "act" + (p.action === "stop" ? " danger" : "");
    els.save.hidden = !hasPosting;
    els.save.disabled = state.saved;
    els.save.textContent = state.saved ? "Saved ✓" : "Save to Job Engine";

    // 018 (FR-032): a queue can be advanced without opening the app.
    els.next.hidden = state.remaining <= 0;
    els.next.textContent = "Next job (" + state.remaining + " left)";

    // progress
    els.prog.hidden = state.counts.seen === 0;
    els.pFilled.textContent = String(state.counts.filled);
    els.pNeeds.textContent = String(state.counts.needs_you);
    els.pSeen.textContent = String(state.counts.seen);

    // notice
    els.notice.hidden = !state.notice;
    els.notice.textContent = state.notice;

    mirror();
  }

  // FR-017: state in the light DOM, so it is observable without piercing the
  // shadow root. Every attribute the 012/016/017 suites assert is carried
  // forward here onto the one remaining host.
  function mirror() {
    const d = host.dataset;
    d.jeCollapsed = state.collapsed ? "1" : "0";
    d.jeSession = state.session;
    d.jeDetection = state.detection;
    if (state.wall) { d.jeWall = state.wall; } else { delete d.jeWall; }
    d.jeSeen = String(state.counts.seen);
    d.jeFilled = String(state.counts.filled);
    d.jeNeedsYou = String(state.counts.needs_you);
    d.jeAnswers = String(state.answers.length);
    d.jeSaved = state.saved ? "1" : "0";
    d.jeCompany = state.posting ? (state.posting.company || "") : "";

    // The score attributes are ABSENT until a score exists, never present and
    // empty. The widget now mounts on detection, before any score has come
    // back — writing `data-je-score=""` made the long-standing
    // `#host[data-je-score]` wait match an unscored card, so a test could read
    // the score before it arrived. It passed on this machine and failed on the
    // slower macOS runner. Absence must mean absence.
    const s = state.score;
    if (s && !s.needs_resume) {
      d.jeScore = String(s.score);
    } else {
      delete d.jeScore;
    }
    if (s) {
      d.jeBand = s.needs_resume ? "none" : (s.band || "fair");
      d.jeSponsor = s.sponsorKey || "unknown";
    } else {
      delete d.jeBand;
      delete d.jeSponsor;
    }
  }

  // ---------- answers ----------
  //
  // 018 (US3). Two things were wrong with the 017 renderer.
  //
  // It listed only what the AI drafter had touched, because the feed came out
  // of `drafter._records`. Everything filled from the profile or the answer
  // bank -- name, email, phone, location, work authorization -- was invisible
  // here, so the surface meant for reviewing an application showed a fraction
  // of it. The feed now carries every decided field, grouped.
  //
  // And it rebuilt EVERY row on every scan (`list.textContent = ""` then
  // recreate), while the app pushed a new payload every ~2 seconds. The input
  // an applicant was typing into was destroyed under their fingers before
  // they could press Enter. Rows are now matched by key and patched in place,
  // and a row holding the focus is not touched at all.

  const GROUPS = [
    { id: "needs_you", label: "Needs you", icon: "\u26a0", open: true },
    { id: "draft", label: "AI drafts \u2014 review", icon: "\u270e", open: false },
    { id: "profile", label: "From your profile", icon: "\u2713", open: false },
  ];

  const rows = new Map();      // key -> row refs
  const groupEls = new Map();  // group id -> {section, header, body, count}
  const groupOpen = {};        // group id -> the applicant's choice
  GROUPS.forEach(function (g) { groupOpen[g.id] = g.open; });

  function ensureGroups() {
    if (groupEls.size) { return; }
    GROUPS.forEach(function (g) {
      const section = document.createElement("div");
      section.className = "grp";
      section.dataset.jeGroup = g.id;

      const header = document.createElement("button");
      header.className = "grph";
      header.type = "button";
      header.setAttribute("aria-expanded", String(groupOpen[g.id]));
      header.addEventListener("click", function () {
        groupOpen[g.id] = !groupOpen[g.id];
        paintGroups();
      });

      const count = document.createElement("span");
      count.className = "grpn";
      header.appendChild(document.createTextNode(g.icon + " " + g.label + " "));
      header.appendChild(count);

      const body = document.createElement("div");
      body.className = "grpb";

      section.appendChild(header);
      section.appendChild(body);
      els.answers.appendChild(section);
      groupEls.set(g.id, { section: section, header: header, body: body,
                           count: count });
    });
  }

  function paintGroups() {
    GROUPS.forEach(function (g) {
      const refs = groupEls.get(g.id);
      if (!refs) { return; }
      let n = 0;
      state.answers.forEach(function (i) { if (i.group === g.id) { n += 1; } });
      refs.section.hidden = n === 0;
      refs.count.textContent = "(" + n + ")";
      refs.header.setAttribute("aria-expanded", String(groupOpen[g.id]));
      refs.body.hidden = !groupOpen[g.id];
    });
  }

  // FR-026: the applicant's typing outranks any update. `activeElement` is
  // read off the SHADOW ROOT -- `document.activeElement` returns the HOST
  // element when focus is inside an open shadow root, so checking the
  // document would never match and this guard would never fire.
  function holdsFocus(node) {
    const active = root && root.activeElement;
    return !!(active && node.contains(active));
  }

  function setAnswers(items, truncated) {
    build();
    if (!host) { return; }
    state.answers = items || [];
    state.truncated = !!truncated;
    reconcile();
    paint();
  }

  function reconcile() {
    ensureGroups();
    const seen = new Set();
    state.answers.forEach(function (item) {
      const key = item.key || item.question || "";
      if (!key) { return; }
      seen.add(key);
      let row = rows.get(key);
      if (!row) {
        row = createRow(item);
        rows.set(key, row);
      }
      const refs = groupEls.get(item.group);
      // appendChild also REORDERS an existing child, which keeps the rows in
      // feed order without ever detaching and recreating them.
      if (refs) { refs.body.appendChild(row.wrap); }
      if (!holdsFocus(row.wrap)) { patchRow(row, item); }
    });
    rows.forEach(function (row, key) {
      if (seen.has(key)) { return; }
      if (holdsFocus(row.wrap)) { return; }  // still being answered
      if (row.wrap.parentNode) { row.wrap.parentNode.removeChild(row.wrap); }
      rows.delete(key);
    });
    paintGroups();
    renderTruncation();
  }

  function createRow(item) {
    const wrap = document.createElement("div");
    wrap.className = "qa";

    const q = document.createElement("div");
    q.className = "q";
    wrap.appendChild(q);

    const a = document.createElement("div");
    a.className = "a";
    wrap.appendChild(a);

    const acts = document.createElement("div");
    acts.className = "acts";
    const copy = smallButton("Copy", function (btn) {
      navigator.clipboard.writeText(row.item.answer).then(
        function () { btn.textContent = "Copied"; },
        function () { btn.textContent = "Copy failed"; });
    });
    const insert = smallButton("Insert", function () {
      if (handlers.insert && row.item.je_idx) {
        handlers.insert(row.item.je_idx, row.item.answer);
      }
    });
    const jump = smallButton("Show me", function () {
      if (handlers.jump && row.item.je_idx) { handlers.jump(row.item.je_idx); }
    });
    acts.appendChild(copy);
    acts.appendChild(insert);
    acts.appendChild(jump);
    wrap.appendChild(acts);

    const why = document.createElement("div");
    why.className = "why";
    wrap.appendChild(why);

    const input = document.createElement("input");
    input.type = "text";
    input.className = "ask";
    input.placeholder = "Your answer \u2014 saved for next time";
    input.addEventListener("keydown", function (evt) {
      if (evt.key !== "Enter") { return; }
      const typed = input.value.trim();
      if (!typed || !handlers.answer) { return; }
      handlers.answer(row.item.question, typed, row.item.je_idx || "");
      input.disabled = true;
      why.textContent = "Saved \u2014 it fills on the next scan.";
    });
    wrap.appendChild(input);

    const row = { wrap: wrap, q: q, a: a, acts: acts, insert: insert,
                  jump: jump, why: why, input: input, item: item };
    return row;
  }

  function patchRow(row, item) {
    row.item = item;
    row.wrap.dataset.jeState = item.state || "";
    row.wrap.dataset.jeKey = item.key || "";
    if (row.q.textContent !== item.question) {
      row.q.textContent = item.question || "";
    }

    const drafting = item.state === "drafting";
    const text = item.answer || (drafting ? "drafting\u2026" : "");
    if (row.a.textContent !== text) { row.a.textContent = text; }
    row.a.className = "a" + (item.state === "drafted" ? " drafted" : "") +
      (drafting ? " muted" : "");
    row.a.hidden = !text;

    // Copy is always available; Insert and Show me need a field to act on.
    // Through v1.7.0 neither ever rendered, because the feed carried no
    // je_idx at all and both were gated on it.
    row.acts.hidden = !item.answer;
    row.insert.hidden = !item.je_idx;
    row.jump.hidden = !item.je_idx;

    row.why.hidden = !item.askable;
    row.input.hidden = !item.askable;
    if (item.askable && !row.input.disabled) {
      row.why.textContent = reasonText(item.reason);
    }
  }

  function renderTruncation() {
    if (!els.more) {
      els.more = document.createElement("div");
      els.more.className = "muted";
      els.more.textContent = "Not every answer fits here \u2014 the app's " +
        "Apply Assist page has the full list.";
      els.answers.appendChild(els.more);
    }
    els.more.hidden = !state.truncated;
  }

  function smallButton(label, fn) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "sm";
    b.textContent = label;
    b.addEventListener("click", function () { fn(b); });
    return b;
  }

  function reasonText(reason) {
    switch (reason) {
      case "binding_commitment":
        return "This one commits you to something \u2014 your call, not ours.";
      case "never_generated":
      case "cannot_answer":
      case "sensitive":
        return "Only you know this one.";
      case "profile_fact_missing":
        return "Add it to your profile and it fills automatically next time.";
      case "no_valid_option":
      case "not_an_option_label":
        return "No option here matched your stored answer.";
      case "wrong_shape":
        return "Your stored answer does not fit this kind of field.";
      case "attempts_exhausted":
      case "job_budget_exhausted":
        return "We could not answer this one \u2014 over to you.";
      default:
        return "Needs you.";
    }
  }

  // ---------- lifecycle ----------

  function show() { build(); }

  function hide() {
    if (host) { host.remove(); }
    host = null;
    root = null;
    els = {};
  }

  return {
    // rendering inputs
    setDetection, setPosting, setScore, setSaved, setSession, setCounts,
    setAnswers, notice: setNotice,
    // 019 (FR-014/FR-017)
    setCredentialNeeded: function (needed) {
      state.credentialNeeded = !!needed;
      if (needed) { build(); setCollapsed(false); }
      paint();
    },
    // lifecycle
    show, hide, isMounted: function () { return !!host; },
    // FR-035: the keyboard shortcut's target
    toggle: function () {
      if (!host) { build(); return; }
      setCollapsed(!state.collapsed);
    },
    // handler registration
    onAction: function (fn) { handlers.action = fn; },
    onSave: function (fn) { handlers.save = fn; },
    onDismiss: function (fn) { handlers.dismiss = fn; },
    onAnswer: function (fn) { handlers.answer = fn; },
    onInsert: function (fn) { handlers.insert = fn; },
    onJump: function (fn) { handlers.jump = fn; },
    onCredential: function (fn) { handlers.credential = fn; },
    // pure, exported for the state-machine test
    primaryFor,
  };
})();

// 017 facade — main.js drives these names and its behaviour is unchanged.
// `hide()` here means "the fill session ended", NOT "remove the widget": with
// one merged companion the badge half must survive a finished fill.
window.jeOverlay = (function () {
  const panel = window.jePanel;
  return {
    show: function () { panel.show(); },
    // NOT "remove the widget" — with one merged companion the badge half has
    // to survive a finished fill. main.js calls this from teardown(), which
    // means the watch stopped, so the session is done and the primary action
    // becomes "Fill again".
    hide: function () { panel.setSession("done"); },
    note: function (text) { panel.notice(text); },
    update: function (summary) { panel.setCounts(summary); },
    setAnswers: function (items, truncated) { panel.setAnswers(items, truncated); },
    onAnswer: function (fn) { panel.onAnswer(fn); },
    onInsert: function (fn) { panel.onInsert(fn); },
    onJump: function (fn) { panel.onJump(fn); },
    // 016 (T016): Fill again is now the primary action in the `done`/`stopped`
    // states, so this registration is kept for compatibility and routed
    // through the same handler chain by discovery.js.
    onFillAgain: function (fn) { window.jeFillAgainHandler = fn; },
  };
})();
