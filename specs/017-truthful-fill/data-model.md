# Data Model: Feature 017 — The Truthful Fill

**Date**: 2026-07-28 · **Plan**: [plan.md](./plan.md) · **Research**: [research.md](./research.md)

All schema changes are **additive**. Existing rows remain valid; every new
column defaults to NULL/empty, which is semantically "unknown → leave the
field alone and flag it" (FR-023).

---

## 1. `user_profile` — additive columns (R11)

Single row, `id = 1`. Added through `db._MIGRATIONS["user_profile"]` and
registered in `db._PROFILE_COLUMNS`. All `TEXT`.

### 1a. Identity

| Column | Answers tag | Notes |
|---|---|---|
| `preferred_name` | `preferred_name` | Blank ⇒ the field is flagged, **not** back-filled with the legal name |
| `middle_name` | `middle_name` | |
| `pronouns` | `pronouns` | Canonical set: `He/him`, `She/her`, `They/them`, `Prefer not to say`, or free text |

### 1b. Address and location

| Column | Answers tag |
|---|---|
| `address_line1` | `location_address1` |
| `address_line2` | `location_address2` |
| `city` | `location_city` |
| `state_region` | `location_state` |
| `postal_code` | `location_postal` |
| `country` | `location_country` |
| `current_location` | `location_full` — display form, e.g. `Arlington, TX, USA`; derived from the parts when blank |

`target_locations` (existing) remains **search-only** and is never used to fill
a form — it is a preference list, not the applicant's address.

### 1c. Work authorization detail

| Column | Answers tag | Notes |
|---|---|---|
| `work_auth_type` | `work_auth_status` | e.g. `US Citizen`, `Permanent Resident`, `F-1 STEM OPT`, `H-1B` |
| `work_auth_expiry` | `work_auth_expiry` | The answer to "when does it expire?" — a date or `N/A`, never `Yes` |
| `work_auth_extensions` | `work_auth_extensions` | The answer to "list any extension options" |
| `sponsorship_future` | `sponsorship_requirement` | Whether sponsorship will be needed later; distinct from today's authorization |
| `sponsorship_detail` | `sponsorship_detail` | The answer to "provide additional detail about your sponsorship needs" |

Existing `authorized_without_sponsorship` and `visa_status` are retained;
`authorized_without_sponsorship` keeps driving the yes/no derivation, now only
for yes/no-shaped controls (R7).

### 1d. Preferences

`desired_salary`, `earliest_start_date`, `notice_period`,
`willing_to_relocate`, `remote_preference`, `willing_to_travel`.

### 1e. Experience facts

`years_experience`, `current_employer`, `current_title`, `highest_education`,
`graduation_month`, `graduation_year`, `gpa`.

### 1f. Links

`github_url`, `other_url`. Existing `portfolio_url` keeps its meaning; the
Lever adapter's `urls[GitHub] → portfolio_url` mapping is retightened to
`github_url`.

### 1g. Voluntary self-identification (D1)

`selfid_gender`, `selfid_race`, `selfid_veteran`, `selfid_disability`,
`selfid_orientation`.

**Semantics — three distinct states, never collapsed:**

| Stored value | Meaning | Fill behaviour |
|---|---|---|
| `""` (blank) | not provided | field untouched, flagged needs-you |
| `Prefer not to say` | explicitly declined | the equivalent decline option is selected |
| a canonical value | provided | the equivalent option is selected |

These values are entered by the applicant only. They are **never** inferred
from the résumé, the answer bank, or any model output.

### 1h. Defaults

`how_heard_default` — answers `how_heard`, the "How did you hear about this
job?" dropdown left unanswered in the live run.

### 1i. Latent fix

`target_titles` is added to `_PROFILE_COLUMNS` so `profile_import` stops
silently dropping it (C20).

---

## 2. `ai_drafts` — one row per question (R3)

Existing columns: `id, job_id, question, draft_text, status, tier, created_at`.

**Changes:**

- New `UNIQUE(job_id, question)` index; writes become upserts, so a question
  can never accumulate 15 rows.
