# Quickstart: Apply Assist

## Prerequisites

- Everything from `specs/001-ai-job-engine/quickstart.md` already set up and
  working (resume uploaded, feed populated).
- No new prerequisite for the local AI tier — it's bundled, works with zero
  setup (spec FR-001). A cloud API key is still optional and, if present,
  still takes priority over the local model (FR-002).
- Apply Assist itself needs one one-time step: a Chromium download
  (~150-280MB) the first time it's enabled — needs an internet connection
  for that one download only, not for anything else in this feature.

## Local AI tier — verify it's working

1. Remove/leave blank `LLM_API_KEY` in `.env` (or Settings).
2. Upload a resume, trigger a refresh.
3. Jobs should score within a few seconds each, labeled distinctly from both
   the existing cloud-AI label and the existing basic-match `~` label (see
   `data-model.md`/`plan.md` for the exact tier tag).
4. Add a cloud API key afterward → next scoring pass should prefer cloud and
   upgrade previously local-scored jobs automatically (FR-003).

## Apply Assist — first use

1. Shortlist a few jobs via the existing status mechanism.
2. Go to `/autofill`, click to enable Apply Assist — this triggers the
   one-time Chromium install (`POST /api/autofill/setup`); watch the
   progress on the page.
3. Once installed, select shortlisted jobs and start the queue
   (`POST /api/autofill/queue`) — a separate, dedicated browser window opens
   (not your regular browser — see `spec.md` Clarifications) on the first
   job's real application page.
4. Watch fields get filled from your profile/answer bank. If a question is
   new or legally sensitive (work authorization, sponsorship), the queue
   pauses and shows a drafted suggestion on the `/autofill` page for you to
   confirm or edit — nothing is typed into that field until you do.
5. Review the filled application yourself in the browser window, make any
   corrections, and click the site's own submit/apply button yourself —
   Apply Assist never does this for you (FR-008).
6. Click "Done, next application" on the `/autofill` page — the next
   shortlisted job's page opens automatically (FR-014). Repeat until the
   queue is empty.

## Saved logins

1. On the Settings page, save a login (domain + email + password) for a job
   site you use often.
2. Next time Apply Assist reaches that domain's login page, the fields
   fill automatically — you still click the login button yourself.
3. Revisit Settings later: you'll see the domain and email, never the
   password again (FR-017).

## What "graceful fallback" looks like

On a site the field-reader can't confidently read (a heavy multi-step
application system, or one that blocks automated access outright — Workday
is the known example from this project's job-ingestion history), the tab
still opens, nothing gets force-filled incorrectly, and clicking "Done,
next application" still advances the queue (FR-009).

## Verification checklist (maps to spec Success Criteria)

- [ ] SC-001: fresh profile, no API key, no internet for scoring — jobs
      still get AI-quality scores.
- [ ] SC-002: on a Greenhouse/Lever/Ashby-style application, most common
      fields are correctly pre-filled without retyping.
- [ ] SC-003: across a full Apply Assist session, no submit button and no
      login button is ever clicked by the app itself.
- [ ] SC-004: answer a question once; it's never asked again on a later job
      with the same/equivalent wording.
- [ ] SC-005: every sponsorship/work-authorization answer used traces back
      to a confirmed answer bank entry — check `application_answers` for a
      session and confirm none reference an unconfirmed draft.
- [ ] SC-006: selecting jobs → "Done, next" is the entire manual loop; no
      extra setup step appears between applications.
- [ ] SC-007: point Apply Assist at a known-difficult site (e.g., a Workday
      posting) and confirm it opens for manual completion and the queue
      still advances afterward, rather than getting stuck.
- [ ] SC-008: full pytest suite and a manual pass over every existing page
      both pass before/alongside this feature's own verification.
