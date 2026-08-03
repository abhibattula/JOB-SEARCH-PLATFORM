# Research — Feature 021 "The Real Application"

Phase 0 decisions. Every claim here is either read directly out of the code at
the cited location, measured on this machine, or explicitly marked as a
hypothesis that Workstream A must confirm before code is written against it.

---

## R1 — Why 149 rows, and why most of them are blank

**Decision**: Treat this as three independent defects, fix all three, and let
Workstream A's real capture decide how much of the 156 is genuine field count
versus accumulation.

**Findings (read from source):**

1. **De-duplication is per element, not per question.**
   `page_answers.build` (`engine/autofill/page_answers.py`) keys each row on
   `item["key"]`, which is `field_core.key(descriptor)` =
   `(descriptor["doc"], descriptor["je_idx"])` — a per-element stamp assigned
   by `scanner.js stamp()`. Two elements serving one question therefore
   produce two rows. On a Workday dropdown (a trigger with
   `aria-haspopup=listbox` plus the listbox itself, both matched by
   `FIELD_SELECTOR`) that is guaranteed, which is exactly the applicant's
   "questions repeated times even for same question that might be a drop down".

2. **A whitespace label is accepted as a question.**
   `ext_backend.question_of()` is
   `label_text or placeholder or aria_label or ""` with **no `.strip()`**. A
   label of `" "` is truthy in Python, so the row is created; `patchRow` then
   sets `row.q.textContent = " "` and the row renders visually blank. There is
   also no fallback to `automation_id`, even though `scanner.js describe()`
   already captures `data-automation-id` — which is precisely where Workday
   puts a field's stable identity.

3. **The index is never pruned.**
   `_page_entries[job_id]` is cleared only in `_start_answer_feed`
   (`ext_backend.py`). Its keys are `(doc, je_idx)`. `je_idx` lives in a DOM
   attribute, so when React replaces a subtree — every wizard step, every
   remount — the new elements receive fresh stamps and become **new entries**,
   while the old ones stay. The document token does not change, because it is
   stored on `documentElement`. So a multi-step Workday application
   monotonically accumulates.

**Open, and deliberately not guessed**: whether the reported `Seen 156` is one
scan genuinely seeing 156 descriptors, or `_frame_seen` summing stale frames.
`_frame_seen[frame_id] = seen` is an assignment (so it is per-scan per-frame),
but the dict is cleared only at session start, so a frame that disappears
leaves its count in the sum forever. **Workstream A resolves this**; the fix
differs depending on the answer, and the existing Workday fixtures (9 and 2
fields) cannot tell us.

**Alternatives rejected**:
- *Cap the list at N rows.* Hides the defect and silently truncates a review
  surface — the failure mode 018 and 019 were spent eliminating.
- *De-duplicate by question across the whole page.* Would merge two genuinely
  different "Start date" fields in two different employment blocks. Section
  scoping is what makes de-duplication safe, which is why B precedes C.

---

## R2 — Section context: a new signal, not a new stamp

**Decision**: `scanner.js formContext()` is extended to also report the field's
enclosing form section as `{section_label, section_index}`, recomputed from the
document on every scan.

**Rationale**: `formContext()` today (`scanner.js:547`) answers only
`""`/`"login"`/`"registration"`. It is already the per-field context channel,
already mirrored into `watcher.py SERIALIZE_JS`, and already covered by the
serializer-parity test — so extending it costs no new plumbing and inherits
drift protection.

The index **must not** be stamped onto the element. A stamped index would drift
on exactly the React remounts that caused R1's accumulation. Recomputing is
O(fields) per scan, which the 020 measurements show is already the cheap part
of a probe (the `querySelectorAll("*")` shadow-host walk dominates).

**Resolution order** (first hit wins, most specific first):
1. nearest ancestor `fieldset` → its `legend`
2. nearest ancestor with `[data-automation-id]` ending in `Section`/`Panel`, or
   `[role=group]`/`[role=region]` → its accessible name
3. nearest preceding sibling heading (`h1`–`h6`) of an ancestor block
4. `""` — no section determined

**Degradation**: `""` means the panel groups exactly as it does today. Wrong
grouping is worse than no grouping, so an undetermined section never guesses.

**Alternatives rejected**:
- *A new top-level descriptor field.* `PROTOCOL_V` stays 1 and additive; a new
  optional key inside the existing `form_context` channel is additive in the
  same way and keeps one context concept in one place.
- *Deriving sections in Python from the flat descriptor list.* The DOM
  ancestry is the signal and it does not survive serialization.

---

## R3 — Work history and education: the data already exists

**Decision**: Add `engine/autofill/history_answers.py` reading
`profile["resume_sections"]`; do not add a new store.

