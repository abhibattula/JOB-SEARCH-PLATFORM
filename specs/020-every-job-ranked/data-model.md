# Data Model: Every Job Ranked (feature 020)

No new tables. One new column-free status record, one new index, and a
sharpened meaning for a field that already exists.

---

## 1. Job score (existing — meaning sharpened)

Stored on `jobs` as it is today:

| field | type | notes |
|---|---|---|
| `match_score` | REAL, nullable | 0–100. **After this feature, NULL means "not yet eligible or not yet ingested" — never "we ran out of budget".** |
| `match_json` | TEXT (JSON) | the serialized `MatchAnalysis` plus `method` |
| `embedding` | BLOB, nullable | packed EmbeddingGemma vector, unchanged |

`match_json.method` is the **score tier**, and is the field the whole feature
turns on. It already exists and is already written; this feature makes it
load-bearing for presentation.

| `method` | produced by | cost | shown as |
|---|---|---|---|
| `basic` | `basic_match.score()` | 0.0044 s | `~` — "quick keyword match" |
| `local` | `matcher.analyze_match()` on the bundled model | ~67 s | `•` — full AI assessment |
| `llm` | `matcher.analyze_match()` on a cloud key | ~2 s | full AI assessment |

**State transitions** (a job only ever moves rightwards):

```
    ingested
       │  eligible? (is_entry_level=1, delisted=0, sponsorship != EXCLUDED)
       ▼
   [no score]  ──ranking stage (every refresh, uncapped, model-free)──▶  method=basic
                                                                            │
                                          assessment pass, best-first ──────┘
                                                        ▼
                                                 method=local | llm
```

- Ranking never overwrites an existing score.
- Assessment overwrites a `basic` score in place — `match_score`, the analysis
  content, and `method` all change together, so a job never displays an AI
  badge over a keyword score.
- A failed assessment leaves the `basic` score untouched (FR-012).
- An ineligible job is skipped by both stages; it keeps whatever it had.

**Analysis content** (`matching_skills`, `missing_skills`, `gap_actions`,
`reasoning`) is unchanged in shape. `basic_match` already populates all four —
so `job_detail.html` needs no new empty-state handling.

---

## 2. Assessment pass (new — in-memory, single-flight)

Owned by `engine/upgrade.py`. Deliberately **not persisted**: the pass is
rebuilt from the database on every start (`jobs_needing_score` +
`semantic.order_jobs`), which is what makes FR-010's resumability free.

| field | meaning |
|---|---|
| `running` | whether a pass is live — the single-flight guard (FR-009) |
| `total` | jobs selected for this pass (≤ the per-pass limit) |
| `done` | jobs whose assessment finished, succeeded or failed |
| `failed` | assessments that failed this pass |
| `started_at` | when the pass began |
| `paused_for_session` | true while standing down for a fill session (FR-013) |

**Lifecycle**

```
idle ──start()──▶ running ──▶ (per job: yield if a fill session is live)
                     │                       │
                     │                       ▼
                     │                  paused_for_session
                     │                       │  session ends
                     │◀──────────────────────┘
                     │
                     ├── limit reached / no candidates ──▶ idle
                     └── app closes ──▶ idle (at most one job's work lost)
```

`start()` while `running` is a **no-op**, not a queue — this is the direct fix
for the duplicate-loop defect in research R2.

**Failure accounting**: a job that fails assessment is counted in `failed`,
keeps its `basic` score, and is **not retried inside the same pass**. It
remains a candidate for a future pass because `jobs_needing_score` still
matches it via `upgrade_methods=("basic",)`.

---

## 3. Assessment progress (new — read-only projection)

A small read-only view of §2 exposed on the existing status payload so the feed
can show "AI-scoring 12 / 40" (FR-011). Additive; no existing field changes
meaning.

```json
{
  "assessment": {
    "running": true,
    "done": 12,
    "total": 40,
    "failed": 0,
    "paused_for_session": false
  }
}
```

Absent or `running: false` renders nothing. This is a *separate record from the
refresh run*, because the pass deliberately outlives the run (FR-007) — the
`_alerts` pseudo-source row in `db.update_run_source` is the closest precedent
but is scoped to a run and therefore not reusable here.

---

## 4. Settings (existing key, new meaning)

| key | before | after |
|---|---|---|
| `MAX_SCORE_PER_RUN` | scores of any tier per refresh run (default 150) | **AI assessments attempted per pass** (default **40**) |

Ranking is uncapped and no longer consults this key at all (FR-001). The
default drops because each unit of work now costs ~67 s rather than a mixture:
40 × 67 s ≈ 45 minutes of background work per pass, off the critical path.

This meaning change is a user-visible behaviour change and is the reason the
release ships as **v2.0.0**.

---

## 5. Rich-text field (new descriptor shape)

A rich-text editor is an editable region, not a form control, so three
descriptor inputs are sourced differently. No protocol version change —
`PROTOCOL_V` stays 1 and every field below already exists on the descriptor.

| descriptor field | native control | rich-text region |
|---|---|---|
| `value` | `el.value` | `el.innerText` |
| `name` | `el.name` | absent — classification falls back to `automation_id`, `id`, and label text |
| label | `el.labels[0]` | the 019 ladder: `aria-label` → `aria-labelledby` → wrapping label with controls stripped → preceding sibling |
| `type` | `el.type` | `"richtext"` |
| `je_idx` | stamped on the control | stamped on the editable element |

`"richtext"` is treated as text-ish everywhere text-ish matters: it counts
toward `looksLikeApplicationForm`'s two-text-field floor, it counts as a
visible required field for step completeness (FR-019), and it is eligible for
drafted answers under the unchanged v1.7.0 refusal contract.

**Write outcome** feeds the existing outcome vocabulary — no new values:
`filled` on success, `needs_manual` when the editor rejects the write
(FR-018). There is no silent third state.

---

## 6. Index (new)

```sql
CREATE INDEX IF NOT EXISTS idx_jobs_sort_date
  ON jobs (COALESCE(posted_date, first_seen) DESC);
```

Serves the feed listing's `ORDER BY`, which today materialises and sorts every
matching row (`USE TEMP B-TREE FOR ORDER BY`, 67.9 ms over 22,145 rows). An
expression index keeps the `posted_date` → `first_seen` fallback semantics that
the constitution's recency rule requires, with no query rewrite.

Added through the existing idempotent schema-init path — no migration script,
no data movement.
