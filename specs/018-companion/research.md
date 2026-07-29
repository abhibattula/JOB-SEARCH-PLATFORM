# Research — 018 The Companion

Every decision below was verified against the code in this repository or
against documented platform behaviour. Where a plausible approach was rejected,
the reason is recorded so it is not re-attempted.

---

## R1 — Why both widgets render at the bottom of the page

**Finding.** `all` is a CSS **shorthand for every property** (except
`unicode-bidi`, `direction` and custom properties). Within one declaration
block, a later declaration of the same property wins. Both hosts do:

```js
host.style.cssText = "position:fixed;z-index:2147483647;top:16px;right:16px;all:initial;";
```

`all:initial` is **last**, so it resets `position` → `static`, `top`/`right` →
`auto`, `z-index` → `auto`, and `display` → `inline`. The host is appended as
the last child of `<body>`, so it renders at the end of the document flow — the
bottom of the page. Present in `extension/content/overlay.js:35-36` and
`extension/content/discovery.js:184-185` since 010 (v1.0.0).

**Decision.** Reset first, then position, and make the positioning
`!important`:

```js
host.style.cssText = "all:initial";
host.style.setProperty("position", "fixed", "important");
host.style.setProperty("inset", "auto 16px 16px auto", "important");
host.style.setProperty("z-index", "2147483647", "important");
host.style.setProperty("display", "block", "important");
```

**Why `!important` and not merely correct ordering.** Inline declarations
without `!important` sit in the author-normal cascade layer and therefore lose
to an author rule marked `!important`. A page shipping
`div { position: static !important }` would re-break the widget exactly as it is
broken today. An inline declaration **with** `!important` sits in the
author-important layer at the highest specificity, so it wins. This is cheap
insurance against a class of failure we have already suffered once.

**Rejected — `all:initial` last but with `position` re-applied after**: works,
but leaves a fragile ordering dependency that the next editor can silently
reintroduce. Reset-then-set reads as intent.

