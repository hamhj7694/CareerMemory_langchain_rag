# Conversation Analysis Benchmark Results

Measured on 2026-10-07 (Asia/Seoul) with `gpt-4o-mini`.
Every case used one cold run and three repeated runs. Benchmark execution did
not call the persistence API and detected no database writes.

## Long conversation performance

Input: 38 user messages and 405 unique source tokens. Values are four-run
medians.

| KPI | `combined-analysis-v1` | `routed-analysis-v2` | Change |
|---|---:|---:|---:|
| Input tokens/run | 8,533.5 | 7,329.5 | -14.11% |
| Output tokens/run | 255.0 | 121.5 | -52.35% |
| LLM calls/run | 7.0 | 2.0 | -71.43% |
| Token amplification | 21.0705x | 18.0975x | -14.11% |
| Unique-source ratio | 4.746% | 5.526% | +0.780%p |
| Cached tokens/run | 0 | 0 | unchanged |
| Estimated cost/run | $0.00143265 | $0.00119168 | -16.82% |
| Total duration | 13.151s | 4.665s | -64.53% |
| Cold duration | 15.046s | 7.149s | -52.49% |
| Repeated-run duration | 12.921s | 4.446s | -65.59% |
| Database writes detected | 0/4 | 0/4 | passed |

The baseline made five job-discovery calls, one job-analysis call, and one
experience-analysis call. The final route made one content-routing call and one
experience-analysis call. The complete-job guard correctly rejected the isolated
requirement bullet that the baseline had treated as a full posting, so no job
analysis call was needed for this conversation.

## Gold-set preservation quality

The same synthetic Korean conversation and gold labels were used before and
after the change. Values are four-run means.

| KPI | Before | After | Change |
|---|---:|---:|---:|
| Experience fact recall | 66.667% | 100.000% | +33.333%p |
| Context-dependent fact recall | 0.000% | 100.000% | +100.000%p |
| Expected source usage | 100.000% | 100.000% | unchanged |
| Expected source fact-citation coverage | 66.667% | 91.667% | +25.000%p |
| Exact citation validity | 100.000% | 100.000% | unchanged |
| Job detection recall | 100.000% | 100.000% | unchanged |
| Job detection precision | 100.000% | 100.000% | unchanged |
| Job requirement term recall | 50.000% | 100.000% | +50.000%p |
| Assistant-only claim contamination | 0.000% | 0.000% | unchanged |
| Irrelevant-chat leakage | 0.000% | 0.000% | unchanged |

On the small gold set, richer context and evidence validation increased input
tokens by 14.56%, output tokens by 43.06%, estimated cost by 28.90%, and duration
by 57.66%. This is the quality cost for recovering context-dependent facts and
validating exact source evidence. On the longer conversation, removing repeated
discovery calls and rejecting an incomplete job fragment outweighed that overhead
and reduced input, cost, and latency. The 91.667% fact-citation coverage means one
expected source was represented in structured output but was not redundantly
cited as a separate `facts` entry in one of four runs; source usage and exact
citation validity both remained 100%.

## Structured skill and metric normalization follow-up

The v3 follow-up keeps the raw `skills`, `facts`, `keywords`, source text, and
exact quotes, then adds optional `skill_mentions` and `metrics` projections.
Unknown technologies remain `unresolved`; they are not discarded. Embeddings
still retrieve candidates, but a required technology is satisfied only by a
sourced canonical skill ID match. Related technologies such as FastAPI/REST API
and JavaScript/TypeScript remain searchable without being treated as identical.

Numbers are reparsed from exact source quotes. Model-proposed numeric values are
not trusted directly, and calendar years are excluded from performance metrics.

### V3 gold-set quality

Cold one run plus three repeated runs, using the same
`synthetic-korean-career-conversation-v1` fixture:

| KPI | Structured v3 |
|---|---:|
| Experience fact recall | 100.000% |
| Context-dependent fact recall | 100.000% |
| Expected source usage | 100.000% |
| Expected source fact-citation coverage | 100.000% |
| Exact citation validity | 100.000% |
| Job detection recall / precision | 100.000% / 100.000% |
| Job requirement term recall | 100.000% |
| Canonical skill normalization recall | 100.000% |
| Structured metric value recall | 100.000% |
| Assistant-only claim contamination | 0.000% |
| Irrelevant-chat leakage | 0.000% |
| Numeric hallucination | 0.000% |
| Database writes detected | 0/4 |

