# Editorial Quality V2: measured experiment

## Decision

**Do not deploy or merge this experiment.** The tested fact-first candidates did
not establish an overall editorial advantage. Production remains on `f0308cd`.
Passing CI establishes software checks, not factual accuracy. No quality score
out of 100 is assigned.

## What was compared

All variants used the actual local Qwen 3.5 9B, the existing runtime options and
the same frozen source records and raw HTTP captures. No paid API or additional
model was used. On this 8 GB laptop, C is an alternative generation scheme.

| Variant | Processing |
| --- | --- |
| A | Immutable production writer, style editor, verifier and bounded revisions |
| B | Requested source-language fact extraction, source verification, Russian writer, final fact audit |
| C | Russian fact extraction, source verification, deterministic paragraph assembly |

B did not consistently obey the source-language instruction. This measures the
implemented candidate's behavior; it does not disprove every possible fact-first
architecture. The verifier is another call to the same model, not an independent
model or evaluator.

### Corpus and independence

The final paired comparison contains 32 source records: 20 development records
and 12 newly reserved controls. One control quotes the same DeepSeek release as
a development record. It remains a duplicate control but is excluded from
independent acceptance: **11 fresh independent records**, at most 31 distinct
events overall. Ambiguous chronology, commentary and one unavailable article
remain in the corpus. They are not replaced by easier examples.

The earlier 14-record holdout became unsealed validation after further
development fixes. It is not independent evidence for the final candidates.
Final source code, runner and partition were hashed before opening the new
controls. Source-grounded references were recorded before control model output;
no code, prompt or threshold was changed afterwards. Original references and
explicit chronology errata are retained separately.

References and output reviews were prepared by the development assistant outside
target Qwen. There was no independent human review panel or blinded variant
judge. The small independent split limits confidence; zero observed errors
would not establish future error-free behavior.

This is a replay of captured material, not a reconstruction of every historical
web page or of which records were available before each real edition deadline.
Individual cases use the source's Moscow publication day and an isolated
publication ledger. Raw sources, prompts, responses, gold, hashes and SQLite
copies remain private.

## Results

Times below are summed case wall times. A mock-published story is an API-bound
text, **not automatically a correct story**. The 12-control performance counts
include the known duplicate and ambiguous controls; independent acceptance does
not silently include them as confirmed unique positive events.

| Variant / split | Cases | Actual LLM requests | Seconds | Mock-published stories |
| --- | ---: | ---: | ---: | ---: |
| A development | 20 | 58 | 985.407 | 13 |
| B development | 20 | 61 | 1315.193 | 0 |
| C development | 20 | 46 | 1149.952 | 8 |
| A controls | 12 | 25 | 316.345 | 3 |
| B controls | 12 | 25 | 452.483 | 0 |
| C controls | 12 | 21 | 438.682 | 3 |

C development preserves 16 completed real C5 cases and four real final-C cases.
An exact offline replay matched all 34 requests and editor results for those 16
cases against final C6. That replay made **zero** new LLM calls and contributes
no invented timing. The interrupted case and prior failed trials were retained.
Full-development C memory telemetry was lost at interruption; it is unavailable,
not zero. Later control-run memory is measured normally.

### Content findings

* B published no stories over all 32 records. Its zero published errors cannot
  count as a quality success. At least one development final rejection denied
  characteristics explicitly present in its supplied approved fact ledger.
* On fresh controls, A turned New Material's six years of work with organizations
  into six years of partnership with Mistral. A also bound researcher-reported
  ReplaySSM maxima specifically to vLLM without that measurement mapping in the
  supplied message. These are two material **unsupported** relations, not
  independent proof that the statements are false in the external world.
* A correctly blocked an incorrect Grok draft with a derived percentage/unit
  problem and a mislabeled preference metric. This is an eligible event missed
  because of a bad draft, not a proven false verifier rejection. It also missed
  the concrete CERN/Mistral research partnership at relevance classification.
* C's development output still omitted the high-concurrency condition from
  LiquidAI's B300 throughput claim. It described Step 5 Preview as a function
  and Day-0 support as a product version. Typed fields and citation IDs did not
  prevent these semantic errors. Literal assembly repeated model names and
  produced awkward or partly untranslated Russian.
