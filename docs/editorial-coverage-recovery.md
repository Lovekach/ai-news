# Editorial coverage recovery: experiment in progress

**Status: Draft, not approved for deployment.** Production remains on stable
`main` (`db46dcd`). Queue improvements alone have not demonstrated better final
editorial coverage. Passing software tests is not evidence that generated news
is factually correct.

## What the earlier ten-event study actually showed

The disclosed PR #13/#14 materials are development evidence, not an independent
control. The following traces distinguish failure of a particular generated
card from whether the source could support a safer short story.

| Event | Evidence and first material loss | Final outcome |
| --- | --- | --- |
| DeepSeek Flash 1017 | Official source available; a repost adds unsupported throughput claims. PR #14 splits the launch by incidental pricing/availability wording and loses part of the version identifier. | Baseline publishes one supported card; the earlier candidate publishes conflicting duplicate coverage. |
| Beam Agent Arena | Primary evaluator available; generated text mixes model/laboratory rankings and loses the open-model ranking scope. | Baseline holds a genuinely faulty card. The earlier candidate also introduces unsupported licensing implications. |
| Ollama v0.40.6 | Updated-only feed time does not establish original publication. Exact-tag metadata can supply `published_at`. | Baseline holds before generation; the earlier candidate recovers the date but the writer rejects relevance. No final length-budget loss. |
| Codex maintenance workflow | Official source describes a current engineering workflow; the writer returns low relevance. | Lost before Ready. The earlier replay bypassed the production queue, so it cannot prove slot starvation. |
| Claude Code v2.1.302 | Updated-only feed needs original-date evidence. Once supplied, the writer changes a 100-account limit to unlimited, although 100 is present in model context. | Baseline date hold is safe; the earlier candidate's published card is factually incorrect. |
| Muse Spark WebDev evaluation | Current primary evaluation, distinct from the model launch; supported Ready card exists. | Baseline publishes it; earlier candidate loses it at selection to a lower-value analysis and duplicate coverage. |
| MOSS Image / vLLM-Omni | Primary integration source, developer and model size available. License wording concerns launch/inference code, not necessarily weights. | Supported integration reaches Telegram in both versions. |
| Kimi K3 AMD AgentX | Hardware/throughput context is available. The writer changes 87.4% more tokens per dollar to 87.4% lower cost and loses per-user throughput. | Held before Ready; refusal of this faulty card is justified. |
| Astra Pro ChatGPT update | Brief but sufficient official update. | Supported story reaches Telegram in both versions; some review/progress details are lost. |
| Arena Alignment Index entrants | Primary source says two new laboratories and three new models. Generated text changes new entrants into the entire field and changes rank scope. | Justified hold before Ready, not exclusion by Telegram length. |

The baseline covered four of the ten important events correctly. Three earlier
candidate cards carried supported event facts, but two coherent whole events
remain under the stricter rule that erroneous duplicate coverage is a failure.
These definitions must not be silently interchanged.

The six baseline losses comprise two original-date evidence holds, one relevance
loss and three faulty generated cards. Broad gate messages are sometimes poor
diagnostics; they do not make an incorrect card safe to publish.

## Candidate boundaries

The experimental code separates cheap signals for eligibility, available
evidence and editorial importance. None approves claims. It adds:

- Event-type priority independent of generated length or repeated keywords,
  without a company ranking.
- Full version identifiers and repository/exact-tag identity. Different explicit
  integration targets and benchmark events remain separate.
- Primary event representatives before alternatives; retained alternatives can
  still be processed when no eligible verified representative exists. Invalid
  Ready rows must not suppress a usable alternative.
- Recap and retained old-quotation checks before expensive generation.
- Exact GitHub tag publication metadata, with tag/as-of/prerelease and existing
  freshness checks. Feed update time is not substituted for event time.
- Queue, eligibility, deferred-duplicate and final-selection audit reasons.

Writer, style and semantic verifier functions/prompts, model, collection adapters,
publication schedule, model-session ownership, transport and ledger are unchanged.
The follow-up also extends the existing exact evidence alignment helper to
flattened pictographic bullets. It may recover one literal source slice; every
claim still requires the existing semantic verifier. It is not automatic approval.

## Completed real-model comparison: iteration A

Inputs were fixed before substantive new model outputs: all 36 records in one
21:00-to-21:00 cutoff interval and all 41 in the next interval. The initial
interval contained only three confirmable important positives, so the complete
next interval was added, without outcome/source/topic exclusions. There were
nine new important events, seven previously disclosed source records kept out
of that denominator, 38 negative records and 23 unresolved records. Unresolved
does not mean irrelevant. Full source snapshots and model responses stay private.

Annotation was a manual source-only review by the coding agent, not independent
human expert scoring. A source-only identity guard correction preceded all
substantive candidate outputs; the implementation and gold were then frozen.
One exploratory replay used the wrong trigger grid and is excluded below.

Both versions used the same saved source bodies, original/discovery dates,
historically bounded publication history, real Qwen 3.5 9B, isolated SQLite,
the actual `prepare_daily` entry point and mocked Telegram. The corrected grid
was 18:00, 20:15, 20:50 MSK plus late polls until 20:59; actual processing time
advances the simulated clock. Existing evening deadlines were retained. This
is a retrospective replay, not a reconstruction of historical internet access.

