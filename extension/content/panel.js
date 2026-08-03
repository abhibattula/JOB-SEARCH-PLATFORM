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
    // 021 (FR-032): where the app is, so a needs-you row can link into it.
    appOrigin: "http://127.0.0.1:8756",
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

  // 019: an ABSENT key is not a claim of zero. Pure, and exported, so the
  // suite can execute the real merge rather than assert on its source.
  function keepValue(value, previous) {
    return (value === undefined || value === null) ? previous : value;
  }

  function mergeCounts(previous, summary) {
    const base = previous || { seen: 0, filled: 0, needs_you: 0, drafts: 0 };
    if (!summary) { return base; }
    return {
      seen: keepValue(summary.seen, base.seen),
      filled: keepValue(summary.filled, base.filled),
      needs_you: keepValue(summary.needs_you, base.needs_you),
      drafts: keepValue(summary.drafts, base.drafts),
    };
  }

  // ---------- mounting ----------

  // 018 (R1): reset FIRST, then pin — `all` is a shorthand for every CSS
  // property, so declaring it after `position:fixed` (as every version from
  // v1.0.0 to v1.7.0 did) reset the widget to `position:static` and it
  // rendered at the bottom of the document instead of the corner of the
  // screen. `!important` because a plain inline declaration loses to a page
  // rule like `div { position: static !important }`.
  // 021 (FR-027..FR-030): the applicant drags the panel out of the way.
  //
  // Offsets from the RIGHT and BOTTOM, not page coordinates: it keeps the
  // existing `inset` idiom, behaves correctly when the window is resized,
  // and does not scroll away from the form.
  //
  // Every declaration stays `!important`. A drag implementation that wrote
  // `style.left` normally would resurrect the exact bug documented above —
  // a page rule like `div { position: static !important }` outranks a plain
  // inline declaration.
  const DEFAULT_POS = { right: 16, bottom: 16 };
  const POS_KEY = "je_panel_pos";
  let pos = { right: DEFAULT_POS.right, bottom: DEFAULT_POS.bottom };

  function clampPos(candidate) {
    // FR-028: a position saved on a large monitor must not strand the panel
    // off-screen on a laptop. Keep a usable amount of it reachable.
    const width = host ? host.offsetWidth || 340 : 340;
    const height = host ? host.offsetHeight || 120 : 120;
    const maxRight = Math.max(0, window.innerWidth - 60);
    const maxBottom = Math.max(0, window.innerHeight - 40);
    return {
      right: Math.min(Math.max(candidate.right, 60 - width), maxRight),
      bottom: Math.min(Math.max(candidate.bottom, 40 - height), maxBottom),
    };
  }


  /* 022 (FR-034, contract panel-theme.md): the applicant's theme arrives as
     an ADDITIVE field on watch_start / overlay_state — outbound messages are
     plain dicts with no schema, so PROTOCOL_V stays 1 and a companion that
     predates this simply never looks for it.

     Resolution order: explicit choice -> OS preference -> light. */
  /* Exposed so main.js can call it from watch_start and
     overlay_state without reaching into the module. */
  function applyTheme(theme) {
    const host = document.getElementById("je-companion-host");
    if (!host) { return; }
    if (theme === "dark" || theme === "light") {
      host.setAttribute("data-theme", theme);
    } else {
      /* No stated preference: let the :host media query in STYLE decide,
         which reads prefers-color-scheme. */
      host.removeAttribute("data-theme");
    }
  }
  window.jePanelTheme = applyTheme;

  function applyPos(el) {
    el.style.setProperty(
      "inset", "auto " + pos.right + "px " + pos.bottom + "px auto",
      "important");
  }

  function pin(el) {
    el.style.cssText = "all:initial";
    el.style.setProperty("position", "fixed", "important");
    el.style.setProperty("z-index", "2147483647", "important");
    el.style.setProperty("display", "block", "important");
    applyPos(el);
  }

  function savePos() {
    try {
      if (chrome && chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({ [POS_KEY]: pos });
      }
    } catch (e) { /* storage unavailable — the panel still moves */ }
  }

  function restorePos() {
    try {
      if (!chrome || !chrome.storage || !chrome.storage.local) { return; }
      chrome.storage.local.get(POS_KEY, function (stored) {
        const saved = stored && stored[POS_KEY];
        if (!saved || typeof saved.right !== "number") { return; }
        pos = clampPos(saved);
        if (host) { applyPos(host); }
      });
    } catch (e) { /* first run, or a context that has no storage */ }
  }

  function resetPos() {
    pos = { right: DEFAULT_POS.right, bottom: DEFAULT_POS.bottom };
    if (host) { applyPos(host); }
    savePos();
  }

  function startDrag(evt) {
    if (!host || evt.button !== 0) { return; }
    // Not from a control — the header carries Collapse and Dismiss.
    if (evt.target.closest && evt.target.closest("button")) { return; }
    evt.preventDefault();
    const startX = evt.clientX;
    const startY = evt.clientY;
    const from = { right: pos.right, bottom: pos.bottom };

    function move(e) {
      // Dragging right REDUCES the right offset; dragging down reduces
      // bottom. Clamped live so it can never be dragged out of reach.
      pos = clampPos({ right: from.right - (e.clientX - startX),
                       bottom: from.bottom - (e.clientY - startY) });
      applyPos(host);
    }
    function done() {
      window.removeEventListener("mousemove", move, true);
      window.removeEventListener("mouseup", done, true);
      savePos();
    }
    window.addEventListener("mousemove", move, true);
    window.addEventListener("mouseup", done, true);
  }

  function onViewportResize() {
    if (!host) { return; }
    pos = clampPos(pos);
    applyPos(host);
  }

  const STYLE = `
    *{box-sizing:border-box}
    :host{contain:layout style}

    /* 022: the app's tokens, INJECTED — the shadow root is opened with
       all:initial, so nothing can be inherited. Same names as
       web/static/styles.css so the two surfaces cannot drift.
       :host carries data-theme; the media query decides only when the
       applicant has expressed no preference. */
    :host{
      --paper:#f6f7f5; --leaf:#ffffff; --ink:#12211c; --ink-soft:#4a5b53;
      --rule:#dfe4e0; --edge:#76857d; --seal:#1f6f5c; --pencil:#4a5f7a;
      --flag:#9a6116; --stop:#a63a2e; --paper-sunken:#eceeea;
      --seal-tint:#e8f2ee; --pencil-tint:#eef2f7; --flag-tint:#fbf3e7;
      --stop-tint:#f9ece9; --on-ink:#f6f7f5;
    }
    :host([data-theme="dark"]){
      --paper:#12160f; --leaf:#1a1f18; --ink:#dfe6dd; --ink-soft:#9aa89e;
      --rule:#2b332a; --edge:#697665; --seal:#4fc4a1; --pencil:#8fa8c4;
      --flag:#e0a53c; --stop:#ef7367; --paper-sunken:#0d100b;
      --seal-tint:#10261d; --pencil-tint:#161d27; --flag-tint:#2a2110;
      --stop-tint:#2d1512; --on-ink:#12160f;
    }
    @media (prefers-color-scheme: dark){
      :host(:not([data-theme="light"]):not([data-theme="dark"])){
        --paper:#12160f; --leaf:#1a1f18; --ink:#dfe6dd; --ink-soft:#9aa89e;
        --rule:#2b332a; --edge:#697665; --seal:#4fc4a1; --pencil:#8fa8c4;
        --flag:#e0a53c; --stop:#ef7367; --paper-sunken:#0d100b;
        --seal-tint:#10261d; --pencil-tint:#161d27; --flag-tint:#2a2110;
        --stop-tint:#2d1512; --on-ink:#12160f;
      }
    }
    /* 022 (FR-018): the provenance stamp, same treatments as the app —
       ring style carries the signal so it survives greyscale. */
    .score.stamp--pencil{color:var(--pencil);border-style:dashed;
      background:var(--pencil-tint)}
    .score.stamp--ink{color:var(--ink);border-style:solid}
    .score.stamp--sealed{color:var(--seal);border-style:double;
      border-width:5px;background:var(--seal-tint)}
    .score.stamp--unscored{color:var(--ink-soft);border-style:dotted;
      background:transparent}
    /* The UA rule for [hidden] is display:none, but an AUTHOR rule such as
       .card{display:flex} outranks it, so el.hidden = true would leave the
       card on screen. Restate it here, in the author layer, where it wins.
       (No backticks in this block: it lives inside a template literal.) */
    [hidden]{display:none!important}
    .pill{display:flex;align-items:center;gap:7px;cursor:pointer;
      font:600 13px/1 system-ui,-apple-system,sans-serif;
      background:var(--leaf);color:var(--ink);border:1px solid var(--rule);
      border-radius:999px;padding:9px 14px;
      box-shadow:0 6px 20px rgba(0,0,0,.4)}
    .pill:hover{background:var(--paper)}
    .pill .mark{width:8px;height:8px;border-radius:50%;background:var(--seal);
      flex:none}
    .pill .mark.idle{background:var(--ink-soft)}
    .pill .mark.warn{background:var(--flag)}
    .card{font:13px/1.45 system-ui,-apple-system,sans-serif;width:340px;
      max-height:calc(100vh - 32px);display:flex;flex-direction:column;
      background:var(--leaf);color:var(--ink);border:1px solid var(--rule);
      border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.45);
      overflow:hidden}
    .hd{display:flex;align-items:center;gap:8px;padding:9px 11px;
      background:var(--paper);border-bottom:1px solid var(--rule);flex:none}
    .hd .tag{font-weight:700;letter-spacing:.2px}
    .hd .sp{flex:1}
    .dot{width:8px;height:8px;border-radius:50%;background:var(--seal);flex:none}
    .dot.idle{background:var(--ink-soft)}
    .icon{cursor:pointer;color:var(--ink-soft);font-size:14px;line-height:1;
      padding:3px 5px;border-radius:5px;user-select:none;background:none;
      border:0}
    .icon:hover{background:var(--paper-sunken);color:var(--ink)}
    .bd{padding:11px;overflow-y:auto;flex:1;min-height:0}
    .co{color:var(--ink-soft);font-size:12px;white-space:nowrap;overflow:hidden;
      text-overflow:ellipsis}
    .ti{font-weight:600;margin:1px 0 9px;white-space:nowrap;overflow:hidden;
      text-overflow:ellipsis}
    .row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
    .score{width:46px;height:46px;border-radius:50%;display:flex;
      align-items:center;justify-content:center;font-weight:700;font-size:16px;
      border:2px solid var(--rule);flex:none}
    .score.strong{color:var(--seal);border-color:var(--seal)}
    .score.good{color:var(--flag);border-color:var(--flag)}
    .score.fair{color:var(--ink-soft)}
    .score.none{font-size:11px;font-weight:600;color:var(--ink-soft)}
    .meta{min-width:0}
    .band{font-weight:600;text-transform:capitalize}
    .band.strong{color:var(--seal)}.band.good{color:var(--flag)}.band.fair{color:var(--ink-soft)}
    .chip{display:inline-block;margin-top:2px;padding:1px 7px;
      border-radius:999px;font-size:11px;font-weight:600;background:var(--paper-sunken);
      color:var(--ink-soft)}
    .chip.grade{background:var(--seal-tint);color:var(--seal)}
    .chip.exempt{background:var(--pencil-tint);color:var(--seal)}
    button.act{width:100%;padding:9px;border:0;border-radius:8px;
      background:var(--seal);color:var(--on-ink);font-weight:600;font-size:13px;
      cursor:pointer;margin-bottom:6px}
    button.act:hover{background:var(--seal)}
    button.act[disabled]{background:var(--paper-sunken);color:var(--ink-soft);cursor:default}
    button.act.ghost{background:var(--paper-sunken);color:var(--ink);
      border:1px solid var(--rule)}
    button.act.ghost:hover{background:var(--rule)}
    button.act.danger{background:var(--stop)}
    button.act.danger:hover{background:var(--stop)}
    .formnote{color:var(--ink-soft);font-size:12px;margin-bottom:9px}
    .wallnote{color:var(--ink);font-size:12px;margin-bottom:9px;
      background:var(--paper);border:1px solid var(--rule);border-left:3px solid var(--seal);
      border-radius:6px;padding:8px 10px}
    .loginform{display:flex;flex-direction:column;gap:6px;margin:8px 0}
    .loginform input{font:13px system-ui,-apple-system,sans-serif;
      background:var(--leaf);color:var(--ink);border:1px solid var(--rule);
      border-radius:6px;padding:7px 9px}
    .loginform input:focus-visible{outline:2px solid var(--seal);outline-offset:1px}
    .credhint{color:var(--ink-soft);font-size:11px;line-height:1.35}
    .prog{display:flex;gap:10px;font-size:12px;color:var(--ink-soft);margin:8px 0 4px;
      flex-wrap:wrap}
    .prog b{color:var(--ink);font-weight:600}
    .prog .warn b{color:var(--flag)}
    .notice{margin-top:7px;padding:6px 8px;background:var(--paper-sunken);
      border-radius:6px;color:var(--flag);font-size:12px}
    .foot{padding:8px 11px;border-top:1px solid var(--rule);color:var(--ink-soft);
      font-size:11px;flex:none;background:var(--leaf)}
    .muted{color:var(--ink-soft);font-size:12px}
    /* answer groups */
    .grp{margin-top:9px;border-top:1px solid var(--paper-sunken);padding-top:7px}
    .grph{width:100%;text-align:left;background:none;border:0;cursor:pointer;
      color:var(--ink-soft);font:600 11px system-ui;text-transform:uppercase;
      letter-spacing:.04em;padding:3px 0}
    .grph:hover{color:var(--ink)}
    .grph[aria-expanded="true"]{color:var(--ink)}
    .grpn{color:var(--ink-soft);font-weight:600}
    .grpb{margin-top:5px}
    .hd{cursor:move;user-select:none}
    .hd button{cursor:pointer}
    .sec{margin:0 0 8px}
    .sech{font-size:11px;text-transform:uppercase;letter-spacing:.04em;
      color:var(--ink-soft);margin:6px 0 4px;padding-bottom:2px;
      border-bottom:1px solid var(--paper-sunken)}
    .qa{margin:0 0 9px;padding-bottom:7px;border-bottom:1px solid var(--paper-sunken)}
    .qa:last-child{border-bottom:0;margin-bottom:0}
    .q{font-size:12px;color:var(--ink);margin-bottom:3px}
    .a{font-size:12px;color:var(--ink);white-space:pre-wrap;word-break:break-word}
    .a.drafted{color:var(--pencil)}
    .a.muted{color:var(--ink-soft)}
    .acts{display:flex;gap:6px;margin-top:5px}
    .sm{padding:3px 8px;font:11px system-ui;background:var(--paper-sunken);color:var(--ink);
      border:1px solid var(--rule);border-radius:5px;cursor:pointer}
    .sm:hover{background:var(--rule)}
    .why{font-size:11px;color:var(--flag);margin-top:3px}
    .plink{color:var(--seal)}
    .ask{width:100%;margin-top:4px;padding:5px 7px;font:12px system-ui;
      background:var(--leaf);color:var(--ink);border:1px solid var(--rule);
      border-radius:5px}
    .ask:disabled{opacity:.6}
    :focus-visible{outline:2px solid var(--seal);outline-offset:2px}
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
        <button class="icon" id="resetpos" title="Reset position"
                aria-label="Reset position">↺</button>
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
        <!-- 021 (FR-001): what this page ACTUALLY looks like, written to a
             file the applicant can hand back. Shape only — never a value,
             never a full URL. It is the artifact behind every future
             "it didn't fill" report. -->
        <button class="act ghost" id="report">Save page report</button>
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
      report: root.getElementById("report"),
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
    // 021 (FR-027/FR-030): drag by the header; reset to the corner.
    root.getElementById("resetpos").addEventListener("click", resetPos);
    root.querySelector(".hd").addEventListener("mousedown", startDrag);
    els.pill.addEventListener("mousedown", startDrag);
    window.addEventListener("resize", onViewportResize);
    root.getElementById("dismiss").addEventListener("click", onDismiss);
    els.primary.addEventListener("click", onPrimary);
    els.next.addEventListener("click", function () {
      if (handlers.action) { handlers.action("next"); }
    });
    els.save.addEventListener("click", function () {
      if (handlers.save) { handlers.save(); }
    });
    els.report.addEventListener("click", function () {
      if (handlers.report) { handlers.report(); }
      setNotice("Saving a page report…");
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
    restorePos();
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
    state.method = (result && result.method) || "basic";
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
    // 019: PATCH, don't replace. Some messages exist only to change the
    // session state — reaching the review page, pausing the escort — and
    // carry no counts at all. Replacing wholesale made those messages
    // claim the page had zero fields, so the applicant arrived at the end
    // of a fully escorted application and was told "Filled 0 · Seen 0" in
    // the exact moment the widget had the most to be proud of. An absent
    // key is not a claim of zero.
    state.counts = mergeCounts(state.counts, summary);
    // 018 (FR-032): session context, so Stop and Next can live here.
    state.remaining = keepValue(summary.remaining, state.remaining);
    state.currentJobId = keepValue(summary.current_job_id,
                                   state.currentJobId);
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
        els.score.className = "score none stamp--unscored";
        els.score.textContent = "—";
        els.band.textContent = "";
      } else {
        const band = s.band || "fair";
        /* 022 (FR-015/FR-018): the ring states how the number was
           produced, exactly as the app's feed does. The discovery path is
           always basic_match, so this badge is a pencil mark — it has been
           rendering in confident colour bands that read like a full
           assessment. */
        els.score.className = "score " + band + " "
          + (state.method === "llm" ? "stamp--sealed"
             : state.method === "local" ? "stamp--ink" : "stamp--pencil");
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

  // 021 (FR-008): rows are grouped by the region of the form they came from.
  // A flat list of 149 rows is not a review surface. `section_label` of ""
  // means UNDETERMINED — those rows sit directly in the group exactly as they
  // did in v2.0.0, because a wrong grouping is worse than no grouping.
  const sections = new Map();  // group\0label\0index -> {wrap, body, count}

  function sectionTitle(item) {
    const index = item.section_index || 0;
    return index > 0 ? item.section_label + " " + (index + 1)
                     : item.section_label;
  }

  // 021: move a node ONLY when it is genuinely out of position.
  //
  // The old code called `refs.body.appendChild(row.wrap)` on every reconcile
  // and relied on appendChild's reordering side-effect. Re-inserting a node
  // BLURS any focused element inside it — so the moment a payload actually
  // changed, focus was stolen from the box the applicant was typing in. Until
  // 021 the digest's send-nothing-if-unchanged rule hid that; the browser
  // suite caught it as soon as the payload gained new fields.
  function placeAt(parent, node, index) {
    if (parent.children[index] === node) { return; }
    // Never reorder under the applicant's fingers.
    if (holdsFocus(node)) { return; }
    parent.insertBefore(node, parent.children[index] || null);
  }

  function sectionBody(item) {
    const refs = groupEls.get(item.group);
    if (!refs) { return null; }
    if (!item.section_label) { return refs.body; }
    const key = item.group + " " + item.section_label + " "
      + (item.section_index || 0);
    let sec = sections.get(key);
    if (!sec) {
      const wrap = document.createElement("div");
      wrap.className = "sec";
      const head = document.createElement("div");
      head.className = "sech";
      const body = document.createElement("div");
      sec = { wrap: wrap, head: head, body: body, key: key };
      wrap.appendChild(head);
      wrap.appendChild(body);
      sections.set(key, sec);
    }
    if (sec.head.textContent !== sectionTitle(item)) {
      sec.head.textContent = sectionTitle(item);
    }
    if (sec.wrap.parentNode !== refs.body) { refs.body.appendChild(sec.wrap); }
    return sec.body;
  }

  function reconcile() {
    ensureGroups();
    const seen = new Set();
    const liveSections = new Set();
    const placed = new Map();   // container -> how many rows placed in it
    state.answers.forEach(function (item) {
      const key = item.key || item.question || "";
      if (!key) { return; }
      seen.add(key);
      let row = rows.get(key);
      if (!row) {
        row = createRow(item);
        rows.set(key, row);
      }
      const body = sectionBody(item);
      if (body) {
        // Placed by INDEX, and only when actually out of position — see
        // placeAt. Blindly re-appending steals focus from a box the
        // applicant is typing in.
        const at = placed.get(body) || 0;
        placed.set(body, at + 1);
        placeAt(body, row.wrap, at);
        if (item.section_label) {
          liveSections.add(item.group + " " + item.section_label
                           + " " + (item.section_index || 0));
        }
      }
      if (!holdsFocus(row.wrap)) { patchRow(row, item); }
    });
    sections.forEach(function (sec, key) {
      if (liveSections.has(key)) { return; }
      if (holdsFocus(sec.wrap)) { return; }
      if (sec.wrap.parentNode) { sec.wrap.parentNode.removeChild(sec.wrap); }
      sections.delete(key);
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
    // 021 (FR-005): one row can stand for several elements — a Workday
    // prompt is a button plus its listbox, and both are real fields. Pressing
    // "Show me" again walks to the next one instead of parking on the first.
    const jump = smallButton("Show me", function () {
      if (!handlers.jump) { return; }
      const all = (row.item.je_idx_all && row.item.je_idx_all.length)
        ? row.item.je_idx_all
        : (row.item.je_idx ? [row.item.je_idx] : []);
      if (!all.length) { return; }
      row.jumpAt = (row.jumpAt + 1) % all.length;  // starts at -1 → first
      handlers.jump(all[row.jumpAt]);
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
                  jump: jump, why: why, input: input, item: item,
                  jumpAt: -1 };
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
      // 021 (FR-032): "Add it to your profile" was a dead instruction that
      // never said WHICH field. On the applicant's real page it appeared on
      // Country/Region and State - fields the app already knows about and
      // they had simply not filled in.
      if (item.reason === "profile_fact_missing" && item.profile_field) {
        const link = document.createElement("a");
        link.className = "plink";
        link.textContent = " Open that field →";
        link.href = state.appOrigin + "/profile#field-" + item.profile_field;
        link.target = "_blank";
        link.rel = "noopener";
        row.why.appendChild(link);
      }
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
    // 021 (FR-001): the applicant asks the app to write a page report.
    onReport: function (fn) { handlers.report = fn; },
    // pure, exported for the state-machine tests
    primaryFor, mergeCounts,
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