- New columns `attempts INTEGER`, `reason TEXT`, `updated_at TEXT`.
- `status` vocabulary extended: `drafted` (existing), `needs_you`, `refused`,
  `confirmed`, `auto_saved` (existing), `discarded` (existing).
- Used to rehydrate the in-memory drafter records for the active job on start,
  so a restart does not re-draft an answered form.

---

## 3. `answer_bank` — provenance is load-bearing (R22, FR-046)

No schema change. The existing `source` column carries the distinction the
purge action depends on:

| `source` | Written by | Removed by "reset learned answers"? |
|---|---|---|
| `ai` | drafter auto-save after a successful generation | **Yes** |
| `auto_saved` | as-submitted capture on job completion | Yes |
| `user` | Profile page, answer-bank editor, **and D7 panel capture** | No |
| `confirmed` | user confirmation of a draft | No |

D7-captured answers are written with `source = 'user'` (FR-046) so a purge of
fabricated answers never destroys what the applicant typed themselves.

---

## 4. Field descriptor — additive shape information

| Field | Change |
|---|---|
| `type` | new value `"checkbox_group"` (alongside the existing `"radio_group"`) |
| `members` | reused for checkbox groups: `[{je_idx, label}]` |
| `widget` | inherited by any input surviving inside a choice-widget ancestor (R8) |
| `options` | populated for merged checkbox groups from member labels |

A merged group's `je_idx` is the **first member's**, matching the 016 radio
rule, so the `(doc, je_idx)` ledger key stays stable across scans.

**Elimination rule (R8):** a candidate element is discarded when an ancestor is
also a captured field *and* that ancestor is a choice widget. The wrapper is
the field; its nested search input is part of the widget.

---

## 5. `FillItem` — additive fields (R19)

| Field | Type | Purpose |
|---|---|---|
| `filename` | `str \| None` | the real name of an attached file (FR-031) |
| `mime` | `str \| None` | expected content type, used for verification (FR-030) |

`kind` is **unchanged** — no new value is introduced. A merged checkbox group
emits one existing `kind:"checkbox"` item per selected member, so older
companions cannot mis-fill and the exact-version gate needs no new entry.

---

## 6. Drafter record — state machine

```
                    ensure(tag not generatable)
   (absent) ─────────────────────────────────────► failed/never_generated
       │                                                    │ (terminal)
       │ ensure(generatable)
       ▼
    drafting ──── validate ok ────► done ──► answer cached, bank saved
       │                                     (no sibling backoff reset — R1)
       │ validate fails / generator error
       ▼
    failed(reason, attempts+1, next_retry_at)
       │                    │
       │ attempts < CAP     │ attempts == CAP  ──► failed(attempts_exhausted)
       │ and retry due                                (terminal, needs-you)
       └──► drafting
```

**Reason vocabulary**

| Reason | Retryable | Surfaces as |
|---|---|---|
| `empty` | yes, until the cap | drafting |
| `no_valid_option` | yes, until the cap | needs you |
| `not_an_option_label` | yes, until the cap | needs you |
| `wrong_shape` *(new)* | yes, until the cap | needs you |
| `cannot_answer` *(new)* | **no** | needs you |
| `sensitive` | no | needs you |
| `never_generated` *(new)* | no | needs you |
| `profile_fact_missing` | no | needs you |
| `attempts_exhausted` *(new)* | no | needs you |
| `job_budget_exhausted` *(new)* | no | needs you |

Only an explicit user "Fill again" clears backoff, and it never clears a
non-retryable reason.

---

## 7. Tag vocabulary

**Existing (20), retained**: `login_password`, `login_email`,
`work_authorization`, `sponsorship_requirement`, `eeo_disclosure`,
`cover_letter`, `resume_upload`, `years_experience`, `salary_expectation`,
`how_heard`, `school`, `location_city`, `linkedin_url`, `portfolio_url`,
`first_name`, `last_name`, `full_name`, `phone`, `email`, `free_text_unknown`.

**Added — identity and location**: `preferred_name`, `middle_name`,
`pronouns`, `location_state`, `location_postal`, `location_country`,
`location_address1`, `location_address2`, `location_full`, `github_url`.

