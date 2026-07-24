# Phase 0 Research: The Discovery Copilot

All "unknowns" here are design decisions, not missing facts — the enabling code
already exists and was read during planning. Each decision records what was
chosen, why, and the rejected alternative.

## D1. Job-page detection signal

- **Decision**: Primary = schema.org `JobPosting` JSON-LD
  (`<script type="application/ld+json">`, direct object or `@graph` member with
  `@type` including `JobPosting`), reading `title`, `hiringOrganization.name`,
  `description`. Fallback = per-host DOM extractors for `linkedin.com/jobs/view`
  and `indeed.com` (`/viewjob`, `/jobs?vjk=`), which do not always emit clean
  JSON-LD. No match → no badge.
- **Rationale**: JSON-LD is the site-agnostic standard emitted by Greenhouse,
  Lever, Ashby, and most company career pages, so one extractor covers the long
  tail for free (mirrors the app's own API-first ethos, Principle III). LinkedIn
  and Indeed are the two highest-traffic boards and warrant dedicated handling.
- **Alternatives rejected**: (a) a hand-maintained per-ATS selector map for every
  board — high upkeep, brittle, and unnecessary given JSON-LD coverage;
  (b) heuristic keyword sniffing of arbitrary pages — false positives on
  non-postings, violates "no badge on non-job pages".

## D2. Where scoring runs

- **Decision**: On demand in the **local app**, reusing `basic_match.score`
  (offline, instant) — the exact call the feed pipeline makes at
  `engine/pipeline.py:251-257`: `basic_match.score(resume_text, title,
  description, extra_skills=set(profile.get("skills") or []))`. Band label
  (Strong/Good/Fair) derived from the score.
- **Rationale**: $0 and instant (Principle II); no cloud key; identical to the
  feed's basic tier so a browsed score matches the in-app score. Keeps all logic
  in the engine (Principle IV).
- **Alternatives rejected**: (a) scoring in JS in the content script — would
  duplicate the skill dictionary and drift from the engine; (b) the LLM/semantic
  tier on demand — slower, and would need a key, breaking the instant, offline,
  $0 promise. (Cloud tier explicitly a non-goal.)

## D3. Sponsorship lookup depth (clarified)

- **Decision**: Two-tier. First `db.get_company_by_name(company)` (fast path:
  the company may already be graded in the feed → returns `sponsor_grade`,
  `cap_exempt`, `h1b_approvals`). On a miss, on-demand
  `sponsorship.match_employer(company, db.load_h1b_employers())` → `grade(...)` +
  `cap_exempt(company)`. "unknown" only when there is genuinely no evidence
  (below the petition floor) — never a fabricated grade (matches
  `apply_to_companies`' guarantee, SC-003).
- **Refactor**: extract the per-company grading block from
  `sponsorship.apply_to_companies()` (~lines 177-200) into
  `sponsorship.grade_company(name, employers=None) -> dict`, called by both the
  batch pass and `discovery.score_page`, so on-demand and batch grading cannot
  diverge (parity unit test).
- **Rationale**: maximizes coverage for freshly-browsed companies while reusing
  the exact fuzzy-join + grade formula. `load_h1b_employers()` is an in-memory
  dict already used by the batch pass; running one match per viewed posting
  (debounced) is cheap and stays off the event loop via `run_in_threadpool`.
- **Alternatives rejected**: fast-path only (most browsed companies would read
  "unknown" — poor value); precomputing every USCIS employer into `companies`
  (needless write amplification for companies the user may never save).

## D4. Bridge transport for score/save

- **Decision**: Reuse the existing authenticated `/ws/ext` companion socket. Add
  two inbound message types — `score_request` and `save_job` — to
  `ext_protocol._INBOUND` (strict pydantic, 1 MB bound already enforced), and two
  outbound envelopes via the existing `outbound()` — `score_result` and
  `save_result`. Content→app uses the existing `relayFromContent` (stamps
  `tab_id`); app→content adds two `state.onMessage` cases routing to the top
  frame via `toContent(tab_id, msg, 0)`.
- **Rationale**: no new trust boundary, no new secret (FR-015); the socket, its
  secret gate, size bound, and threadpool offload all already exist. The handlers
  are added to `ext_backend` but read nothing from `_watch`/`bc._state`, so
  discovery is fully independent of the fill session (FR-013).
- **Alternatives rejected**: a separate HTTP endpoint — would need its own auth
  and CORS handling and a second connection lifecycle; the WS bridge is already
  paired, alive, and authenticated.

## D5. Badge as a separate, read-only overlay

- **Decision**: A NEW content script `extension/content/discovery.js` renders its
  own closed-shadow-DOM host (`je-discovery-badge-host`), distinct from the fill
  overlay (`overlay.js` / `je-companion-overlay-host`). Top frame only. It reads
  posting metadata and renders the badge; it performs **no** page clicks/mutations.
- **Rationale**: reuses the proven closed-shadow-root isolation technique from
  `overlay.js` (page CSS can't reach in, our styles can't leak). A separate host
  guarantees discovery and fill never fight over one DOM node and can coexist
  (FR-013). Read-only keeps it far from the Principle III click boundary.
- **Alternatives rejected**: extending `overlay.js` — couples discovery to the
  fill session's show/hide lifecycle and the "filling" framing; a page-injected
  (non-shadow) badge — page CSS collisions and style leakage.

## D6. Disconnected / no-resume behavior (clarified)

- **Decision**: The badge renders **only** when a `score_result` arrives, so if
  the app is closed or the companion disconnected, no request is answered and no
  badge appears (zero page footprint). If the user has no resume/profile,
  `score_page` returns a neutral result flagged "add your resume", and the badge
  shows that honest prompt instead of a misleading number (FR-016).
- **Rationale**: least-intrusive, matches FR-006 and the user's clarify answer;
  avoids a dead/greyed badge on every job page when the app isn't running.
- **Alternatives rejected**: a dormant "connect me" hint on every job page —
  rejected by the user in clarify (footprint when idle).

## D7. Save semantics (clarified)

- **Decision**: Save → `db.upsert_job({title, company, url, description,
  source:"manual", ...})` then set status `saved`, so the job appears in the feed
  AND the Saved view. `upsert_job` already dedups by URL / (company,title,loc);
  a repeat save reports "already". `db.get_job_by_url(url)` powers the
  already-saved state on render.
- **Rationale**: `source="manual"` is already a valid source; dedup is already
  correct; marking `saved` matches the explicit intent (clarify answer, FR-008/009).
- **Alternatives rejected**: plain feed entry (status none) — the user rejected
  this in clarify; a new dedicated table — needless, the feed/tracker already
  models saved jobs.

## Testing strategy (confirms Principle V)

- Unit: `discovery.score_page` (score/band, sponsor grade, unknown company,
  no-resume, already_saved); `sponsorship.grade_company` parity vs.
  `apply_to_companies`; `db.get_job_by_url`.
- Protocol/backend: new inbound models validate/reject; handlers emit correct
  outbound with **no fill session set** (independence regression guard).
- Static asset: `discovery.js` present + in manifest + closed shadow root + makes
  no page `.click()` (read-only proof).
- Real browser (`-m browser`): JSON-LD + LinkedIn + Indeed fixtures each render
  the badge with the right score/company; Save upserts + dedups; existing 20
  browser tests stay green (no interference).
