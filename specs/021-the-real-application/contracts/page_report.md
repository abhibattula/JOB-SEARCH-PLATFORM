# Contract — page report (the shareable diagnostic)

**Module**: `engine/autofill/page_report.py` (pure; no I/O, no `web/` import)
**Written by**: `web/routes_api.py` → `data/reports/page-<ISO timestamp>.json`
**Read by**: the Diagnostics page (list + download)

## Purpose

Answer "what is actually on this page and what did the app decide about each
field?" without ever recording what the applicant typed. It is the artefact to
attach to any future "it didn't fill" report, and it is what Workstream A uses
to build the real Workday fixture instead of an imagined one.

## Shape

```json
{
  "captured_at": "2026-08-02T18:04:11Z",
  "app_version": "2.1.0",
  "protocol_v": 1,
  "ats": "workday",
  "url_host": "intel.wd1.myworkdayjobs.com",
  "counts": {"seen": 156, "filled": 5, "needs_you": 149, "sections": 12},
  "fields": [
    {
      "tag": "input", "type": "text", "widget": "", "role": "",
      "name": "country", "id": "input-23",
      "automation_id": "countryDropdown",
      "label_text": "Country/Region",
      "section_label": "Address", "section_index": 0,
      "visible": true, "required": true, "has_value": false,
      "decision": "skip", "tag_classified": "location_country",
      "reason": "profile_fact_missing"
    }
  ]
}
```

## Hard exclusions

The report **must not** contain, at any nesting depth:

- any field `value`, `placeholder` **content that was typed**, or option text
  the applicant selected
- any secret, credential, token or password
- the full page URL — **host only**. A full ATS URL routinely carries a
  session or candidate token
- any `Authorization` header, cookie, or storage contents

`has_value` is a **boolean**. That is the entire signal the report carries
about content, and it is what makes the file safe to share unmodified.

## Determinism

Field order is document order. `captured_at` is the only non-deterministic
value, and it is supplied by the caller — `page_report.build()` itself takes it
as an argument, so the builder is a pure function and its tests need no clock
freezing.

## Test requirements

Both directions, per the project rule that a one-directional assertion is no
coverage at all:

1. **Refusal**: build a report from descriptors carrying values, secrets, a
   full URL with a query string, and credential fields — assert none of those
   strings appear anywhere in the serialized output.
2. **Substance**: assert the report *does* contain the identity, shape,
   section and decision of every descriptor it was given, so the refusal test
   cannot be satisfied by a builder that emits nothing.
3. **Round trip**: the report is valid JSON, re-readable, and every
   `fields[]` entry carries the full key set even when values are empty.
