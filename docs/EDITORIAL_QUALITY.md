# Evidence and daily edition quality

AI News uses its existing local writer, editor and fact verifier. Quality checks
produce concrete findings and review decisions; they do not assign a numerical
score or certify that every claim is true.

## Provenance

- An account posting a message is not automatically the product developer,
  founder, investor or speaker in a quoted announcement. X RSS quote boundaries
  and quoted status links are retained when supplied by the mirror. Missing
  boundaries cannot be reconstructed reliably from a previously flattened post.
- The source URL and account are supplied to all editorial stages. Long source
  envelopes retain the beginning, attribution/condition excerpts and the end,
  rather than silently losing README footers. These excerpts remain verbatim.
- Source publication, source update, original article publication and explicit
  release-note event dates have separate fields in `source_dates`. Discovery
  remains `items.created_at`. Unknown dates remain null. Sitemap `lastmod` and
  Atom `updated` alone cannot establish an original publication date.
- A bare GitHub repository link in a repost needs a dated primary announcement.
  Stable releases are checked through GitHub's bounded HTTPS API. Only releases
  published before the repost can establish its freshness; a later release
  cannot retroactively date that earlier message.
- Explicit retrospective launch/funding posts require event-date verification.
  A benchmark communication does not establish a new model release.

## Checks

Generation preserves a product name in the headline, attribution, units,
comparison conditions and meaningful details. Numeric presence checks normalize
decimal commas without rounding values. Semantic guards cover observed mistakes:
independent products attributed to unaffiliated companies, quoted launches
attributed to commentators, benchmark scores called accuracy without evidence,
unattributed benchmark comparisons, lost source-install scope, and unsupported
data-safety guarantees. Existing guards for weights/code, tokens/steps and access
conditions remain active.

The LLM verifier is still required. A JSON response cut off by the output-token
limit gets one bounded retry with the same schema and prompt. Partial JSON is
never accepted or repaired into facts. Failed checks retain the original article
for investigation and send the item to `needs_review`.

An explicit verifier rejection requires a text revision. Later checks of smaller
claim groups cannot override it. Measurement findings are reported together, so
the existing bounded revision loop can repair all observed unit/condition errors.
Writer, style-editor and revision responses are retained in the private audit.
The verifier and correction editor use Ollama's native chat API with separate
system instructions and JSON evidence in a user message. The same installed model and non-thinking mode
are retained. An experimental thinking/structured-output combination returned JSON
inside reasoning with an empty final response on the installed runtime and was
rejected. Only the final content is accepted. Tokens and overall runtime remain
bounded by the existing editorial deadline; no additional model or service is added.

Measurement guards distinguish context tokens from characters, reasoning mode
from agent-only restrictions, aggregate parallel throughput from a single response,
and milliseconds from seconds. Short GPU announcements preserve stated interfaces
and cooling. A benchmark index leader cannot inherit another model's speed or cost
record. Source-backed translation repairs cover context/vocabulary units, the
cited parallel throughput condition and an index score mislabeled as a subtest.
Explicit author measurements retain attribution without inventing a developer role.
Numbers and facts still require the unchanged checks, and original source text
is never edited. Missing evidence remains a review decision, never a numerical
quality score.

Event grouping identifies the main product, its explicit version, brand namespace,
event type and distinct hosting provider. Generic versioned product names are
supported; a competitor in a comparison does not become the subject. Original
announcement titles establish availability events even if Russian headlines differ.
App, developer API and global notices of the same rollout can form one story;
model releases, patches, benchmarks and distinct provider launches remain separate.
Merged text is checked against original source excerpts, not earlier paraphrases.
For availability notices, intact approved sentences are combined first and
verified against every original and the newest state. No new prose is invented
in this path; contradictions must pass the same verifier before caching.
The verifier receives separate dated original documents when they fit the
existing evidence budget; a short new notice does not cancel earlier details
without a contradiction. Relative "today" wording and leaked editorial
instructions are removed from generated prose, preserving date metadata.
An invalid merge receives at most two revisions within the existing deadline;
only a revised, verified result can replace the latest approved fallback.
Availability is not a new model release; a combined index score cannot be
assigned to a named subtest. Expert counts retain their per-block scope.
Full primary announcements take precedence over short X echoes in the link budget.

A transient article connection/timeout failure gets one editorial retry before
review. It never approves a story or bypasses factual checks. Repeated failures
are held rather than creating an unbounded retry loop.

`editorial_audit` records state decisions, verification results and revision
reasons in the local database. Previously approved drafts, merged drafts and
shortened Telegram cards pass deterministic checks again before sending. Failed
stories are held for review; they do not make an empty post publishable.

Relational checks also reject incorrect score differences, unsupported per-task
cost ratios and savings, effort settings presented as separate models, reversed
max/xhigh output comparisons, and a non-leading rank described as the leader.
Only arithmetic with explicit endpoints is checked; ambiguous tables remain a
verifier responsibility. A new score difference may pass numeric-presence checks
only when both source endpoints and the arithmetic agree.

Throughput claims retain the stated GPU count, device, precision and per-user
scope. Parallel workloads cannot be inferred from a per-user rate. Advertised
context maxima retain attribution and are distinct from explicitly tested
lengths. A disclosure alone does not establish a vulnerability fix; day-zero
support is not a separate technology. Opinions retain attribution. Access or
pricing statements without corresponding source evidence are held, including
editorial instructions accidentally copied into prose.

Final checks run per card before and after compaction. A failed card receives
`needs_review` and a private `final_quality_gate` audit record; other qualifying
cards can still publish. Compaction keeps the benchmark result sentence and its
hardware conditions, or omits the card when those details cannot fit. An exact
single article link can join a short notice to its official announcement when
neither has a conflicting product/event signature. Multi-link roundups do not
establish that identity.

## Edition and resources

The existing publication schedule stays at 21:00 Europe/Moscow, once per day.
Telegram's application budget is **3900 UTF-16 code units**, even if a larger
limit is configured. Primary links and complete qualifying sentences survive
compaction. The full local edition includes coverage findings and date
provenance. The transaction and uncertain-delivery ledger still prevent retries.
Model releases, access expansions and developer tools receive an explicit priority
tier before keyword weights. Compaction favors concrete specifications over generic
benefits and keeps concurrency conditions attached to throughput results.
Subscription and paid API conditions survive even when the writer puts them
outside the main paragraph. Repeated reasoning-mode definitions are omitted
without dropping distinct numeric details.

The existing final evening editor task can pick up late queue arrivals until its
20:59 deadline. Its short SQL/sleep waits run outside the owned Ollama session;
the model starts only for work and its process tree closes afterwards. This is a
bounded evening window, not a new schedule or an all-day LLM loop.

## Verification and limits

Run the Windows regression suite with:

```powershell
python -m unittest discover -s tests -v
```

Tests use temporary databases and mocked model/publication calls. Real-model
comparisons must use separate databases, frozen unmodified inputs and mock
senders; preserve the production queue, credentials and publication ledger.
Collected source text, comparisons, audit logs and archives remain local and
must not be committed.

These checks cannot recover missing X quotes, establish an unknown event date,
guarantee source coverage when mirrors fail, or replace independent verification
of a vendor's benchmark. A null date or held story is preferable to an invented
fact. News arriving after the daily cutoff is outside that edition; the current
calendar-day policy does not silently turn it into the next day's news.
