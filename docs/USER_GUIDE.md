# User Guide — Personalized AI Job Engine

This is the daily-use manual. For first-time setup, follow
[../specs/001-ai-job-engine/quickstart.md](../specs/001-ai-job-engine/quickstart.md).

## The daily loop

1. Run `.\run.bat` (Windows) or double-click `run.command` (Mac) — the app
   opens in its own window. (It's a local web server underneath: if you prefer
   a browser, `python app.py` with the venv still serves
   **http://127.0.0.1:8000**.)
2. The feed shows instantly from the local database. A background refresh
   starts automatically — unless one ran in the last 30 minutes — and new jobs
   stream into the list with a green **new** flag. No reload needed.
3. Scan, open, apply, and mark each job as you go. Done.

## Reading the feed

- **Channel strip** (top of the feed): per-source status for the current or
  last refresh — `✓ greenhouse 41` means done with 41 new jobs, `▸` running,
  `✕` failed (other sources keep going; one bad source never blocks the rest).
- **Sponsor badge** per job:
  - `HIGH` — the JD offers sponsorship outright, or the company has a strong
    H-1B approval history (≥25 recent approvals)
  - `MEDIUM` — some approval history, JD silent
  - `EXCLUDED` — the JD refuses sponsorship or demands citizenship, a security
    clearance, or ITAR "U.S. person" status. **These never appear in your
    normal feed** — you can't get them, so they don't waste your time. The
    **Ineligible** tab shows them with the exact wording that triggered the
    exclusion, in case you want to audit a call.
  - `UNKNOWN` — no signal either way (also what you get before loading the
    USCIS data)
  - **Sponsor grade** (A–F, next to the badge): a local grade from real
    USCIS approval/denial history, engineering filings, and DOL wage
    levels. Only companies with 10+ petitions get graded — below that it
    stays UNKNOWN rather than guessing. **cap-ex** marks likely cap-exempt
    employers (universities, nonprofit research, hospitals) that can
    sponsor year-round outside the H-1B lottery.
  - **Strong sponsors only** (toolbar) narrows the feed to grade ≥ B or
    cap-exempt employers.
  - The **evidence** (approvals, denials, approval rate, wage level,
    lottery-odds hint, exact JD phrase) is on the job's detail page.
- **Match** — 0–100 resume fit, sorted best-first by default. `~62` (tilde) is
  the built-in **basic keyword match**; `•71` (dot) is the **bundled offline
  AI model** — both work with zero setup and upgrade automatically to a full
  cloud score once you add a key. `—` means not scored yet (no resume
  uploaded, or the model output failed validation — the job stays visible
  either way).

## Filters and views

- **Today / This week / All** — recency windows using the source's posting
  date (falling back to when this app first saw the job).
- **Location contains… / Remote only** — narrowing only; nothing is ever
  silently hidden by your saved preferences.
- **Entry-level only / All levels** — the default feed hides senior roles;
  switch to All levels to see everything a source returned.
- **New today** (top navigation) — everything the engine discovered in the
  last 24 hours, best matches first. Pair it with desktop notifications
  (Settings) and you'll be among the first applicants.
- **Saved / Applied / Hidden** (top navigation) — your marked jobs.
  Marking **Applied** or **Hidden** removes a job from the default feed
  permanently (refreshes never reset statuses). **Saved** keeps it in the feed
  with a marker.
- **Applied is your pipeline**: each row gets a stage dropdown
  (applied → OA → interview → offer/rejected) and inline notes; rows quiet for
  7+ days get a ⚑ **follow up** flag. Switch to the **Board** view for a
  kanban of stage columns — drag cards between stages or use each card's
  ◀/▶ buttons. **Analytics** shows your funnel and which sources and score
  bands actually produce callbacks.
- **Tailor for this job** (on a job's detail page) — generates resume bullets
  rewritten in that posting's language, a short cover letter, and ATS keywords,
  from your real resume only. Click any block to copy it — or download the
  **tailored resume PDF** and **cover-letter PDF** (ATS-safe, rendered
  offline from your Resume builder sections + the tailoring).
- **Theme**: Settings → Theme switches between the light "datasheet" look
  and the dark "scope screen"; your choice persists and overrides the OS
  preference.
- **CSV ↓** — downloads exactly the current filtered view.

## Your profile (fill it once, reuse everywhere)

1. Open **Profile** — one page, sectioned: Basic info (name, email, phone,
   LinkedIn, portfolio), Work authorization, Common Questions (+ optional
   EEO disclosures), and Resume & job search. Fill it in once; Apply Assist
   and the matcher both reuse it from then on.
2. Upload your resume PDF and optionally edit the **skills** field —
   anything the automatic extraction missed still counts toward matching,
   especially without a cloud AI key. Set preferred locations (they pre-fill
   the location filter, never exclude jobs). Scores and gap analysis appear
   on newly refreshed entry-level jobs immediately — the bundled offline AI
   model needs no setup at all.
   The **Resume builder** section fills itself from your upload (experience,
   education, projects, skills) — review and correct it once; those sections
   become your tailored resume PDFs. Re-uploading a new resume later *asks*
   whether to keep your edits or re-extract; it never overwrites silently.
3. Pre-fill **Common Questions** (sponsorship, years of experience, salary
   expectation, how you heard about the role, and — optionally — the
   standard EEO gender/race/veteran/disability questions) so Apply Assist
   has answers ready instead of pausing to ask on your first few
   applications.
4. Optional: get a free API key at **console.groq.com** (no card required),
   then open **Settings**, paste it, and click **Test key** to confirm it
   works. (Advanced: the Settings page can point at any OpenAI-compatible
   provider — e.g., local Ollama at `http://localhost:11434/v1`.) A `.env`
   file still works as a developer override. This upgrades every score to
   full cloud-quality analysis automatically — you don't lose anything by
   adding a key later.
5. Scoring is throttled (~28 calls/min for the cloud tier) and capped per
   refresh to stay inside the free tier. Use the **Best matches** tab (or
   the "Match: 70+" toolbar filter) to browse only strong fits.

Your resume text never leaves your machine except inside scoring calls to a
cloud provider you've explicitly configured — the bundled model runs fully
offline.

## Apply Assist (auto-fill applications)

1. Save jobs you want to apply to (☆ in the feed), then open **Apply
   Assist** from the top nav.
2. Nothing to download: Apply Assist uses the Edge or Chrome already on
   your machine (with its own separate profile). **Check my browser**
   verifies it can start.
3. Pick your saved jobs (select all/none buttons) and **Start Apply
   Assist**. A dedicated browser window (separate from your everyday
   browser) opens on the first job's application page with recognized
   fields already filled from your Profile and answer bank — including
   **your resume file** (the job's tailored PDF when one exists), and
   dropdowns answered by matching the site's own option wording.
4. **You always click the site's own submit/next/login button — the app
   never does.** The mission panel shows the whole queue ("3 of 8"), and a
   per-field report of exactly what was filled (passwords show only as
   `•••`). When *you* click Next on a multi-page form, the new page fills
   automatically; **Re-scan this page** covers forms that redraw without
   navigating.
5. New or sensitive questions (work authorization, sponsorship, EEO-style)
   pause the queue with an AI-drafted suggestion for you to confirm or
   edit — nothing is saved or typed until you do. Answer once, reused
   automatically after that.
6. Click **Done, next application** to move to the next job — nothing
   advances on its own. Closed the browser window by accident? Your spot is
   saved — click **Resume queue**. A batch summary wraps up every run.
7. On a site the app can't confidently read (including Workday), it just
   opens the tab for you to finish manually and still advances afterward.

Optional: **Settings → Saved logins** — set one **default** email/password
(realistically the same login covers most job sites) and, only where a site
needs something different, a **per-site override** for that domain (in your
OS's own credential store, never this app's database). Apply Assist fills
matching login pages from whichever applies — again, never clicking login
itself.

## Sponsorship data (unlocks HIGH/MEDIUM badges)

- Download the latest **USCIS H-1B Employer Data Hub** export CSV(s) into
  `data/uscis/` (uscis.gov → Reports and Studies → H-1B Employer Data Hub;
  direct files follow the pattern `h1b_datahubexport-<year>.csv`).
- Optionally add **DOL LCA disclosure** files (xlsx) into `data/dol/` for
  per-title sponsorship detail.
- Load with `python cli.py load-sponsorship`. Re-run whenever you add files
  (quarterly-ish). JD-wording detection (EXCLUDED/HIGH from the text itself)
  works even without this data.

## Managing job sources

- **Add a company**: one line in `companies.yml`
  (Greenhouse/Lever/Ashby/SmartRecruiters/Workable slug), then
  `python scripts/check_seeds.py` to confirm the slug is right — a wrong slug
  fails silently as zero jobs.
- **Freshness**: postings older than 45 days that you never saved, applied to,
  or hid are pruned automatically after each refresh.
- **Workday employers** (NVIDIA, AMD, Qualcomm…): blocked for HTTP clients by
  Cloudflare as of 2026-07, so none ship by default — their roles arrive via
  the Indeed source instead. If that changes, add entries with `ats: workday`,
  `host`, `site`.
- **LinkedIn**: use the feed's **Search on LinkedIn ↗** button (a genuine
  14-day LinkedIn search in your own browser). Scraping stays opt-in in
  Settings and rate-limits quickly by nature.

## Automation

- **Refresh from a terminal/scheduler**: `python cli.py refresh` (add
  `--force` to bypass the 30-minute cooldown).
- **Nightly auto-refresh while the app runs**: set `SCHEDULE_REFRESH=1` in
  `.env` (fires 07:00 local).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Feed empty on first run | Wait for the channel strip to finish (first pull takes a few minutes), or run `python cli.py refresh` and watch the counts |
| A source shows `✕` | Check its error in `/api/refresh/status`; one source failing is tolerated by design — worth a look only if it persists for days |
| All sponsorship badges UNKNOWN | Load the USCIS data (`python cli.py load-sponsorship`) |
| No match scores | Add `LLM_API_KEY` to `.env` and upload a resume on Profile; then refresh |
| Resume upload rejected (422) | The PDF has no text layer (scanned image) — export a text PDF from your editor |
| `database is locked` / WAL errors | `JOBS_DB_PATH` must point to a **local** disk, not a network drive |
| Refresh button says "cooldown" | A refresh finished < 30 min ago — use **Refresh now** (it bypasses the cooldown) |
| Scores show `~` even though you expected `•` or a cloud score | The bundled model file may be missing/corrupted — the app degrades to the basic matcher rather than crashing; reinstalling fixes it |
| Apply Assist won't start a browser | Click **Check my browser** on the Apply Assist page — the error names the fix (usually: install Microsoft Edge or Google Chrome) |
| Apply Assist opened a job but nothing got filled | The status panel now names the exact reason (page unreadable / failed to load / fields unrecognized) — fill it manually, then click **Done, next application** |
| Something else misbehaves | Open **Diagnostics** (top nav): run the self-checks and use **Export logs** |