* On fresh controls, C preserved the CERN/Mistral research goal and avoided A's
  explicit vLLM-only speedup binding. However, it omitted researcher attribution
  from ReplaySSM measurements and promoted a personal Muse Wonder comment into
  a confirmed Meta announcement without official corroboration in its input.
  The reference had marked that authorship unresolved before generation. C also
  correctly held a draft interpreting an evolved Arena signal as a simple rename.

No complete, error-free unique-event coverage count is inferred from the number
of sends. Reviews record missing and partially covered essential facts separately
from withheld events. Disputed source chronology, legal wording and direct-API
billing scope are explicitly marked unresolved; they are not automatically
counted as proven factual errors or false holds. A source-contradicting verifier
objection does not necessarily make the entire rejection wrong if the draft has
another real problem.

### Independent control review

Of the 11 independent controls, six have resolved positive event eligibility.
The other five are optional/noise or have unavailable/ambiguous evidence. The
known cross-source duplicate is a twelfth record, outside that denominator.

| Review outcome | A | B | C |
| --- | ---: | ---: | ---: |
| Resolved eligible events with mock output, out of six | 3 | 0 | 2 |
| Resolved events without a flagged material source problem | 1 | 0 | 1 |
| Published cases with a material unsupported relation/announcement | 2 | 0 sends | 1 |
| Additional measurement-attribution omission | 0 additional | 0 sends | 1 |
| Cases with a confirmed source-contradicting verifier objection, lower bound | 0 established | 3 | 1 |

These are conservative case-level manual findings, not an accuracy estimate.
No direct contradiction of a published external-world fact was independently
established on the fresh split. That does **not** certify factual safety: two A
claims and one C announcement lacked the required grounding, and C omitted a
measurement's attribution. B's absence of posts earns no safety advantage.
A false objection is counted separately from a falsely rejected complete correct
text. For example, C's incorrect price objection to Grok is recorded, but its
correctly rejected Arena rename draft is not a false hold.

Completeness is also not the send count. C's ReplaySSM story retained the runtime
integration, caching mechanism and maxima, but lost attribution. Its development
Jev story omitted the fastest-model comparison; its DeepSeek brief omitted API
availability despite repeating six sentences. Essential facts lost in extraction
cannot be recovered by a fact-only writer. Per-case references and partial
coverage findings remain in the private audit; no unmeasured global coverage
percentage is invented.

## Architectural causes

1. **Evidence selection can precede an unrecoverable loss.** A bounded window or
   extraction quota can omit conditions or main results. Later source chunks
   must contribute facts to the existing event, rather than declare another one.
   The prototype fixes that continuation defect, but still lacks an independent
   coverage guarantee.
2. **Citation validity is weaker than entailment.** Correct numbers may be bound
   to the wrong actor, runtime, date or metric. The same model can approve its
   own reinterpretation or reject facts using external assumptions despite an
   explicit edition date. Some refusals assume an earlier current year.
3. **Discovery metadata is not fully isolated.** An uncited secondary
   `signal_title` remains visible inside the model's source context. It has no
   span ID, but can influence generation. The caller-owned cache omits the title
   while the actual prompt includes it. No production command uses this cache.
4. **Conservative guards can lose essential coverage.** The numeric guard can
   drop a model-marked essential fact with an inadequate citation instead of
   reporting the coverage loss explicitly. A later writer cannot recover it.
5. **Reported claims and independent truth are different.** Verifiers sometimes
   demand the original benchmark dataset to report an official ranking, or
   incorrectly reject a quote because its original status ID differs from the
   quoting post. Other refusals correctly catch missing scope or a wrong draft.
6. **Formatting after verification can change meaning.** Earlier development
   trials verified URL-dependent statements and only then removed their object.
   The prototype sanitizes public wording before verification and withholds
   required URL-valued facts needing a source-checked rewrite. Source URLs remain
   in evidence and private archives.
7. **Structured output is still generated output.** B sometimes produced six
   exact copies of one fact or marked ordinary capabilities as limitations.
   Deduplication removes literal copies; it cannot supply omitted information.