### V3 long-conversation performance

Against the original `combined-analysis-v1` baseline on the same 38-message
conversation:

| KPI | Baseline | Structured v3 | Change |
|---|---:|---:|---:|
| Input tokens/run | 8,533.5 | 7,494.0 | -12.18% |
| Output tokens/run | 255.0 | 147.0 | -42.35% |
| LLM calls/run | 7.0 | 2.0 | -71.43% |
| Estimated cost/run | $0.00143265 | $0.00123195 | -14.01% |
| Total duration | 13.151s | 4.564s | -65.30% |
| Database writes detected | 0/4 | 0/4 | passed |

Compared with routed v2, the larger structured schema increased input tokens by
2.24%, output tokens by 20.99%, and cost by 3.38%, while median duration improved
by 2.16%. This is the measured cost of lossless skill/metric projections and
their source validation; the main routing savings over the original baseline
remain intact.

## V4 ontology/Evidence actual-model validation

Measured on 2026-10-08 with the synthetic Korean gold fixture and
`gpt-4o-mini`. The run used one cold execution plus three repeated executions.
All 12 model calls succeeded without fallback or workflow failure.

| Runtime KPI | V4 result |
|---|---:|
| Successful runs | 4/4 |
| Input tokens/run, median | 3,995.5 |
| Output tokens/run, median | 1,374.5 |
| LLM calls/run | 3 |
| Duration/run, median | 18.955s |
| Estimated cost/run, median | $0.00142463 |
| Total cost for four runs | $0.00574995 |
| Database writes detected | 0/4 |

| Gold-set KPI | V4 result |
|---|---:|
| Experience fact recall | 100% |
| Context-dependent fact recall | 100% |
| Expected source usage / citation coverage | 100% / 100% |
| Exact citation validity | 100% |
| Job detection recall / precision | 100% / 100% |
| Job requirement term recall | 100% |
| Skill normalization recall | 100% |
| Structured metric value recall | 100% |
| Assistant-only claim contamination | 0% |
| Irrelevant-chat leakage | 0% |
| Numeric hallucination | 0% |

This V4 run validates that the ontology/Evidence persistence changes preserve the
previous structured-v3 gold-set quality. Runtime values are reported as a new
fixture validation, not as a direct long-conversation comparison with the v1/v2/v3
tables above because their input sizes and measurement dates differ.

## File extraction quality

The deterministic `file-extraction-gold-v1` fixture covers Markdown with a
percentage, native PDF, DOCX tables, PPTX slide relationship order, and HWPX
section paragraphs. Each format is generated in memory and passed through the
same parser registry used by the APIs.

| KPI | Result |
|---|---:|
| Deterministic parser success | 5/5 (100%) |
| Required-fragment recall | 100% |
| Numeric-token recall | 100% |
| Character error rate | 0% |
| Unintended database writes | 0 |
| Real Korean OCR smoke test | passed: Tesseract 5.4.0, kor+eng+osd |
| OCR required-fragment recall | 100% |
| OCR numeric-token recall | 100% |
| OCR character error rate | 8.333% |
| OCR quality score | 0.8246 |
| OCR duration | 1,102.862ms |

`run_ocr` now evaluates PSM 3/4/6/11 candidates and penalizes short or fragmented
results even when their confidence is high. Repeated horizontal table separators
trigger row-level OCR whose output is fuzzy-deduplicated with the whole-page result.

Two existing portfolio assets were also inspected read-only as an acceptance check.
The chat UI screenshot reproduced 6/6 required phrases. The KPI table reproduced
all nine core values (`41.45%`, `68.0%`, `+26.55%p`, `23.59%`, `52.0%`,
`+28.41%p`, `96.67%`, `98.0%`, `+1.33%p`). Small footer text still misread
`477,293` and `P95 34.06`, so this is not reported as 100% recall over every numeric
token in the source image. The actual 31-slide PPTX parsed 31 segments and 18,937
characters without warnings.

### Attachment storage and durable queue

