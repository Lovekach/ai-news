# Editorial coverage and resilience candidate

This is an experimental change from stable `main`. It does not merge the
previous editorial experiments and must not be deployed merely because its
unit tests or mocked publication pass.

## Narrow changes

- Reuse the existing verified-subset mechanism. Remove locally disproved
  optional explanations while protecting the main event, headline, caveats,
  licensing, access and measurement conditions. Reverify the exact remaining
  text before marking it ready. A malformed verifier response still holds it.
- Do not restore previously generated quantitative sentences while repairing
  a quantitative or benchmark error. Restoration is not evidence.
- Scope automatic-launch detection to related words, rather than words in
  unrelated sentences. A competitor's Preview label is not the subject's
  preliminary status. Recognize named evaluation arenas as attribution, while
  still verifying their actual ranking and scope.
- Reuse the existing GitHub release-date lookup for an exact tag. Require
  matching tag identity, a stable published release and `published_at` no later
  than the source post. Preserve source publication/update/discovery values;
  commit creation and repository modification are not publication dates.
- Quarantine an invalid merged-cache card without aborting unrelated cards.
  Check each shortened card, then the exact assembled public payload and its
  selected provenance before archive/reservation/network. A changed payload or
  unresolved duplicate selection blocks the send globally.
- Preserve licensing conditions during compaction, complete writer headlines
  when styling damages them, and source-code-style library display names when
  removing public links.

The configured model, context settings, collectors, scheduling, live settings,
production state, ledger and Telegram format are unchanged. There is no new
model, resident process, retrieval subsystem or publication adapter.

## Evaluation protocol

Run the full Windows unittest suite with temporary stores and mocked model and
publication calls. The partial-failure regression prepares ten independent
cards, damages one merged cache, and requires the other nine to survive with
the bad card diagnosed locally. A repeated run must not send again.

Real-model evaluation uses identical saved sources, isolated database copies
and mocked Telegram. Disclosed experimental data is development data. Reserve
a new cohort without selecting previous editorial outcomes, freeze code,
annotate source facts and importance before model outputs, then compare both
versions. Preserve complete before/after payloads and refusals privately.

Measure correct coverage of important confirmed events, not just send counts
or rejection counts. Report false holds separately from justified refusals,
and report missing evidence separately from generation/verifier failures.
Count unsupported explanatory claims and lost conditions as quality failures.
Retain call, generated-token and elapsed-time measurements.

## Acceptance and limits

Deployment requires greater correct important-event coverage, zero observed
critical errors, no duplicate/false-merge regression or new unjustified holds,
working partial-failure isolation, exact final-payload checks and viable runtime.
Any failed criterion or insufficient control coverage means a Draft PR.

The structured verifier remains a small model and can incorrectly approve
unsupported explanations. Deterministic checks are conservative and incomplete;
they do not prove arbitrary causality or cross-card contradictions. The existing
grouping and merge checks still handle related event histories. There is no
claim that these narrow changes eliminate every factual or grouping failure.

No real test posts or historical re-publication are allowed. Production retains
its continuous daily window, one scheduled edition at 21:00 Moscow time, a
3900-UTF-16 public limit, private sources/archive and conservative send ledger.
Laptop wake stays disabled; sleeping or offline hardware remains an availability
limitation. Finite evaluation jobs close only their owned Ollama process tree.

## Evaluation result: do not deploy

The frozen candidate passed 323 Windows unit tests, but failed the new held-out
editorial evaluation. The retrospective cohort contained 57 real records and
ten important source-confirmed events, annotated before either model output.

| Measure | Stable baseline | Candidate |
| --- | ---: | ---: |
| LLM calls (attempted and completed) | 68 | 69 |
| Generated tokens | 19,482 | 18,752 |
| Elapsed seconds | 839.661 | 803.195 |
| Public cards | 9 | 9 |
| Important events with a supported card | 4 / 10 | 3 / 10 |
| Extra duplicate cards | 0 | 1 |
| Public UTF-16 units | 3,877 | 3,887 |
| Correct neighbors surviving one corrupt cache in fault injection | 0 / 9 | 9 / 9 |

One otherwise supported candidate event also has an erroneous duplicate; only
two important events are unambiguously clean across their entire public report.
The candidate retained critical factual problems, including a finite account
limit rendered unlimited and a median cost rendered as a mean. Better card
isolation therefore does not establish better editorial coverage or correctness.
Both complete payloads passed the actual Telegram adapter with HTTP mocked;
this establishes transport integrity, not factual quality.

These are single-run measurements and manual source-based adjudications, not
an external human score or a prospective performance guarantee. Some primary
release metadata was captured separately before evaluation; original news
records were not rewritten. The independent cohort is now disclosed and must
not be reused as an independent control after further tuning.

Keep this PR Draft. Production must remain on stable main; the deployment
criteria above have not been met.
