# Editorial Quality V2 experiment

## Deployment boundary

This is an isolated experiment, not an enabled production editor. The CLI,
collectors, scheduled tasks, model settings and publication ledger retain their
existing behavior. `fact_first.prepare_entry` and `compose_edition` are explicit
Python APIs; no production command selects them. A passing unit suite is not
evidence of editorial accuracy and is not sufficient to deploy this experiment.

## Architecture audit

```mermaid
flowchart LR
    D[Discovery] --> R[Source retrieval]
    R --> E[Event detection]
    E --> F[Fact extraction]
    F --> V[Source verification]
    V --> W[Editorial writing]
    W --> A[Final audit]
    A --> P[Existing archive and publisher]
```

The stable baseline is commit `f0308cd`. Findings below describe its behavior,
not hypothetical errors attributed to every item.

| Stage | Existing behavior | Failure mechanism / experimental change |
| --- | --- | --- |
| Discovery | RSS, Telegram and X adapters retain source text and dates in SQLite. | Discovery time, feed update time and event time are different. An item discovered after an edition cannot be counted as an editorial rejection by that edition. |
| Retrieval | Bounded source enrichment, selected primary hosts, text extraction and source windows. | Flattening HTML can lose table headers and pricing scopes. A source window can omit conditions present later in a long page. The experiment preserves headings, table rows, document identity and paragraph spans. |
| Event detection | Relevance decisions and heuristic event signatures accompany writing. | A repeated product name does not establish the same event. The experiment records company, product, version, event kind, scope and independently evidenced event date. |
| Fact extraction | The writer creates prose before the complete structured claim ledger. | Correct numbers can be attached to the wrong object or scope. The experiment extracts typed facts with individual provenance before prose. |
| Verification | Numeric rules, claim verification and bounded revisions use the same local model. | A citation ID proves provenance, not entailment. Narrow unit patterns can reject a correct measurement; a missed qualifier can survive several correlated model calls. The experiment verifies complete source chunks and the fields and publishable wording of each fact. |
| Writing | Writer, style editor and up to two revisions can restate explanations. | Forced explanatory fields encourage repetition; number-preserving edits can retain awkward Russian. B writes only from verified facts; C assembles independently verified Russian fact sentences without a second free prose generation. |
| Final audit | Existing integrity, numeric, link-removal and length gates. | A valid final length does not prove preserved meaning. The experiment drops only whole paragraphs and retains mandatory facts and limitations; material that cannot fit is withheld. |
| Publication | Existing Moscow-day selection, private archive, reservation ledger, API adapter and uncertain-send protection. | Reuse this boundary, with a supplied experimental composer only in isolated runs. Never exercise real Telegram in the benchmark. |

All model stages use the existing local Qwen 3.5 9B. The experimental verifier
is a separate call, **not an independent model or an independent evaluation**.
The benchmark reference is manually checked against sources outside Qwen.

### Historical counts and attribution limits

The read-only snapshot taken after the October 18 edition contains the following
rows by **source publication day in Moscow**, not by discovery day:

| October 2026 | Source rows | Discovered by 21:00 MSK | Discovered later | Public stories recorded in archive |
| --- | ---: | ---: | ---: | ---: |
| 12 | 53 | 34 | 19 | 4 |
| 13 | 68 | 47 | 21 | 6 |
| 14 | 91 | 71 | 20 | 9 |
| 15 | 96 | 71 | 25 | 6 |
| 16 | 78 | 64 | 14 | 9 |
| 17 | 52 | 49 | 3 | 3 |
| 18 | 33 | 33 | 0 | 3 |

These are source records, not independently established unique events. Snapshot
states can reflect subsequent processing and cannot reconstruct every historical
state transition. Three other records lack a usable publication date. On October
18, 16 of the 20 review holds lacked a direct verifiable primary source beyond
a Telegram repost. Increasing throughput alone would not make those publishable.

Call-level timing is available for October 18: 21 actual requests, approximately
168.92 seconds in total (10 writer, 4 style, 3 verifier, 4 revision). There are
five stored `style_editor` events but four instrumented style requests: a stored
stage result is not necessarily an LLM call. Earlier missing call telemetry
must be reported as unavailable, never as zero.

## Comparison protocol

* A: immutable stable production code at `f0308cd`, using Qwen 3.5 9B.
* B: source-first typed extraction, source verification, fact-only writer and
  final verification, using the same Qwen model and runtime settings.
* C: the same extraction and verification, followed by deterministic assembly
  of verified Russian sentences. This is an alternative generation scheme,
  not a claim that a larger model fits the laptop.

The private corpus contains 20 development records and 14 held-out records
from real source material. The partition, original records, raw HTTP captures,
implementation files and source-derived gold facts are hashed. Raw responses
are identical across variants; each variant executes its own actual parser.
Source content is not edited to improve results. Source text, SQLite, prompts
and channel archives are private and must not be committed.

The historical captures are a bounded replay, not a reconstruction of the exact
web as it existed on every publication date. A README may have changed since a
source post. Such ambiguity must be recorded, not resolved by inventing dates.

Development failures can inform a new explicitly versioned candidate. A failed
run remains in the audit. Before opening holdout source bodies, freeze the
candidate and record the acceptance protocol. Then prepare source-grounded
holdout references before examining model output. No prompt changes, case
replacement or selective reruns may be based on holdout results.

For every output record critical factual errors, unsupported claims, missing
essential facts, false rejections, correctly published unique events,
duplicates/stale items and concrete Russian-language defects. Distinguish an
eligible story missed by the pipeline from a verifier correctly rejecting a
wrong draft. Unresolved reference cases are reported separately, not silently
scored as correct or removed from the denominator.

Record actual HTTP model calls (including JSON retries), wall time, generated
tokens, prompt evaluation, decoding, model loading and sampled memory. GPU
memory includes desktop usage; report the sampling interval and any absent
measurements. Variations in token throughput across identical requests mean
wall-clock differences alone cannot establish an architectural speedup.

Every case uses isolated SQLite, the real publication ledger and a mock sender.
A second publication attempt must not send again. The public output must be
link-free and at most 3900 UTF-16 units; full facts and sources remain in the
private archive. Per-event runs evaluate story behavior; they do not establish
cross-story deduplication or full-day capacity. Those require a separate edition
test before deployment.

## Acceptance

Deployment requires zero **detected** critical factual errors on the untouched
holdout, a demonstrated overall advantage over A, and acceptable evening-window
resource use. This is not a guarantee about future unseen events. Green CI,
more accepted stories or fewer model calls alone do not meet this criterion.
If the experiment fails, keep production unchanged and leave the experimental
branch and an explicit failure report for review.

Known prototype limits include bounded extraction of very long documents,
correlated extractor/verifier errors, incomplete retrieval of social threads,
and no proof yet of complementary-fact merging or day-scale capacity. Event
identity currently prevents exact duplicates; it does not resolve conflicting
updates automatically. These must not be advertised as solved by provenance IDs.
