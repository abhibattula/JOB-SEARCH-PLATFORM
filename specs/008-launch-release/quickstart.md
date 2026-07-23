# Quickstart — verifying Feature 008 (Launch Release)

Two verification contexts matter this release: dev (uvicorn + browser) and
the **frozen pywebview shell** — the second is mandatory; it's where 007's
defects hid.

## Dev loop

```powershell
.venv\Scripts\python -m pytest -q          # full suite green ×2
.venv\Scripts\python desktop.py            # real shell, dev code
```

## Shell walkthrough (release gate — run in the frozen build)

1. **Shell trust**: drag-select a job title and Ctrl+C it; click Copy link
   on a feed row (toast + paste elsewhere); Open posting → system browser;
   download a tailored resume PDF; every action confirms visibly.
2. **Apply Assist**: save 2 jobs → Start. Edge window opens < 15 s, no
   download step ever appears. Kill Edge mid-run → interrupted banner →
   Resume works. Rename Edge+Chrome away (or use preflight endpoint) →
   specific "no supported browser" error, queue refuses to start.
3. **Freshness**: default window shows "2 weeks"; every visible posted
   date ≤ 14 days or marked approximate; remove a watchlist company's job
   (or pick one known-closed) → next refresh marks it delisted.
4. **Sort/paging**: flip sort to newest — instant, filters preserved; page
   past 100 results; filter by source.
5. **Profile**: upload resume into empty profile → name/email/phone/links
   fill; re-upload with a field hand-edited → keep-or-replace prompt;
   derived search terms visible/editable; edit them + set target location
   → refresh uses them (check refresh strip/jobspy terms).
6. **AI**: no key → jobs still ranked (semantic, offline); with Groq key →
   extraction uses strict-JSON model; Settings shows ≥2 provider presets
   with limits.
7. **Update**: on previous version, Check for updates → banner → Update →
   progress bar → silent install → relaunch → What's New shown once; data
   intact (jobs, profile, watchlist edits). `data_dir()/backup/` contains
   the pre-migration DB.
8. **Diagnostics**: all self-checks pass with timings; break one (e.g.,
   no network) → real error text; Export logs produces a zip; legacy
   browser cleanup reclaims space.

## Frozen build + smoke test

```powershell
.venv\Scripts\python -m PyInstaller packaging\jobengine.spec --noconfirm
.venv\Scripts\python packaging\smoke_test.py   # now also: embeddings selftest,
                                               # update-check dry run, version triple-match
```

Release: merge → tag v0.8.0 → both CI installers green → verify BOTH
artifacts on the Release page (v0.6.0 lesson) → install over v0.7.0 on the
user's machine via the new in-app updater.
