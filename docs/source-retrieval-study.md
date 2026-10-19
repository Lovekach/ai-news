# Source retrieval and local editorial model study

Date: 2026-10-19. Baseline: production `f0308cd`.

## Decision

**Keep this experiment in Draft; do not deploy it.** Structured extraction
preserves useful evidence, but this study does not establish a reliable gain in
complete, accurate daily stories. Replacing Qwen with the tested Ministral is
not supported. Passing CI is not evidence of editorial quality.

PR #9 was research material only. Its fact-first pipeline was neither imported
nor merged. The existing production editor, collectors, model, configuration,
publication ledger and 21:00 Moscow schedule remain unchanged. This reader is
an experimental API, with no production caller or enabling configuration.

## Protocol and evidence boundaries

- Development: the 20 review cases from October 18, including the 16 holds whose
  stored reason was absence of a direct source beyond a Telegram repost.
- Control 1: all 13 October 19 source records in the morning snapshot, reserved
  before reading their bodies. Extractor and editor frozen before unsealing.
- Control 2: all 15 additional records through the predeclared afternoon cutoff,
  without selecting favorable examples. No editorial or extraction tuning after
  the first control results. Previously exposed old events remain negative
  controls, not independent positive examples.
- There are **28 source records, not 28 independent publishable events**. Only
  two strict new-event positives were identified: D3 recipe integration and the
  MiniMax M3.1 Flash launch. Several resources/opinions have conditional value.
  This is too small a positive sample for a reliable accuracy percentage.
  D3 timing uses the dated official-account collector record; its benchmark
  results remain attributed claims, not independently replicated measurements.
- Source-bound reference assertions and eligibility decisions were recorded
  before each cohort's model outputs. The tested Qwen did not provide the gold
  judgments. Review was by the investigating agent, not an independent external
  human panel; no inter-rater agreement is claimed.
- The interrupted session missed the originally reserved 17:00 capture cutoff.
  That deadline was not silently backdated. The same first-cohort records were
  retained for a prospective 19:15 cutoff; the additional cohort used 19:20.
  Newly captured documents are **not** evidence of what the system knew on
  October 18. Publication labels do not prove availability of an earlier body.
- Later changes validated original URLs before GitHub API rewriting and rejected
  multicast/IPv6 transition addresses. These were transport security fixes;
  extraction, editorial prompts and control selection did not change.
- Source JSON and captured HTTP bytes remain private and hash-checked. No real
  Telegram publication, paid API or third-party upload of private input occurred.

## Why October 18 produced few stories

The snapshot contains 41 records whose **source publication date in Moscow** is
October 18: 3 sent, 10 skipped, 20 held for review and 8 pending. These are record
states at snapshot time, not counts of unique events or historical processing
outcomes at the publication deadline.

### A separate coverage gap

All eight pending records were published after the 21:00 edition. The existing
calendar-day window excludes them both from that edition and from the next
day's editor. This was reproduced with the actual eight timestamps and the
unchanged `daily.window` / `published_in_window` functions, without model calls.

