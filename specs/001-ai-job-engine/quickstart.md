# Quickstart: Personalized AI Job Engine

## Prerequisites

- Python 3.11+ on PATH
- A free Groq API key (console.groq.com — no card required) for match scoring.
  The app runs without it; jobs just stay unscored.

## Setup

```powershell
# from repo root
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# configuration
copy .env.example .env
# edit .env: set LLM_API_KEY=<your groq key>
# (defaults: LLM_BASE_URL=https://api.groq.com/openai/v1, LLM_MODEL=llama-3.3-70b-versatile)
```

## Optional: sponsorship data (unlocks HIGH/MEDIUM badges)

1. Download the latest employer CSV from the USCIS H-1B Employer Data Hub
   (uscis.gov → Reports and Studies → H-1B Employer Data Hub) into `data/uscis/`.
   Direct file URLs follow the pattern
   `https://www.uscis.gov/sites/default/files/document/data/h1b_datahubexport-<year>.csv`
   (2023 verified working; add every year you can fetch — approvals accumulate).
2. Download the latest LCA disclosure file from the DOL performance data page
   into `data/dol/`.
3. Load: `python cli.py load-sponsorship`

Without this step every job shows sponsorship UNKNOWN (JD-text EXCLUDED flags
still work).

## Run

```powershell
.\run.bat        # Windows — opens the desktop app window
```
```bash
./run.sh         # macOS — or double-click run.command (chmod +x first time)
```

Server-only mode (browser at http://127.0.0.1:8000): `python app.py` (venv).

First open on an empty database: the feed shows an empty state and a refresh
starts automatically; jobs stream in over the next few minutes. Subsequent opens
render instantly from cache and only re-refresh after the 30-minute cooldown.

Headless refresh (same pipeline, no browser):

```powershell
python cli.py refresh
```

## Use

1. **Profile** page → upload your resume PDF, set preferred locations.
2. **Feed** → default view is entry-level jobs from the past 7 days, sorted by
   match score. Toggle **24h**, filter by location/remote, sort by date.
3. Mark jobs **Saved / Applied / Hidden** — Applied and Hidden leave the default
   feed; each has its own view.
4. **Job detail** → description beside match breakdown, missing skills, gap
   actions, and sponsorship evidence.

## Verify (smoke test)

```powershell
pytest                      # unit + contract tests, no network needed
python cli.py refresh       # real network pull; expect per-source counts > 0
```

Then open http://127.0.0.1:8000 and confirm: feed populates, 24h toggle narrows,
marking a job Applied removes it from the default feed, and a scored job's detail
page shows gap actions.

## Adding companies

Edit `companies.yml`:

```yaml
- name: Example Corp
  ats: greenhouse        # greenhouse | lever | ashby | workday
  slug: examplecorp      # board slug; for workday use tenant/site fields
```

Next refresh picks it up automatically.