`attachment-pipeline-v1` creates ten files in an isolated temporary LocalBlobStore
and in-memory DB, processes the persisted jobs, verifies every SHA-256 hash, and
simulates one expired worker lease.

| KPI | Result |
|---|---:|
| Files ingested | 10 |
| LocalBlobStore originals | 10/10 |
| New DB BLOB bytes | 0 |
| SHA-256 verification | 10/10 |
| Completed processing jobs | 10/10 |
| Expired leases recovered | 1/1, returned to `queued` |
| Ingest duration | 113.007ms |
| Parse duration | 44.857ms |
| Total duration | 175.314ms |
| Persistent database writes | 0 |

### Ontology, Evidence, and incremental index

`knowledge-layers-gold-v1` uses an isolated in-memory database and fake vector
store. It verifies conservative concept resolution, evidence lineage, invalid quote
rejection, dry-run safety, and content-hash-based incremental indexing.

| KPI | Result |
|---|---:|
| Concept resolution accuracy | 100% |
| Relation classification accuracy | 100% |
| Unresolved expression preservation | 100% |
| Evidence lineage completeness | 100% |
| Invalid quote rejection | passed |
| Ontology dry-run data writes | 0 |
| Evidence dry-run data writes | 0 |
| Seed projection | 10 concepts / 20 normalized aliases / 19 relations |
| Initial evidence projection | 1 document / 1 chunk / 1 link |
| Initial embedding writes | 1 |
| Repeated unchanged embedding writes | 0 |

The regression suite also covers changed source text, stale record transitions,
source unlink deletion, stale vector removal, and full rebuild. The production DB
dry-run scanned zero existing confirmed experiences/source refs and planned no user
data writes; it reported the same deterministic ontology seed projection.

### Product and operational stability

- File workers claim a queued job atomically with `UPDATE ... RETURNING`, a worker
  lease, and ownership checks, preventing two workers from processing one job.
- SSE sends heartbeats and reconnects once with the same `client_request_id`.
  The server returns the persisted `assistant.snapshot` and terminal event without
  starting another model call or storing duplicate messages.
- HTTP middleware records route count, error rate, P50/P95 latency and request ID.
  It deliberately excludes query strings, request bodies, and user source text.

Capability check on the development PC:

- Tesseract 5.4.0: available with `kor`, `eng`, `osd`.
- FFmpeg/FFprobe: not detected in the 2026-10-08 capability run; STT key configured.
- LibreOffice: unavailable, so actual DOC/PPT conversion remains environment-blocked.
- Hancom HWP→HWPX converter: unavailable, so actual HWP conversion remains environment-blocked.
- STT timestamp mapping and persistence passed mocked integration tests; a paid live-audio
  request was intentionally not included in this benchmark.

### Validation

- Backend: 219 tests passed, including actual Korean OCR, ontology/Evidence/index,
  atomic file claim, request metrics, and SSE replay coverage.
- Frontend: 108 tests passed, including interrupted SSE reconnection.
- Frontend production build passed.
- ESLint passed.
- `git diff --check` passed.
- Normalization backfill dry-run scanned 0 existing experiences and wrote no data.
- Attachment BLOB migration dry-run examined 0 existing attachments and wrote no data.
- Both four-run benchmark suites detected 0 database writes.

The 2026-10-08 V4 actual-model rerun completed successfully after explicit approval
to send the synthetic fixture to OpenAI. The earlier connection-failed attempt is
not included in any quality, token, cost, or latency result.

## Raw reports

Runtime reports are intentionally written under the ignored
`data/benchmarks/conversation-analysis/` directory:

- `baseline-v1-20261007-020121.json`
- `routed-v2-complete-job-guard-20261007-025529.json`
- `gold-baseline-v1-valid-20261007-020806.json`
- `gold-routed-v2-complete-job-guard-20261007-025437.json`
- matching `-evaluation.json` files for the gold runs
- `routed-v3-structured-normalization-20261007.json`
- `gold-routed-v3-structured-normalization-20261007.json`
- `gold-routed-v3-structured-normalization-20261007-evaluation.json`
- `routed-v4-ontology-evidence-20261008-155150.json`
- `routed-v4-ontology-evidence-20261008-155150-evaluation.json`