For example, the [Anthropic fund announcement](https://www.anthropic.com/news/public-benefit-fund)
has a stored publication time of 21:05 Moscow and was discovered at 21:11.
It is not a model rejection or a lack of source material. Eight excluded records
are not necessarily eight valuable unique stories: they include reposts and
opinions. At least this directly inspectable company announcement demonstrates
the coverage problem.

The recommended policy is a continuous interval between edition cutoffs,
retaining original dates and ledger deduplication. That changes the earlier
calendar-day specification, so it is a proposal here, **not an untested live
change**. Publication can still remain at 21:00.

### Audit of all 20 review cases

“Link exists” does not mean the linked page confirms the repost's whole claim.
Availability below distinguishes application retrieval from an external web
inspection; historical raw responses are unavailable for most cases.

| Case | Material | Evidence and actual obstacle | Editorial conclusion |
| --- | --- | --- | --- |
| 01 | Podcast | Video/community links, no captured transcript | Episode metadata is not a technical release |
| 02 | Pinned photo | Service notification, no technical source | No independent news event |
| 03 | Weekly roundup | Own channel links and aggregation | Do not present the roundup as a new event |
| 04 | Electric transport | Older secondary article, outside AI focus | Not a missed AI release |
| 05 | Coding benchmark | Author's X link exists; X is not selected as linked evidence; direct body not captured | Author-reported experiment remains unverified; conditions matter |
| 06 | TDFlow research | ACL link exists, but speculation filter runs before retrieval; application fetch timed out | Primary abstract confirms research; proceedings date is March, not October 18 |
| 07 | BuildingBench | Benchmark-site link exists; unselected host; response exceeds the 2 MB safety bound | Web inspection exposes methodology, not the asserted numeric leaderboard rows or training claim |
| 08 | Vague model comparison | No inspectable reference | Cannot establish the claimed result |
| 09 | Audio tutorial | API root, not a dated model announcement | Resource/tutorial, not proof of a new capability |
| 10 | Security incident | No captured primary incident notice | Scope and percentage are not established |
| 11 | Personal comparison | No methodology or raw-data reference | Cannot turn observations into a controlled benchmark |
| 12 | Claimed gzip speedup | No direct source in repost; manually found older release confirms a feature only | Compression does not prove threefold overall model speed |
| 13 | Harness² | Official repository exists; no captured dated launch or preceding stable release | README confirms framework, not its launch date; old extractor loses tables |
| 14 | Coding-workflow quotation | Opinion without a source | Not a new product event |
| 15 | Agents course | Video playlist, no captured transcript or new-course date | Resource availability alone is insufficient |
| 16 | Lean/Mathlib essay | Author blog is linked; unselected WordPress host, application HTTP 403 | Inspectable guest essay dated October 16; not an official position of entire communities |
| 17 | Court report | Older secondary article; captured preview, not the filing | Limited support and peripheral scope |
| 18 | Mathematics interview | Older secondary preview/opinion | Not a fresh product announcement |
| 19 | Quoted commentary | Mirror HTTP 403; editor uncertainty | No demonstrated false rejection of a clean news story |
| 20 | vLLM 0.32.0 | Official short post already captured; invalid noncontiguous evidence quote blocks the draft | Fresh event is supported; source ambiguity and invented explanations must not be amplified |

Primary checks: [TDFlow / ACL](https://aclanthology.org/2026.eacl-long.70/),
[BuildingBench](https://enactra.ai/buildingbench),
[Harness²](https://github.com/google-research/harness2),
[guest essay](https://xenaproject.wordpress.com/2026/10/16/how-to-formalize-all-of-mathematics/),
[vLLM release](https://github.com/vllm-project/vllm/releases/tag/v0.32.0).
The essay explicitly disclaims representing associated organizations. Current
release notes clarify Model Runner V2's default status; the compressed original
post is less explicit. Do not blame a model for lacking that later-retrieved
clarification. Its unconditional accuracy guarantee and fabricated quotation
are independently unsupported by its actual input.

The 16 missing-source holds therefore do **not** establish 16 lost valuable,
fresh stories. Source selection, freshness, source access and model errors are
different failure classes.

## Experimental Source Retrieval Layer

`ainews.source_retrieval` adds a dependency-free document API:

- Headings, table rows/columns, captions, adjacent notes and explicit span markers.
- Separate document authorship, publication, modification and observation fields.
  Repository ownership and release-editor identity are not inferred developers.
- Raw-response hashes and complete extracted blocks, with a separate bounded
  whole-block model projection. Retrieval time is not supplied as an event date.
- GitHub release API notes and repository README support. A README's activity
  does not become a release timestamp.
- HTTPS-only requests, original URL validation before API rewriting, all-address
  DNS checks and IP-pinned TLS. Redirects are revalidated. Private, link-local,
  multicast and transition destinations are rejected; no proxy credentials,
  cookies, scripts or commands from documents are executed. Fixed byte, redirect
  and HTML-structure bounds apply. Public addressability does not establish trust.

### What was measured without LLM calls

On the same captured bytes, the old extractor retained **0/12 explicit table-row
bindings**, the new extractor **12/12**, both in full extraction and their 7,000
character projections: 5 development bindings and 7 control-document bindings.
Documents were the Harness² README, a vLLM startup article and vLLM structured
decision documentation. This is a narrow **structure-retention measure**, not
12 newly discovered unique facts or a factual-accuracy score. A fact can also
appear elsewhere in prose. No model calls were used for this comparison.

Important failures remain: academic citation dates/authors and text in some flat
containers are incompletely extracted; a resource page shrank from 976 to 176
characters. A Hugging Face page fails substantive-content extraction. Dynamic
scoreboards, some WordPress requests and binary PDFs are not solved. These
failures were kept in the results, not repaired by tuning on controls.

The production authority catalog and first-link selector are unchanged. A better
HTML parser cannot bypass those earlier gates. The linked official MiniMax blog
in a Telegram repost is not selected; the official X account still supplies the
launch independently. Expanding verified publisher discovery is a separate
requirement from silently trusting every public HTTPS domain.

## A/B/C/D: real local-model controls

Same production writer, style editor, revisions, deterministic checks and
structured verifier. Temperature 0, context 6,144, thinking off, native output
limits/retries unchanged. Experimental keep-alive was 5 minutes for every arm;
owned server shutdown ended each session. No production setting was edited.

- **A:** Qwen 3.5 9B, existing retrieval.
- **B:** same Qwen/editor, experimental document retrieval only. Same-release
  API notes can replace feed notes when publication dates agree. Trust/freshness
  gates remain unchanged; no editorial prompt changes.
- **C:** same enhanced input/routing as B, Ministral 3 8B instead of Qwen.
- **D:** B was selected before control outputs as the combined candidate, given
  Ministral's development errors. D aliases B; no artificial fourth run/cost.

| Arm, both control cohorts | LLM calls | Generated tokens | Batch seconds | Mock story records | Strict target events represented |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 18 | 4,680 | 260.333 | 5 | 2 of 2 |
| B | 16 | 4,133 | 217.404 | 4 | 2 of 2 |
| C | 19 | 7,081 | 412.409 | 2 | 1 of 2 |
| D | Same as B | Same as B | Same as B | Same as B | Same as B |

Target-event representation is **not** a count of fully correct publishable
texts. The table below gives source-checked defects. No percentage accuracy or
90-point quality score is inferred. Single sequential runs include startup,
cache and sampling overhead; timing differences are not a statistical speedup.

| Control outcome | A | B | C |
| --- | --- | --- | --- |
| D3 integration | Core event and snapshot date retained; mixed-workload qualifier lost; stray English word | Core retained; snapshot date lost and misleading “vLLM hardware” wording | More benchmark conditions retained; awkward calques and extra organizational interpretation |
| MiniMax launch | Core release retained; cached price and benchmark labels omitted despite visible input | Similar omissions | Held after inaccurate draft and numeric/evidence checks; important event not delivered |
| Startup optimization | Loses already-local images/models condition; chronology unresolved | Same text as A | Invents literal `--uv` and gives ambiguous time-saving wording; verifier accepts the invented flag |
| Weekly old-model recap | Emits the old DeepSeek release as fresh | Blocks because extraction fails | Blocks because extraction fails |
| Interface/model opinion | Turns an analogy into stronger causal prose | Same problem | Skips it |

B's lower stale-post count and cost are partly caused by a **parser failure**,
not proven correct chronological reasoning. This is not a safe quality win.
The complete model-visible inputs already contain several omitted conditions;
those omissions cannot be blamed on missing retrieval. Conversely, absent speed
profiles in the short MiniMax post were not facts a model was expected to invent.

No clean, whole-story false verifier rejection was established. A valid derived
four-day interval triggers the numeric guard in one otherwise unsafe Ministral
draft; that is a local overstrict signal, not proof the complete draft deserved
publication. A source-backed definition is also removed as uncertain in one
Qwen subset. Actual audit stages identify revisions separately from fact-check
calls; a writer-shaped revision response is **not** misreported as a malformed
verifier response. The invented CLI flag is a demonstrated false acceptance.

### Full-primary-input diagnostic (not independent control)

The same MiniMax case was additionally supplied with its captured full official
blog, manually, to test the ceiling without automatic discovery. The original
source files were unchanged. This cannot be counted as B's retrieval success.

- Qwen: 4 calls, 1,163 generated tokens, 67.320 case seconds; mock story produced.
  It now retains cached pricing, named additional benchmarks and the 200+ TPS /
  P50 170+ profile. Marketing wording and attribution still need improvement.
- Ministral: 4 calls, 3,126 generated tokens, 175.096 case seconds; held. It adds
  an unsupported concurrency condition to the median speed, repeats differently
  rounded benchmark lists, uses an unjustified record claim and paraphrases the
  evidence field instead of quoting it exactly.

Thus complete evidence helps Qwen, but does not automatically solve selection,
attribution or editorial reliability. The two models still fail differently.

## Local-model feasibility

| Candidate | Evidence and decision |
| --- | --- |
| Qwen 3.5 9B | Existing production model; actually tested, retained in production |
| Ministral 3 8B Instruct 2512 Q4_K_M | Official Ollama tag, about 6 GB package, 8.92B total parameters, Apache 2.0; actually tested in private cache |
| Gemma 4 E2B | Official tag lists a 7.5 GB package including additional components; effective parameters alone do not predict residency; not downloaded or tested |
| Qwen 3 8B | Official approximately 5.2 GB package, Apache 2.0; no measured advantage over current Qwen, not tested |
| Gemma 3 4B | Approximately 3.3 GB package, Gemma terms; smaller candidate, no evidence of superior editorial quality, not tested |

Sources: [Ministral tag](https://ollama.com/library/ministral-3:8b-instruct-2512-q4_K_M),
[model/configuration](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512),
[Gemma 4](https://ollama.com/library/gemma4:e2b),
[Qwen 3](https://ollama.com/library/qwen3:8b),
[Gemma 3](https://ollama.com/library/gemma3:4b).

For Ministral, 34 layers × 8 KV heads × 128 head dimension × K/V × FP16 × 6,144
tokens gives 816 MiB theoretical KV. Actual runtime reports 744 MiB GPU KV and
72 MiB CPU KV, with 32/35 layers offloaded; weight buffers are 4,263.52 MiB GPU
and 685.50 MiB host. It fits only with partial host placement in this run.
No production Ollama upgrade or shared-service intervention was needed.

Peak **whole-device** GPU use on controls: A 7,581 MiB, B 7,552 MiB,
C 7,339 MiB, including desktop/other applications. Peak summed owned process
working sets were approximately 2.89 / 2.67 / 3.87 GiB respectively; private
committed memory approximately 9.74 / 9.52 / 10.20 GiB is a different measure,
not resident RAM. Shared-page sums and sampled peaks have normal limitations.
All owned sessions closed. No claim is made that untested models cannot work,
or that all compact models have been exhausted.

## Verification and production boundary

- **300 Windows unit tests passed**, including 17 focused reader tests. Existing
  scheduling, publication, evidence, deduplication and lifecycle tests remain.
- Real-model control runs: 84 case executions over 28 records; 53 LLM calls.
  Development and full-input diagnostics add 15 calls: **68 total**, 24,493
  generated tokens. Retrieval-retention checks add zero model calls.
- Three aggregate mock editions: one send each, **3,363 / 2,762 / 1,493 UTF-16**,
  no public links, no second send on retry, full private artifacts retained.
  This verifies delivery mechanics, not semantic truth or every possible
  multi-source merge. Existing merge regressions were not replaced by fake data.
- Original control input hashes match reservation hashes. Production historical
  ledger and protected configuration/archive hashes match; main remains
  `f0308cd`. Scheduled production tasks were read only, never rewritten.
- The new code uses only the standard library. No new dependency, scheduler,
  model daemon, secret or production deployment is introduced by this branch.
  Public tree/history receive redacted Gitleaks and exact staged-content review;
  private inputs, measurements, models, databases and credentials stay local.

## What to do next

1. Resolve the calendar-cutoff gap explicitly: a continuous edition interval
   avoids permanently losing evening arrivals without changing 21:00 publication.
2. Capture provenance **before** editing: verified publisher identities, canonical
   primary links, dated source versions and access failures. Prioritize official
   documents over the first recognized link; do not loosen evidence standards.
3. Add source-format adapters for academic metadata, model cards and dynamic
   tables, then validate on new untouched documents. Preserve complete raw
   captures privately and measure facts in the actual model-visible projection.
4. Keep Qwen for now. Address demonstrated unsupported explanations and code
   literals without assuming that another call by the same model is independent
   verification. Do not resurrect PR #9's unproven redesign or add model-name
   regexes. Any narrower translation/editor strategy needs a new controlled test.

The current bottleneck is a combination of **coverage-window policy, primary
discovery/access, lossy extraction and limited model/verifier reliability**.
Neither an HTML-parser replacement alone nor this model swap establishes a
production-ready improvement. Retain the stable installation until that changes.
