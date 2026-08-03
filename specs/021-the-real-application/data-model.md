# Data Model — Feature 021 "The Real Application"

Entities this feature introduces or extends. Storage stays SQLite at
`data/jobs.db` plus files under `data/reports/`; no new database, no new
top-level store.

---

## Extended: `user_profile.resume_sections` (JSON column)

Already exists and is already populated by `engine/resume_extract.py`. Two
entry types gain optional fields. **All new fields default to empty**, so every
profile stored by v2.0.0 remains valid and no migration of existing rows is
required.

### ExperienceEntry

| field | type | new | notes |
|---|---|---|---|
| `title` | str | | job title |
| `organization` | str | | employer name |
| `start` | str | | free-form as parsed; normalized at fill time |
| `end` | str | | empty when current |
| `bullets` | list[str] | | not used by the fill layer |
| `location` | str | **new** | city/state of that role |
| `is_current` | bool | **new** | drives "I currently work here" |

### EducationEntry

| field | type | new | notes |
|---|---|---|---|
| `degree` | str | | e.g. "B.S. Computer Engineering" |
| `institution` | str | | school name |
| `start` | str | | |
| `end` | str | | graduation date when known |
| `details` | str | | free text |
| `field_of_study` | str | **new** | separated from `degree`; ATSs ask for both |
| `gpa` | str | **new** | string, not float — "3.6", "3.6/4.0", "First Class" |

**Rule (FR-013)**: a request for section index *i* returns `None` when
`len(entries) <= i`. Never entry 0, never the nearest entry.

---

## Extended: profile facts (inside `user_profile.preferences`)

New keys, all optional, all resolved through the existing
`profile_answers._DIRECT` mapping:

| key | tag | why |
|---|---|---|
| `phone_country_code` | `phone_country_code` | seen on the applicant's Workday page as "Country/Region Phone Code*" |
| `address_line2` | `location_address2` | already a tag, no stored fact behind it |
| `work_auth_expiry` | `work_auth_expiry` | already a tag, no stored fact |
| `security_clearance` | `security_clearance` | asked by every defence-adjacent employer |
| `drivers_licence` | `drivers_licence` | common yes/no |

---

## New: Form section (transient, never stored)

Carried on each field descriptor inside the existing `form_context` channel.
Additive under `PROTOCOL_V` 1 — an older app ignores the new keys.

| field | type | notes |
|---|---|---|
| `section_label` | str | resolved name, `""` when undetermined |
| `section_index` | int | 0-based ordinal among repeats of the same label |

**Recomputed on every scan** from DOM ancestry (R2). Never stamped onto an
element — a stamped index drifts on the React remounts that caused the
original flood.

### Pruning window

A field is evicted from the page index after it has been absent from **3
consecutive scans** of the same document. One missed scan is a re-render, not
a removal; evicting on the first miss would make live fields flicker out of
the review list exactly when the page is busiest.

---

## New: Page report (file, `data/reports/page-<timestamp>.json`)

A shareable, **value-free** description of one application page.

| field | type | notes |
|---|---|---|
| `captured_at` | ISO 8601 str | |
| `ats` | str | detected adapter, `""` when unknown |
| `url_host` | str | **host only** — never the full URL, which can carry tokens |
| `counts` | object | `seen`, `filled`, `needs_you`, `sections` |
| `fields[]` | array | one entry per descriptor |

Each `fields[]` entry:

| field | type | notes |
|---|---|---|
| `tag`, `type`, `widget`, `role` | str | shape |
| `name`, `id`, `automation_id` | str | identity |
| `label_text` | str | the resolved question |
| `section_label`, `section_index` | str, int | |
| `visible`, `required`, `has_value` | bool | `has_value` is a **boolean**, never the value |
| `decision`, `tag_classified`, `reason` | str | what the app did and why |

**Never present**: any `value`, any secret, any credential, any full URL, any
`Authorization`-bearing string. Asserted in both directions by
`tests/test_secret_hygiene.py`.

---

## Extended: `answer_bank` (existing table, no schema change)

The `source` column already exists and already distinguishes provenance. This
feature adds one value.

| provenance | written by | may be overwritten by |
|---|---|---|
| `user` | the applicant, in the app or the panel | the applicant only |
| `confirmed` | `drafts.py` on acceptance | the applicant only |
| `auto_saved` | `drafts.py` auto-accept | the applicant, `confirmed` |
| `model` | `drafter.save_auto` | anything |
| **`observed`** | **new** — read off a page the applicant filled | the applicant, `confirmed`, `auto_saved`, and later `observed` |

**Write rule (FR-019)**: an `observed` row is written only when no row exists
for that normalized question, or the existing row's provenance is itself
`observed`. `question_normalized` stays `UNIQUE`; no migration.

---

## Extended: `application_answers` (existing table, no schema change)

Already the immutable per-application snapshot. An observed answer records here
too, so the Learned answers page can show which application taught it.

---

## New: AI tier preference (settings key)

| key | values | default |
|---|---|---|
| `AI_INTERACTIVE_TIER` | `"cloud"` \| `"local"` | `"cloud"` when a key is saved, else `"local"` |

Replaces the discoverability failure of `PREFER_LOCAL_LLM`, which is retained
and honoured for **bulk background work only**. Bulk never uses the cloud tier
(FR-024) — the free tier's ~1K/day budget is reserved for what the applicant is
waiting on.

---

## New: Panel placement (extension storage, not the database)

`chrome.storage.local` key `je_panel_pos` → `{right: int, bottom: int}`, CSS
pixels from the viewport's right and bottom edges. Clamped into the current
viewport on every restore (FR-028). Absent means the default corner.

Stored in the extension, not the app: the panel must restore before the app is
reachable, and it must be the same position on every employer's domain — which
rules out `localStorage`.
