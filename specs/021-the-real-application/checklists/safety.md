# Safety Checklist: The Real Application

**Purpose**: This feature opens two new places private data could leak (page
reports, learned answers) and touches the fill layer. These are the items that
must hold before v2.1.0 is tagged.
**Created**: 2026-08-02
**Feature**: [spec.md](../spec.md) · [contracts/observed_answer.md](../contracts/observed_answer.md) · [contracts/page_report.md](../contracts/page_report.md)

## Secrets and private data

- [ ] CHK001 A page report contains no field value at any nesting depth, only the `has_value` boolean
- [ ] CHK002 A page report records `url_host` only — never a path, query string, fragment or token
- [ ] CHK003 A page report contains no credential, secret, cookie or authorization string
- [ ] CHK004 The report refusal test is paired with a substance test, so a builder that emits nothing cannot pass
- [ ] CHK005 An observed answer is refused for every credential and secret tag
- [ ] CHK006 An observed answer is refused for every `selfid_*` tag
- [ ] CHK007 An observed answer is refused for national identifier, date of birth, government identifier and financial questions — matched by tag **and** by question text
- [ ] CHK008 Refusal happens before the value is copied anywhere, including before any log statement
- [ ] CHK009 A refused value appears in no log, no report, no diagnostic and no database row
- [ ] CHK010 The deny-list reuses the existing vocab patterns rather than introducing a second, divergent list
- [ ] CHK011 `tests/test_secret_hygiene.py` covers both new surfaces and still passes
- [ ] CHK012 The doctor/diagnostics endpoint still never renders the pairing secret

## Truthfulness of what gets typed

- [ ] CHK013 A history request for section index *i* returns `None` when fewer than *i+1* entries exist — never entry 0, never the nearest
- [ ] CHK014 A missing GPA, employer or date is flagged for the applicant, never substituted
- [ ] CHK015 A profile fact is never written from an observed value without an explicit click
- [ ] CHK016 An observed answer never overwrites a `user`, `confirmed` or `auto_saved` row
- [ ] CHK017 Tailoring still refuses to invent employers, projects, degrees, metrics or tools

## The automation line (unchanged, and proven so)

- [ ] CHK018 No new `.click(` site is introduced in `extension/content/filler.js`
- [ ] CHK019 The final Submit / Apply / Create account / pay control is never clicked
- [ ] CHK020 CAPTCHA is never interacted with
- [ ] CHK021 Nothing is ever clicked on LinkedIn
- [ ] CHK022 The click-guard tests are extended, never weakened or edited to pass
- [ ] CHK023 019's outstanding T076 is performed on a frozen build before the tag

## Offline and cost

- [ ] CHK024 The app is fully functional with no cloud key and no network
- [ ] CHK025 Bulk background work never consumes the cloud tier's daily budget
- [ ] CHK026 A cloud failure, timeout or rate-limit falls back to on-device with no applicant action
- [ ] CHK027 No new dependency requires payment, a card or a trial
- [ ] CHK028 Every new ingest source obeys the 1 req/sec per-domain limit and bypasses no bot protection

## Notes

CHK004 and CHK009 exist because of this project's own history: a
string-presence assertion was once a control's only coverage, and a
one-directional test passed against a function that did nothing. Every refusal
item here needs its positive counterpart.
