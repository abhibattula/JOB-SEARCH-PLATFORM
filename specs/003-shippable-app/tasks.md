# Tasks: 003 Shippable App

- [x] W2-1 RED: min_score db + API tests → GREEN: `query_jobs(min_score=)`, param plumbing, toolbar dropdown, "Best matches" nav tab
- [x] W1-1 RED: settings precedence/masking/test-endpoint tests → GREEN: `engine/settings.py` + `settings` table, consumers switched (matcher, jobspy, scoring cap, scheduler)
- [x] W1-2 Settings page (`/settings`) with masked key, provider override, toggles, live "Test key" (HTMX snippet / JSON dual response)
- [x] W1-3 First-run welcome block on the feed (resume + key + refresh steps)
- [x] W1-4 Bundled USCIS data (`assets/uscis/`) with background auto-load on first run (tested)
- [x] W1-5 Test isolation hardening: autouse per-test DB fixture (no test can touch data/jobs.db); schema-resilient setting reads for pre-003 databases
- [x] W3-1 RED: paths tests → GREEN: `engine/paths.py` (`data_dir`, `resource_path`), wired into db/pipeline/cli/web; desktop passes the app object to uvicorn
- [x] W4-1 `APP_VERSION` + UI footer
- [x] W4-2 `packaging/jobengine.spec` (onedir, datas, uvicorn hidden imports, macOS BUNDLE)
- [x] W4-3 `packaging/windows.iss` (per-user install allowed, Start menu, uninstaller) + `packaging/make_dmg.sh`
- [x] W4-4 `.github/workflows/ci.yml` (pytest on push) + `release.yml` (tag → tested Windows exe installer + macOS dmg on the Release)
- [x] W4-5 Local frozen build + smoke test (fresh JOBS_DATA_DIR: serves, bundled USCIS bootstraps, clean shutdown)
- [x] D-1 Docs: README install section, docs/RELEASING.md, USER_GUIDE/MANUAL settings + best-matches
- [x] D-2 Spec 003 artifacts; memory update; restart the running desktop app on the new code
- [ ] D-3 (USER) Publish to GitHub + tag v0.3.0 per docs/RELEASING.md — produces both installers on the Release page