**Finding**: `engine/resume_extract.py` already defines and populates
`ExperienceEntry(title, organization, start, end, bullets)` and
`EducationEntry(degree, institution, start, end, details)`, persisted as the
`resume_sections` column (`engine/db.py`). `profile_answers._DIRECT` maps
**none** of them. `job_detail.html` already renders from "your Resume builder
sections", so the data is real, populated and user-visible — it has simply
never reached the fill layer.

**The hard rule, inherited from 017**: a missing entry yields `None`, which
means *flag it for the applicant*. Never a guess, never a fallback to a
neighbouring entry. 017 exists because "Do you have a preferred name?" was
filled with the legal full name by exactly that kind of fallback. Three
employment blocks against two stored entries must leave the third blank.

**Gap identified**: `EducationEntry` has no GPA field and no field-of-study
field; `ExperienceEntry` has no location and no is-current flag. These are
added as optional fields (defaulting empty, so existing stored profiles remain
valid) and are editable in the profile — which the spec requires anyway
(FR-014), because a value parsed by a 1.5B model must be correctable before it
is typed into an employer's form.

**Alternatives rejected**:
- *Ask the AI per field at fill time.* 67 s per field on-device, and it would
  invent. The structured data is right there.
- *A separate work-history table.* Duplicates `resume_sections` and creates a
  synchronization problem with the resume the applicant re-uploads.

---

## R4 — Learning what the applicant types

**Decision**: A new `observed` outcome in `field_core`, routed to
`answer_bank.save_with_provenance(..., "observed")`.

**Finding**: There is no capture path today. Writes into `answer_bank` come
only from the panel's own input (`_handle_answer_question`), the app's Apply
Assist page (`routes_autofill.py`), and the drafter (`save_auto`). When the
applicant fills a field themselves, the next scan sees a non-empty value and
`field_core.decide` returns `settle` with outcome `skipped_existing` — the
value is dropped.

**Capture predicate** (from the Clarifications session): the app did not fill
it, **and** it was observed empty on an earlier scan of the same document, and
non-empty now. A value present on first sight is the employer's prefill or the
browser's password manager, not an answer the applicant gave. This requires one
new bit in the ledger — "seen empty" — which is cheap and per-document.

**Deny-list, refused before any storage**: every tag in `_CREDENTIAL_TAGS`, any
`selfid_*` tag, and any question or tag matching national identifier, date of
birth, government identifier, or financial detail. `answer_bank.is_refusal` and
the existing sensitive classifier are reused rather than reimplemented.

**Uniqueness**: `answer_bank.question_normalized` is `UNIQUE`. An observed
answer is written only when no row exists, or the existing row's provenance is
itself `observed`. It never overwrites `user`/`confirmed`.

**Alternatives rejected**:
- *Prompt on the page for each answer.* 149 confirmations on one Workday form.
  The applicant chose auto-save with an app-side review list.
- *Write straight to the profile.* Silently rewriting stored facts from a value
  read off a page is a different and larger risk; the profile write stays
  one-click.

---

## R5 — Why "generate a tailored resume" did nothing

**Decision**: Two separate causes, both fixed.

1. **The error handler throws.** `job_detail.html` binds
   `hx-on::after-request="... JSON.parse(event.detail.xhr.responseText).detail"`.
   On a dropped, empty or non-JSON response `responseText` is `""`,
   `JSON.parse("")` raises, the handler dies, and **nothing at all** is shown —
   which is exactly what the applicant saw. Guarded, with a fallback message.

2. **It queues behind background scoring.** `upgrade._wait_out_any_session`
   stands down only for an active fill session (`browser_controller`). A
   tailoring request is a strict-FIFO `queue.Queue` submission
   (`engine/inference.py`) behind however many upgrade jobs are already queued,
   each ~67 s, against its own 300 s deadline which starts at submit time. The
   stand-down is widened to any applicant-initiated request.

**Measured context**: `TAILOR_TIMEOUT_S = 300`; the requested output is a
summary line, 4–6 bullets, a ~180-word cover letter and keywords ≈ 500–700
tokens; at the measured 5–6 tok/s that is **100–140 s of generation alone**,
plus ~36 s of prompt evaluation. So the operation is inherently 2.5–3 minutes
on-device — inside its budget only when nothing is queued ahead of it.

---

## R6 — Making the AI fast: the fast tier already ships, switched off

**Decision**: Make `scoring_tier()` purpose-aware — cloud for
applicant-initiated work when a key exists, on-device for bulk background work.

**Findings**:
- `matcher.DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"` and
  `DEFAULT_MODEL = "llama-3.3-70b-versatile"`. Settings already renders the
  key field and links `console.groq.com`.
