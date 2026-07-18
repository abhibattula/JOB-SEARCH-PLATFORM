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
  - The **evidence** (approval count, exact JD phrase) is on the job's detail
    page.
- **Match** — 0–100 resume fit, sorted best-first by default. `—` means not
  scored yet (no resume uploaded, no LLM key, or the model output failed
  validation — the job stays visible either way).

## Filters and views

- **Today / This week / All** — recency windows using the source's posting
  date (falling back to when this app first saw the job).
- **Location contains… / Remote only** — narrowing only; nothing is ever
  silently hidden by your saved preferences.
- **Entry-level only / All levels** — the default feed hides senior roles;
  switch to All levels to see everything a source returned.
- **Saved / Applied / Hidden** (top navigation) — your marked jobs.
  Marking **Applied** or **Hidden** removes a job from the default feed
  permanently (refreshes never reset statuses). **Saved** keeps it in the feed
  with a marker.
- **CSV ↓** — downloads exactly the current filtered view.

## Your profile (unlocks scoring)

1. Get a free API key at **console.groq.com** (no card) and put it in `.env`
   as `LLM_API_KEY=...`. Any OpenAI-compatible endpoint works — change
   `LLM_BASE_URL`/`LLM_MODEL` to swap providers (e.g., local Ollama:
   `LLM_BASE_URL=http://localhost:11434/v1`).
2. Open **Profile**, upload your resume PDF, optionally set preferred
   locations (they pre-fill the location filter, never exclude jobs).
3. Scores and gap analysis appear on newly refreshed entry-level jobs. Scoring
   is throttled (~28 calls/min) and capped per refresh (`MAX_SCORE_PER_RUN`,
   default 150) to stay inside the free tier.

Your resume text never leaves your machine except inside the scoring calls to
the LLM provider you configured.

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
- **LinkedIn**: set `JOBSPY_LINKEDIN=1` to try it (expect blocks).

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