| Replay | Baseline | Iteration A |
| --- | ---: | ---: |
| 36 records: completed LLM calls | 25 | 25 |
| Generated tokens | 5,813 | 5,813 |
| Elapsed seconds | 300.939 | 279.155 |
| Final cards / UTF-16 units | 3 / 1,864 | 3 / 1,864 |
| 41 records: completed LLM calls | 45 | 45 |
| Generated tokens | 14,598 | 14,598 |
| Elapsed seconds | 704.891 | 792.543 |
| Final cards / UTF-16 units | 9 / 3,864 | 9 / 3,892 |

These are single runs, not a statistically reliable speed comparison. There was
no call/token saving. All important sources received an attempt; observed losses
cannot be attributed to editor starvation in these replays.

### Important-event adjudication of the exact final payload

| Event | Baseline | Iteration A | Remaining issue |
| --- | --- | --- | --- |
| Ollama / DeepSeek cloud integration | Correct | Correct | Repetitive prose, but supported new integration. |
| Kimi DSpark decode result | Partial | Partial | Correct headline measurement; unsupported comparator replaces the source's tested-configuration scope. |
| vLLM 0.32.0 | Held | Held | Spliced evidence; other scope implications also need checking. Not a proven clean-card false refusal. |
| D3 vLLM recipes | Partial | Partial | New integration supported, but benchmark drops checkpoint-server/equal-workload conditions. |
| MiniMax Artificial Analysis evaluation | Held | Held | Generated text reverses cheaper versus more expensive. |
| Speculators 0.9.0 | Partial | Partial | Hidden-state storage and speculator quality broaden to memory/generation quality. Baseline additionally loses the forward-training qualifier; candidate removes that claim during shortening. |
| DeepSeek Artificial Analysis evaluation | Held | Held | Non-hallucination improvement becomes an error rate that supposedly falls from 4% to 33%. |
| Ming / vLLM-Omni integration | Correct | Correct | Parameter breakdown omitted, without a false size claim. |
| Gemini Notebook co-creation | Correct, brief | Correct, fuller | Candidate retains Review/plan editing; baseline has one truthful sentence. Rollout timing omitted. |

Under conservative whole-card acceptance the result is **3/9 to 3/9**. Six of
nine events reached Ready and Telegram in each version, which is not six correct
cards. Accepting the abbreviated D3 benchmark condition raises both scores by
one equally. Ambiguous Kimi comparator and FP8 storage wording are disclosed
review sensitivities, not proven numeric contradictions or a claimed repair.

No exact event duplicates or false merges were observed in these final payloads;
that does not establish a general absence of those bugs. Both editions still
publish an old policy reminder and an old weekly recap. No wholly clean card
was proven falsely rejected by the verifier. Some held sources could support a
safer shorter card, but the unchanged writer did not create one.

One previously disclosed fund story fails in both editions: an aggregate share
commitment is incorrectly made the fund's future stake. Candidate length
allocation exposes a second unsupported assertion, changing a pledge to an
already completed donation. These are one bad card with one versus two critical
claims, not two separate failed events. Known disclosed material is excluded
from the independent important-event denominator, but remains a deployment risk.

Four actual Telegram-adapter calls were intercepted with fake HTTP. Each exact
payload matched the replay, was link-free and below 3,900 UTF-16 units. Each
replay produced one mocked send and blocked the repeat invocation. No request
was sent to a real channel.

## Follow-up B and the remaining gate

After A became development evidence, one bounded follow-up fixed generic
availability/release cues, Russian recap forms, case-sensitive Git tags,
eligible-Ready reuse and exact flattened-bullet evidence alignment. It has
333 passing mocked Windows tests. Its code was frozen before opening a new
60-record control, containing eleven source-confirmed important positives.
That partial-day cohort and source-only gold are sealed before either B output.

Missing original captures were obtained with the unchanged stable reader before
model outputs, uniformly for sources requiring them: 11 fetches, eight successful,
three HTTP errors, plus five exact GitHub metadata captures. Both replay arms
will receive identical captures. Retrieval took 47.491 seconds; cached replay
timing must not be presented as end-to-end live-network latency. Reader failures
or truncated abstracts must not be replaced with invented source material.

**The B real-Qwen baseline/candidate comparison has not run.** A's numbers above
do not validate the B code in this Draft. Experiments are held outside the
production evening interval. Complete that paired comparison, source-grounded
final-card adjudication and adapter proof before considering any adoption.

## Deployment decision

**Do not merge or deploy yet.** A fails the coverage criterion and exposes
additional bad content; B has only deterministic regression evidence so far.
No numeric quality score is assigned. Do not merge earlier Drafts wholesale,
relax fact checks or send historical editions to manufacture apparent coverage.

Production configuration, tokens, data, archives, publication ledger, Windows
tasks, power policy and running model settings are outside this experiment.
One daily 21:00 MSK edition remains configured. `WakeToRun=false` remains intact;
an asleep/offline host cannot guarantee delivery. PremWire is untouched.