**Added — work authorization detail**: `work_auth_status`,
`work_auth_expiry`, `work_auth_extensions`, `sponsorship_detail`.

**Added — self-identification (never generated)**: `selfid_gender`,
`selfid_race`, `selfid_veteran`, `selfid_disability`, `selfid_orientation`.
`eeo_disclosure` is retained as the catch-all for unrecognised EEO wording.

**Added — factual history (never generated, R6)**: `applied_before`,
`worked_here_before`, `prior_industry_experience`, `completed_course`,
`offer_deadlines`, `residency_state`, `currently_employed`,
`criminal_history`, `references`.

**Added — library facts**: `age_18_plus`, `non_compete`,
`security_clearance`, `background_check`, `drug_test`, `start_date`,
`notice_period`, `relocate`, `remote_preference`, `travel`, `degree`, `gpa`,
`graduation_date`.

**Added — consent**: `acknowledgement` with a binding/routine sub-classification
(R16). Binding is never answered.

**Never-generated set** = self-identification ∪ factual history ∪
`criminal_history` ∪ `references` ∪ binding `acknowledgement` ∪ the existing
sensitive tags.

---

## 8. Canonical vocabulary families (R14)

Each family maps a canonical value to the surface forms a form may use.

| Family | Canonical values (abbreviated) |
|---|---|
| `yes_no` | `Yes`, `No` — surfaces include `Y`/`N`, `Yes, I am authorized…`, `No, I do not…` |
| `gender` | `Man`, `Woman`, `Non-binary`, `Prefer not to say` — surfaces include `Male`, `Female`, `M`, `F` |
| `race` | US EEO categories — surfaces include slash/comma variants (`Hispanic/Latino` ↔ `Hispanic or Latino`) |
| `veteran` | `Protected veteran`, `Not a protected veteran`, `Prefer not to say` |
| `disability` | `Yes`, `No`, `Prefer not to say` — surfaces include the long CC-305 phrasings |
| `orientation` | `Straight`, `Gay`, `Lesbian`, `Bisexual`, `Prefer not to say` — surfaces include `Heterosexual` |
| `pronouns` | `He/him`, `She/her`, `They/them`, `Prefer not to say` — surfaces include `He/him/his` |
| `work_auth` | `Yes`, `No` — **strictness unchanged**; only exact/prefix surfaces, no loose synonyms |
| `education_level` | `High school`, `Associate`, `Bachelor's`, `Master's`, `Doctorate` — surfaces include `BS`, `B.S.`, `MS`, `PhD` |
| `remote_pref` | `Remote`, `Hybrid`, `On-site`, `No preference` |
| `decline` | `Prefer not to say` — surfaces include `I don't wish to answer`, `Decline to self-identify`, `I do not wish to disclose` |

Matching is **exact on canonical form**; it adds no fuzziness to
`match_option`'s existing three passes.

---

## 9. Resume attachment resolution (R18, D6)

```
resume_upload field
   │
   ├─ job.tailor_json is non-empty  ──► data_dir()/tailored/<job_id>.pdf
   │                                    (the document the applicant tailored)
   └─ otherwise                     ──► profile.resume_file_path
                                        (the applicant's own upload)
```

The resolved path's basename travels to the page as `FillItem.filename`; the
bytes are verified before attachment (PDF magic bytes, non-zero length, size
within tolerance of the declared size). Verification failure attaches nothing
and reports the field as needing the user — never a placeholder.

---

## 10. Answer (transport shape)

Carried by the new `answers` message (contract in
`contracts/bridge-protocol-additions.md`):

| Field | Meaning |
|---|---|
| `je_idx` | the field it belongs to, when known |
| `question` | the question as the form asks it |
| `answer` | full text — not the 120-character preview used by the activity log |
| `state` | `filled` \| `drafted` \| `needs_you` \| `refused` |
| `reason` | the drafter reason vocabulary above, when `state` is not `filled` |
| `askable` | true when the panel should offer an input to capture the answer (D7) |