Entity identity currently prevents exact duplicates. Complementary fact merging,
alias resolution and conflicting-update resolution are not proven. Same-product
releases, integrations and benchmark updates must remain distinct events.

## Performance and resource boundary

Development A generated 20,495 tokens: approximately 808.557 seconds of native
decode time, 148.697 seconds of prefill and 11.916 seconds of loading. B generated
31,497 tokens with 1,169.932 seconds of decoding. C generated 27,464 tokens with
1,016.165 seconds of decoding. Fewer calls did not mean less model work.

The final paired comparison consumed 236 actual model requests. Another 151
requests from preserved diagnostic trials are reported separately, not hidden
inside an alleged efficiency gain. Some interrupted wall/memory measurements
are incomplete. Offline replays contribute zero new model requests.

These measurements explain long processing bursts; they do not reconstruct an
unsaved historical 53-call run exactly. Identical requests in earlier trials
also had different token throughput, so wall time alone is not a causal speedup
claim. Keeping the GPU loaded while waiting would not fix this decode cost.

Three-second samples include desktop GPU usage. A development peaked at
7,546 MiB and B at 7,657 MiB on an 8,151 MiB GPU. These are sampled total peaks,
not guaranteed true peaks or model-only allocation. Owned-process working-set
sums may double-count shared pages. No larger model was downloaded or claimed
to fit based on active parameter count alone.

Every completed real batch reported its owned Ollama port closed. Only the
experiment's own model job was managed; production and shared model processes
were not stopped. No model was kept active waiting for publication time.

## Publication replay and tests

* 322 Windows unittest tests passed, including 39 experimental tests. These
  verify orchestration, provenance/validation guards, dates, rendering and mock
  publication; mocked semantic verdicts do not establish real model accuracy.
* A seven-day replay of saved A results produced six nonempty mock editions,
  maximum 3,616 UTF-16 units, no URLs and no duplicate sends. B produced no empty
  post and no sends. C produced seven mock editions, maximum 2,396 UTF-16
  units, with no URLs or duplicate sends. This included the unsupported Muse
  Wonder story; mechanical publication success is not editorial success.
* Real editor cases use temporary SQLite and the existing reservation ledger,
  archive and API boundary. A repeated publication attempt cannot send again.
  No test message was sent to real Telegram.
* The edition replay is a subset-composition check with no additional LLM calls,
  not proof of capacity on the complete daily source pool. That deployment gate
  remains unmet.

Gitleaks and exact-index/outgoing-history checks exclude credentials, personal
files, live configuration, source archives, databases, logs and experiment tools.
No dependency was added. Required GitHub checks remain Python 3.11, Python 3.14
and secrets; branch protections are unchanged.

## Production and next decision

The production checkout, protected settings, seven historical digests and their
41 inclusion records remain unchanged. Collection and the 21:00 Europe/Moscow
task continue with the stable editor. This confirms the deployment boundary,
not a promise that the stable editor's known content problems are solved.
PremWire was not changed.

The next candidate needs an explicit distinction between attributed reports
and independent measurements, coverage accounting for rejected essential facts,
and isolation of uncited discovery metadata with a matching cache identity.
Those changes need a new unseen corpus and source review. Tuning them on these
controls and reusing the same controls as independent evidence would invalidate
the experiment. The evidence does not establish that a particular larger local
model would solve the problem within this laptop's resource limits.

See the [architecture and acceptance protocol](editorial-quality-v2.md) and
[experimental PR](https://github.com/Lovekach/ai-news/pull/9).

### Source references for the control findings

The review uses immutable captured text; current live X pages may be unavailable.
The source claim and the actor reporting it must not be conflated.

* [Mistral quoting New Material](https://x.com/MistralAI/status/2110377713525796942)
* [vLLM quoting the ReplaySSM researcher](https://x.com/vllm_project/status/2109865690031411349)
* [Lambert's Muse Wonder comment](https://x.com/natolambert/status/2109694746562097282)
* [Mistral/CERN research goal](https://x.com/MistralAI/status/2110684732103041474)
* [Artificial Analysis on Grok Voice](https://x.com/ArtificialAnlys/status/2110421964095713743)
* [Arena's signal update](https://x.com/arena/status/2110048840082653647)
