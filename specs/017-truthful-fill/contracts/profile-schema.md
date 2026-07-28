# Contract: Profile schema and canonical values (feature 017)

The profile is the supply of truth that makes the refusal policy productive:
the more it holds, the less the applicant is asked. Every field is optional.
**Blank means "unknown" — the form field is left untouched and flagged, never
guessed.**

---

## 1. Form contract — `POST /api/profile`

Existing behaviour is unchanged: `multipart/form-data`, redirects to
`/profile` for HTML clients, returns the profile payload for JSON clients. All
new fields are optional form fields; omitting one leaves the stored value
untouched, and submitting it empty clears it.

### Existing fields (unchanged)

`resume` (file) · `first_name` · `last_name` · `email` · `phone` ·
`linkedin_url` · `portfolio_url` · `skills` · `target_locations` ·
`authorized_without_sponsorship` · `visa_status`

### New fields

| Form field | Section | Notes |
|---|---|---|
| `preferred_name` | Identity | blank ⇒ "Preferred name" fields are flagged, never back-filled with the legal name |
| `middle_name` | Identity | |
| `pronouns` | Identity | canonical or free text |
| `address_line1`, `address_line2` | Address | |
| `city`, `state_region`, `postal_code`, `country` | Address | |
| `current_location` | Address | display form; derived from the parts when blank |
| `work_auth_type` | Work authorization | canonical list below |
| `work_auth_expiry` | Work authorization | date or `N/A` — answers "when does it expire?" |
| `work_auth_extensions` | Work authorization | answers "list any extension options" |
| `sponsorship_future` | Work authorization | `yes` / `no` / `""` |
| `sponsorship_detail` | Work authorization | answers "additional detail about your sponsorship needs" |
| `desired_salary`, `earliest_start_date`, `notice_period` | Preferences | |
| `willing_to_relocate`, `remote_preference`, `willing_to_travel` | Preferences | |
| `years_experience`, `current_employer`, `current_title` | Experience | |
| `highest_education`, `graduation_month`, `graduation_year`, `gpa` | Experience | |
| `github_url`, `other_url` | Links | |
| `how_heard_default` | Defaults | answers "How did you hear about this job?" |
| `selfid_gender`, `selfid_race`, `selfid_veteran`, `selfid_disability`, `selfid_orientation` | Voluntary self-identification | see §3 |

### Response payload

`GET /api/profile` returns every new field verbatim. As today,
`resume_file_path` is **never** returned — only `has_resume_file: bool`.
Self-identification values are returned so the form can render them; they are
never included in diagnostics, logs, reports, or the doctor endpoint.

---

## 2. Canonical values

Stored values SHOULD be one of these, but free text is accepted and matched on
a best-effort basis.

| Field | Canonical values |
|---|---|
| `work_auth_type` | `US Citizen` · `Permanent Resident` · `F-1 OPT` · `F-1 STEM OPT` · `H-1B` · `TN` · `E-3` · `H-4 EAD` · `L-2 EAD` · `Other` |
| `sponsorship_future`, `willing_to_relocate`, `willing_to_travel` | `yes` · `no` · `""` |
| `remote_preference` | `Remote` · `Hybrid` · `On-site` · `No preference` |
| `highest_education` | `High school` · `Associate` · `Bachelor's` · `Master's` · `Doctorate` |
| `pronouns` | `He/him` · `She/her` · `They/them` · `Prefer not to say` · free text |
| `notice_period` | `Immediately` · `2 weeks` · `1 month` · `2 months` · free text |

---

## 3. Voluntary self-identification (D1)

**Three distinct states, never collapsed:**

| Stored | Meaning | Fill behaviour |
|---|---|---|
| `""` | not provided | field untouched, flagged needs-you |
| `Prefer not to say` | explicitly declined | the form's equivalent decline option is selected |
| a canonical value | provided | the form's equivalent option is selected |

| Field | Canonical values |
|---|---|
| `selfid_gender` | `Man` · `Woman` · `Non-binary` · `Prefer not to say` |
| `selfid_race` | US EEO categories · `Prefer not to say` |
| `selfid_veteran` | `Protected veteran` · `Not a protected veteran` · `Prefer not to say` |
| `selfid_disability` | `Yes` · `No` · `Prefer not to say` |
| `selfid_orientation` | `Straight` · `Gay` · `Lesbian` · `Bisexual` · `Prefer not to say` |

**Guarantees**

1. Entered by the applicant only — never inferred from the résumé, the answer
   bank, or any model output.
2. Never sent to any model, in any prompt, for any purpose.
3. Used solely to select an equivalent option on a form that asks the question.
4. Stored locally like the rest of the profile and excluded from diagnostics.
5. The UI states that these questions are voluntary and that leaving them blank
   is a supported choice.

---

## 4. The answer library

Pre-answered common questions are resolved by **classifier tag**, not by
matching question text (R13 — `answer_bank.lookup`'s `ratio ≥ 85` misses real
ATS phrasings). The Profile page renders one input per library tag; each saves
an `answer_bank` row with `source = 'user'`.

Seeded tags: `age_18_plus` · `worked_here_before` · `applied_before` ·
`prior_industry_experience` · `completed_course` · `offer_deadlines` ·
`residency_state` · `currently_employed` · `non_compete` ·
`security_clearance` · `background_check` · `drug_test` · `start_date` ·
`notice_period` · `relocate` · `remote_preference` · `travel` · `degree` ·
`gpa` · `graduation_date` · routine `acknowledgement`.

The library also grows by itself: any question the system declines to answer is
offered to the applicant in the on-page panel, and what they type is stored
here as their own answer (D7, FR-045/FR-046).

---

## 5. Purge contract (FR-011, R22)

"Reset learned answers" deletes:

- `answer_bank` rows with `source IN ('ai', 'auto_saved')`
- `ai_drafts` rows not confirmed by the applicant

It **never** deletes:

- `answer_bank` rows with `source IN ('user', 'confirmed')` — including every
  D7-captured answer
- any `user_profile` column

The confirmation dialog states the exact counts before deleting.

---

## 6. Round-trip guarantee

Every column registered in `db._PROFILE_COLUMNS` must save and reload
unchanged. This is asserted by a single table-driven test, which also closes
the existing `target_titles` defect — it is proposed by the résumé importer but
absent from `_PROFILE_COLUMNS`, so today it is silently dropped.