- But `scoring_tier()` returns `"local"` whenever `local_llm.available()` and
  `PREFER_LOCAL_LLM != "0"` — and `PREFER_LOCAL_LLM` defaults on. **Saving a
  key changes nothing**, and nothing in the UI says so.
- `_min_interval()` defaults to 2.2 s ≈ 28 req/min, under the free tier's 30
  RPM. The free tier is also ~1K requests/day, so bulk work must stay local —
  and 020 already made bulk ranking model-free, so there is nothing to lose.

**Two hypotheses tested and discarded** — recorded so neither is chased again:

- *GPU offload is silently hurting.* **No.** The installed
  `llama_cpp` 0.3.34 ships `ggml-base.dll`, `ggml-cpu.dll`, `ggml.dll`,
  `llama.dll`, `mtmd.dll` — **no CUDA, Vulkan, SYCL or Metal backend**.
  `n_gpu_layers=-1` is inert on this install. Not a lever.
- *Thread misconfiguration.* Already measured in 020: 8/4/3 threads →
  22.9/23.2/24.0 s. Flat. Memory-bandwidth-bound. Not a lever.

**On-device levers that remain real**, in order of measured value:
1. Fewer output tokens — the dominant cost, already proven by 020.
2. Streaming — no throughput change, but removes the "nothing happened"
   experience entirely, which is the actual complaint.
3. KV cache type quantization and right-sized `n_ctx` — memory-traffic
   reductions on a bandwidth-bound CPU. **To be measured in T00x before being
   claimed**; if flat, they are recorded as dead ends like the thread test.

---

## R7 — Panel placement

**Decision**: Drag by the header; persist `{right, bottom}` offsets in
`chrome.storage.local`; clamp into the viewport on every restore.

**Constraint from history**: `panel.js:142` carries an explicit comment that
`all:initial` resets `position` and that every version from v1.0.0 to v1.7.0
rendered the widget at the bottom of the document because of it. Every
placement property is therefore set with `setProperty(..., "important")` and
must stay that way — a drag implementation that writes `style.left` normally
would resurrect that bug on any page with `div { position: static !important }`.

**Offsets, not coordinates**: storing `right`/`bottom` keeps the existing
`inset` idiom and behaves correctly when the viewport is resized. Clamping on
restore is required because a position saved on a large monitor would otherwise
strand the panel off-screen on a laptop.

**Rejected**: `position: absolute` with page coordinates (scrolls away from the
form), and storing in `localStorage` (per-origin, so the panel would forget its
place on every new employer's domain).

---

## R8 — Additional free job sources

**Decision**: Add keyless public board APIs on the existing
`engine/ingest/base.py` pattern — **Recruitee, Teamtailor, Personio, Breezy,
JazzHR** — plus **Adzuna** and **The Muse** behind an optional free key.

**Rationale**: The five keyless ones are the same shape as the five already
shipped (`greenhouse`, `lever`, `ashby`, `workable`, `smartrecruiters`): a
per-company JSON board endpoint, which means they qualify as
`FULL_BOARD_SOURCES` — absence from a successful fetch authoritatively means
the posting is gone, which the delisting logic already depends on. They also
reach real employer career pages rather than an aggregator's copy, so the apply
URL is the genuine one.

Adzuna and The Muse are aggregators with free keys; they broaden coverage but
cannot be board-diffed, so they join `SCRAPED_SOURCES` and get the bounded HEAD
liveness check instead.

**Constitution III compliance**: all are official public JSON endpoints, all
route through `base.py`'s process-wide 1 req/sec per-domain limiter and honest
User-Agent, none require payment, a card, or any bot-protection bypass. Per
FR-033 and the existing `_run_source` contract, a failure in one cannot abort
the others.

**Rejected**: SerpAPI / Google Jobs (paid — Principle II), anything requiring
scraping behind bot protection (Principle III), and USAJOBS (free, but federal
postings overwhelmingly require citizenship, so near-zero value to this
applicant and it would dilute the feed).

---

## R9 — What must be measured before it is claimed

Recorded here so the tasks enforce it. This project has killed three approved
plan claims by measurement (CPU threads, the "slow" feed query, companion idle
cost); these are the equivalents in this feature.

| Claim | Must be measured as | Task |
|---|---|---|
| The page really has ~156 fields | Real capture from the applicant's Intel Workday page | A |
| Section detection covers the real page | % of fields resolving to a section in that capture | A |
| History filling cuts the 149 | Recount needs-you on the same page after C | C |
| KV quantization / `n_ctx` help | Timed on-device runs before and after; if flat, recorded as a dead end | F |
| The cloud tier is ~10x+ faster | Timed tailoring request on each tier | F |
| Panel render stays cheap at 150 fields | Timed `reconcile()` on the new fixture | B |
