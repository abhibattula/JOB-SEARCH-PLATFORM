# Patch 0.6.0: Profile overhaul — identity fields, Common Questions, credential default, skills-driven matching

**Requested**: 2026-07-20 — after fixing the v0.5.6 Apply Assist bug, the
user reported the feature still didn't feel like it worked as expected:
"there are no questions in profile section" (nothing to pre-fill), and
asked for the Profile tab to become "more detailed, like a job
application" so answers filled once get reused everywhere and also help
matching, plus a rethink of the credential model since "the user id
password or email id password will be same for every domain."

## Design decisions (user-confirmed via clarifying questions)

1. **Profile layout**: one page, sectioned — Basic Info → Work
   Authorization → Common Questions → Resume/Locations. (Recommended
   option, accepted.)
2. **EEO-style voluntary questions** (disability, veteran status,
   race/ethnicity): add an upfront, clearly optional "EEO disclosures"
   section — a deliberate override of the recommendation to leave them out
   entirely, because the user wants them pre-fillable like everything else.
3. **Credential model**: one default login + optional per-domain
   overrides, rather than requiring a fresh save for every site.

## Root causes found while investigating "not as expected"

- `browser_controller._value_for_tag()` read `profile.get("full_name")`,
  `"email"`, `"phone"`, `"linkedin_url"`, `"portfolio_url")` — none of
  those columns existed in `user_profile`, and `first_name`/`last_name`
  (real taxonomy tags from `fields.py`) had no handling at all and fell
  through silently to the answer-bank Q&A path. These fields could never
  have been filled by Apply Assist, regardless of the browser-launch bug.
- The `answer_bank` table (sponsorship, years of experience, salary
  expectation, how-heard, EEO) already existed and was written to via
  `/api/autofill/answers/confirm`, but had no read/manage surface in the
  UI — so the user had no way to pre-fill "Common Questions" ahead of time,
  only react to Apply Assist's confirmation pauses one at a time.
- The basic (no-cloud-key) matcher only saw skills regex-extracted from
  raw resume text; a skill the user has but phrased differently (or not at
  all) in their resume couldn't be told to the matcher.
- Credentials required a full save per domain even though most users reuse
  one login everywhere.

## Changes

**A — Identity fields** (`engine/db.py`, `engine/autofill/browser_controller.py`):
`user_profile` gains `first_name`, `last_name`, `email`, `phone`,
`linkedin_url`, `portfolio_url`. `save_profile()` refactored to build its
SQL from a single `_PROFILE_COLUMNS` source of truth instead of a
hand-maintained string. `_value_for_tag()` now handles `full_name` (combines
first+last), `first_name`, `last_name`, `email`, `phone`, `linkedin_url`,
`portfolio_url` directly — these are facts, not judgment calls, so they
fill without a confirmation pause.

**B/C — Common Questions + EEO disclosures** (`engine/autofill/answer_bank.py`,
`web/routes_autofill.py`, `web/templates/partials/profile_answer_bank.html`):
added `list_all()`/`delete()` to `answer_bank.py` (the existing `save()`/
`lookup()`/`suggest()` are unchanged — `/api/autofill/answers/confirm`
remains the only write path per FR-011). New `GET /api/autofill/answers`
and `DELETE /api/autofill/answers/{bank_id}` routes. Profile page renders
every saved entry with an edit/delete control, plus a templated "EEO
disclosures (optional)" subsection (gender, race/ethnicity, veteran status,
disability status) that pre-fills from existing answer-bank entries.

**D — Credential default + per-domain override** (`engine/credentials.py`,
`web/routes_api.py`, `web/templates/settings.html`): a reserved keyring
service (`__default__`) and settings key (`cred_default_email`) hold the
default; `get(domain)` checks the domain-specific entry first, falls back
to the default. `POST/DELETE /api/credentials/default` registered **before**
`DELETE /api/credentials/{domain}` — locked in with a named regression test
since FastAPI's dynamic path param would otherwise greedily match the
literal string "default".

**E — Editable skills feed the basic matcher** (`engine/basic_match.py`,
`engine/pipeline.py`, `web/routes_api.py`): `basic_match.score()` accepts
`extra_skills` — Profile's explicit skills list, filtered to the canonical
skill dictionary, unioned with resume-text regex extraction.
`pipeline._score_new_jobs()` passes `profile["skills"]` through on the
basic tier. The `/api/profile` route merges an edited `skills` form field
with any same-request resume-extraction result — manual entries first,
deduplicated — so neither a fresh extraction nor an explicit edit is ever
silently dropped.

## Verification

TDD throughout: each phase's tests written first and confirmed failing
before implementation (`tests/test_db.py`, `tests/test_browser_controller.py`,
`tests/test_api.py`, `tests/test_answer_bank.py`, `tests/test_routes_autofill.py`,
`tests/test_credentials.py`, `tests/test_routes_credentials.py`,
`tests/test_settings.py`, `tests/test_basic_match.py`, `tests/test_pipeline.py`).
Full suite: 300 passed.

## Ship

Version bumped to 0.6.0 (`engine/__init__.py`, `packaging/windows.iss`,
`packaging/jobengine.spec`). Docs updated: `docs/USER_MANUAL.md` §5, §7,
§11.3/§11.4, §12; `docs/USER_GUIDE.md` profile + saved-logins sections.