**Rejected — dropping `all:initial`**: it is doing real work (it prevents the
page's `div{}` rules from styling the host box). Keep it, just first.

---

## R2 — Why "Apply with Apply Assist" does nothing

**Finding.** `discovery.js:319-321`:

```js
function onApply() {
  const p = current && current.posting;
  if (!p || !els.apply || els.apply.disabled) { return; }
```

but `requestScore()` (`discovery.js:157`) sets
`current = { ...p, url: location.href }` — keys `title`, `company`,
`description`, `location`, `url`. There is **no `posting` key**, so `p` is
always `undefined` and the handler returns before sending `apply_here`.

**Decision.** Read `current` directly. The message the app expects
(`ext_protocol.ApplyHere`: `tab_id`, `url`, `title`, `company`, `description`)
maps straight onto `current`'s own keys.

**Note.** The app side (`ext_backend._handle_apply_here`) is correct and was
never reached. No app-side change is needed for this defect.

---

## R3 — Why the test suite did not catch R2

**Finding.** `tests/test_extension_assets.py:517-535` — every 017 badge-launcher
test asserts a **string appears in a source file**:

```python
assert "Apply with Apply Assist" in self.badge()
assert "apply_here" in self.badge()
assert "window.jeOverlay" in source
```

All three pass against the dead handler.

**Decision.** Interaction coverage moves to the real-browser harness. Static
guards are retained **only** for negative invariants — "this file contains no
`.click(` on page elements", "answers never go in via `innerHTML`" — which is
the one thing source inspection genuinely proves.

**Harness already exists**: `tests/integration/test_discovery_badge.py` loads
the real unpacked extension into real Chromium, points `pairing.json` at a live
in-process FastAPI app over the real WebSocket bridge, and drives shadow-root
controls with

```python
page.evaluate("() => document.getElementById('<host>').shadowRoot"
              ".getElementById('save').click()")
```

Every new interaction test reuses this pattern. No new infrastructure.

---

## R4 — Why Insert and Show me never appear

**Finding.** `overlay.js:249` gates both buttons on `item.je_idx`.
`drafter.answers_for_page()` builds its items from `drafter._records` and emits
`question`, `answer`, `state`, `reason`, `askable` — no `je_idx`.
`grep je_idx engine/autofill/drafter.py` returns nothing.

**Decision.** The field identifier is already known where the decision is made:
`ext_backend._handle_fields` computes `fkey = (tab_id, frame_id, raw["je_idx"])`
at line 455 and puts `raw["je_idx"]` on the outgoing fill item at line 484. The
answer feed is therefore assembled **in `_handle_fields`**, not read out of the
drafter alone.

---

## R5 — Why the panel shows only a fraction of the application

**Finding.** `drafter._records` is populated only by the AI drafting path.
Fields resolved by `profile_answers`, the answer bank, or a direct tag map never
enter it, so they cannot reach the page. `browser_controller._record` does hold
every field — but truncates to a 60-character `value_preview` and carries no
`je_idx`, so it cannot back Insert either.

**Decision — one page-answer index per job**, assembled in `_handle_fields`
where every decision passes, keyed by `field_core.key(raw)` (the existing stable
ledger key), holding `{je_idx, question, answer, group, reason, tag}`. Drafter
records are merged in for questions the drafter owns.

Groups:

| group | source | shown |
|-------|--------|-------|
| `needs_you` | `decision.action == "skip"` with a needs-you reason, or a drafter refusal | expanded, first |
| `draft` | `decision.ai_draft` is true | collapsed |
| `profile` | any other filled decision | collapsed |

**Rejected — extending `browser_controller._record`**: it feeds the app's
activity log, whose 60-character truncation is deliberate. Widening it would
change an unrelated surface and grow every fill report.

**Rejected — a new DB table**: the feed is per-live-session state. Nothing here
needs to outlive the session; the answer bank already persists what should
persist.

---

## R6 — Why typing in the panel is destroyed

**Finding.** Two independent causes compound:

1. `overlay.js:174-181` — `setAnswers` does `list.textContent = ""` and rebuilds
   every row, so the `<input>` the applicant is typing into is **replaced**.
2. `ext_backend.py:580-594` — the `answers` payload is pushed on **every**
   `fields` message, and `main.js:82` scans on a MutationObserver plus a 2 s
   safety poll.

So a half-typed answer is destroyed within ~2 seconds, every time.

**Decision.**

- **Keyed reconciliation** in the panel: each row carries a stable key (the
  question key). Rows are matched and patched in place; only genuinely new rows
  are created and only removed rows are deleted.
- **Focus is sacred**: if a row contains `document.activeElement` (or the
  panel's shadow root's `activeElement`), that row's input is not touched at
  all, even if its data changed.
- **Digest suppression** app-side: hash the assembled feed and skip the push
  when it equals the last one sent for that tab. This also removes a payload of
  up to 400 KB from the socket every 2 s.

**Note on shadow DOM**: `document.activeElement` returns the **host** element
when focus is inside an open shadow root. The focus check must therefore use
`root.activeElement` on the shadow root, not `document.activeElement`.

---

## R7 — Making the companion appear on a bare application form

**Finding.** The badge renders only when `detect()` finds posting metadata
(JSON-LD `JobPosting`, or LinkedIn/Indeed selectors). A Greenhouse
`…/application` page frequently has none. The fill panel appears only once a
session is already watching (`main.js:83-84`). So the page where the applicant
most needs the companion shows nothing.

**Decision — a read-only form probe.**

**Critical constraint discovered:** `jeScanner.serialize()` **mutates the page**
— `stamp()` writes `data-je-idx` on every field and `docToken()` writes
`data-je-doc`/`data-je-next` on `<html>` (`scanner.js:59-76`). Calling it merely
to decide whether to show a widget would break the 012 read-only guarantee on
every page the applicant browses, before they have asked for anything.

So the probe is a **new, separate, non-stamping** function —
`jeScanner.probe()` — reusing the same `FIELD_SELECTOR` and visibility rule but
returning only counts:

```js
function probe() {  // read-only: no stamp(), no docToken()
  const els = document.querySelectorAll(FIELD_SELECTOR);
  ...
  return { fields, hasFile, hasEmail };
}
```

**Heuristic** (deliberately conservative — a false positive puts a widget on
every page with a search box). Exclusions, in order:

1. **Drop every field inside a form that contains a visible password input.**
   A credential form is not an application, and we never fill credentials.
   This exclusion is load-bearing: dropping the password field *alone* still
   leaves `username` in the count, which — together with a newsletter email —
   reaches three controls and two text-ish fields on an entirely ordinary page.
2. Drop `type=search` and `type=password`.
3. Drop fields whose `name`/`id` matches `^(q|s|search|query|keyword)$`.

Then, over what remains:

- `fields` = count; `textish` = count of `text|email|tel|url|number|""` inputs
  and `textarea`s; `hasFile` = a visible `input[type=file]` is present.
- **A form is present when `textish >= 2 && (fields >= 3 || (hasFile && fields >= 2))`.**

Verified against the three fixtures: `bare_application.html` → 8 fields /
6 text-ish → yes; `search_only.html` → 2 fields / 1 text-ish → no;
`hostile_css.html` → 1 field → no (it is detected as a *posting*, not a form).

Posting metadata, when present, still adds the score header; the two signals are
independent inputs to one widget.

---

## R8 — One widget, and where it lives

**Decision.** New `extension/content/panel.js` owns the single host
`je-companion-host`. `discovery.js` keeps **all** detection/scoring logic and
becomes a data source (`panel.setPosting`, `panel.setScore`). The fill half
(`overlay.js`) is replaced.

**`window.jeOverlay` is preserved as a thin facade** over the panel
(`show/hide/update/note/setAnswers/onAnswer/onInsert/onJump/onFillAgain`), so
`main.js` needs no restructuring and the 016/017 behaviour it drives is
unchanged.

**Content-script world.** All content scripts of one extension share **one
isolated world per frame**, so `panel.js`, `discovery.js` and `main.js` see each
other's globals — this is already relied on by 017 (`discovery.js:329` calls
`window.jeOverlay.show()`).

