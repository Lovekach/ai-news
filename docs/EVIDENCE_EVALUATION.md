# Sentence-level evidence experiment: acceptance results

## Decision

**Do not merge or deploy this implementation yet.** The deterministic contract
tests pass, but the real-model editorial acceptance criteria do not. This
branch preserves the implementation for review. It is not a completed quality
fix and no quality score is assigned.

## Method

The comparator is main commit `bb1d9e2`, not a reconstruction of every historic
deployment. Both versions used identical saved input records, Qwen 3.5 9B,
the same generation settings, isolated databases and mocked Telegram delivery.
Original source records were not edited. Replay editing time was fixed at
20:59 Moscow, followed by publication attempts at 21:00 and 21:01.

Development used 23 archived records from October 12–14, 2026. Six additional
previously held records were evaluated separately; their results must not be
added to the main fixture as if they were one deduplicated edition. Private
source text, database snapshots, model responses and publication archives are
excluded from Git.

An initial frozen implementation was rejected after development-set checks
found incorrect score/test relationships. Its first control set was subsequently
opened for independent source review. A second, disjoint 16-record control was
therefore selected using recorded metadata before opening its text. The final
implementation was frozen before that second control was opened. No source
changes were made in response to its results. Original manifests, hashes,
freezes and excluded runs remain in the private audit.

Early exploratory replays with an incorrect 20:00 editing cutoff are excluded.
These are single paired runs: time differences are observations, not statistically
established speedups. Peak GPU usage was not measured reliably.

## Observed results

| Paired fixture | Baseline requests / seconds | Experiment requests / seconds | Baseline / experiment mock cards |
| --- | ---: | ---: | ---: |
| October 12, 4 archived records | 8 / 42.93 | 5 / 41.24 | 0 / 1 |
| October 13, 7 archived records | 31 / 233.77 | 19 / 270.77 | 3 / 5 |
| October 14, 12 archived records | 57 / 393.48 | 32 / 383.76 | 8 / 7 |
| Additional held records, 6 total | 29 / 282.23 | 16 / 235.11 | 1 / 5 across three separate fixtures |
| Disjoint control, 16 records | 30 / 232.48 | 28 / 298.91 | 0 / 6 |

For the main development fixture, calls fell from 96 to 56, while wall time
rose from 670.18 to 695.77 seconds. Fewer calls did not establish faster
processing. On the disjoint control, six cards instead of zero increased
coverage, but included unsupported claims. A publication count is not a count
of correct stories. The zero-publication baseline cannot be assigned a factual
error rate that makes this experiment look better.

Each completed replay sent at most one mock message, blocked the second daily
attempt, stayed within 3900 UTF-16 units and closed its owned Ollama server.
No test message was sent to a real channel.

## Confirmed improvements and release blockers

- Development examples retained context tokens, per-user throughput and its
  GPU/precision conditions more reliably. Intel cooling/interface details were
  retained. Optional rejected sentences can be pruned without another model call.
- Gemini app/global notices merged, but the developer availability notice still
  remained separate because provider metadata was inconsistent. The requested
  complete event deduplication is not achieved.
- A Muse comparison still transferred a point difference to the wrong model.
  The headline could also select the comparator instead of the subject. Exact
  quotations containing all the numbers did not prove the relationship.
- The independent control turned a Kimi tutorial into a product release. The
  source describes a tutorial, not a new launch. A supported LLM verdict failed
  to establish the event type.
- The control described Meta's model as the largest open multimodal MoE, while
  its source discusses much larger scale and claims US capability leadership.
  These are different claims. A literal quote was insufficient protection.
- Valid complex releases still suffered false holds: strict quote/contract
  failures and the existing update-only date gate remain material limitations.
- Native-model comparison errors, cross-clause conditions, source assertions
  and quoted-speaker roles still need human acceptance. The verifier uses the
  writer's model and is not an independent fact-checking authority.

The regression suite checks literal IDs, units, versions, evidence integrity,
pruning, stale ledgers, event separation, final sentence integrity and mocked
pipeline behavior. Passing that suite does not close the above real-data
failures. They require focused corrections and another untouched control before
this branch can be considered for production.

## Production boundary

No schedule, model, collector, secret or historical publication is changed by
this branch. Code work occurred in the scheduled installation's checkout, so
unchanged task definitions alone do not prove an unchanged runtime. The October
16 production edition ran while the experiment was present; that is disclosed
in the private operational audit. Keep the production checkout on approved main
while this PR remains unmerged. Preserve collected state and existing receipts.