**Manifest change.** `discovery.js` currently sits in a **second**
`content_scripts` entry. Merging it into the single entry, ordered after
`panel.js`, makes the load order explicit rather than dependent on
cross-entry injection order. Guards stay defensive regardless.

**Top-frame only.** The companion mounts only when `window === window.top`
(both current widgets already do this); sub-frames continue to scan and fill
their own documents with no UI.

---

## R9 — Persisting collapsed/expanded state

**Finding.** `chrome.storage.session` defaults to `TRUSTED_CONTEXTS` access
level, which **excludes content scripts**. It is usable from the service worker
(as `service-worker.js:57` already does) but not from `panel.js` unless the
worker calls `setAccessLevel({accessLevel: "TRUSTED_AND_UNTRUSTED_CONTEXTS"})`.

**Decision.** Keep the collapse state in a module variable in the content
script. The content script is **not** re-injected on same-document (SPA)
navigation, so this satisfies FR-014 for the case that actually matters. A full
page load resets to the default resting state, which is the correct default
anyway.

**Rejected — widening `storage.session` access to untrusted contexts**: it would
expose every session key (including the connection-attempt record) to every
content script on every site, to persist one boolean. Bad trade.

**Rejected — `window.sessionStorage`**: writing to the page's own storage is a
page mutation, which the badge has promised never to do since 012.

---

## R10 — On-page session control

**Decision.** One new **additive** inbound message, `session_control`, with an
`action` field (`stop` | `next`), handled beside the existing `fill_again` and
delegating to `browser_controller.stop_queue()` / `advance()` — the same
functions `POST /api/autofill/stop` and `/next` already call.

**No new capability.** These actions already exist and are already reachable
from the app; this only removes the tab switch. `fill_again` stays as it is.

**`PROTOCOL_V` stays 1.** `ext_protocol` models are `_Strict` with
`extra="ignore"` on the outbound side and defaulted optional fields, so a
companion older than the app ignores unknown outbound fields, and the app
rejects unknown inbound types with the existing protocol-reject counter rather
than crashing. Adding an inbound type is additive; the version-gate pattern used
for `kind:"radio"` (016) is available if any behaviour ever needs an exact-match
companion.

---

## R11 — Keyboard shortcuts

**Decision.** Add a `commands` block to the manifest with two commands —
toggle the companion, and fill the current page. `chrome.commands.onCommand`
fires in the service worker, which messages the active tab's top frame.

- No permission is required for `commands`.
- Suggested keys must avoid Chrome's reserved set; both are user-rebindable at
  `chrome://extensions/shortcuts`, and Chrome silently drops a conflicting
  suggestion rather than failing to load, so a clash degrades to
  "unbound", never to a broken extension.
- Suggested: `Alt+J` (toggle), `Alt+Shift+J` (fill). `Alt`-based combinations
  avoid the `Ctrl+Shift+…` space Chrome and most sites contend for.

---

## R12 — Removing the app-side round trip

**Finding.** `web/templates/job_detail.html:188` does
`window.location.href = "/autofill"` after a successful start, so starting a
fill navigates away from the job being read.

**Decision.** Start the session and render status **in place** (the response
already carries `started`, `current_job_id` and `backend`), with a link to the
Apply Assist page for anyone who wants the full record. `POST
/api/autofill/apply/{job_id}` is unchanged.

---

## R13 — Rendering safety and offline-first

- Answer text and question text continue to go in via `textContent`. The 017
  guard test (`renderRow` contains no `.innerHTML`) is retained and extended to
  the new renderer.
- All companion CSS is inline in the shadow root; icons are inline SVG or text
  glyphs. **No external requests, no web-accessible resources, no fonts** —
  the offline-first constraint holds and `web_accessible_resources` stays `[]`.
- The companion respects `prefers-reduced-motion` and ships a visible focus
  ring (FR-018).

---

## R14 — What is deliberately NOT changing

017's answer semantics are correct and stay exactly as they are: the
`CANNOT_ANSWER` refusal contract, `NEVER_GENERATED_TAGS`, `value_fits`
(answer-shape-must-fit-field), canonical vocabulary matching, the
routine-vs-binding acknowledgement split, the verified résumé attach, and the
per-question attempt cap. This feature changes **what reaches the page and how
it is presented** — not what the app decides.

Also unchanged: the click-guard denylist, "the applicant performs every submit",
`engine/` never importing `web/`, and secrets never appearing in any message,
log or diagnostic.
