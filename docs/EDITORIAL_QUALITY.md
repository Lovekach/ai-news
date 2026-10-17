# Evidence and daily edition quality

**Experimental branch, not approved for production.** Exact source quotes and
passing unit tests do not prove that a sentence is entailed by its evidence.
Real-model acceptance found remaining factual regressions; see
[evaluation and release blockers](EVIDENCE_EVALUATION.md).

AI News uses its existing local writer and fact verifier. Quality checks
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

Generation requests a product name in the headline, attribution, units,
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

Daily mode uses one writer request and one sentence-level verifier request on
the successful path. The unconditional style-editor request is omitted. The
legacy verification path remains for older drafts without a valid ledger.
Writer, verifier and revision responses are retained in the private audit.
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
Original source text is never edited. Missing evidence remains a review
decision, never a numerical quality score.

### Source-bound claim ledger

The verifier returns a verdict for every stable sentence ID, including the
headline. Each verdict carries a source index, up to three separate exact
continuous evidence spans from that source,
entity, version, event, explicit date, attribute, value, unit, conditions,
provider, evidence basis and entity kind. These records use the existing private
`editorial_audit`; there is no new database, model or service.

Missing/duplicate IDs and spliced or invented quotations fail closed. Every
evidence span is checked individually against the original; quoting separate
facts does not permit inventing the relationship between them. Source
typographic apostrophes/quotation marks and whitespace can be located through
a narrow canonical match, but the ledger stores the original source substring.
Changed words, identifiers, signs and numeric values are not repaired this way.
URLs are assigned by the application. Names with numeric suffixes cannot change
to another version merely because the replacement number occurs elsewhere.
Literal source-validated entity numbers are distinct from measurement numbers.
Explicit quantities normalize K/M/B/T scales and Russian abbreviations, while
tokens, characters, parameters and time units retain their meanings.

Invented metadata fields are cleared and recorded as metadata repairs; they
cannot supply an event date, value or measurement condition. An actual invented
number or changed unit in prose still fails its corresponding source check.
Entity antecedents can be anchored elsewhere in the same original document.
Source publication and detection dates never silently become release dates.

Unsupported optional sentences are removed locally. The first main-event
sentence must survive; a minor surviving detail cannot replace a rejected
event. A rejected headline can use a verified literal entity as its safe title.
Benchmark statements retain source attribution, added once when necessary.
Failure of the main event still uses the existing bounded repair/review path.
No later fragment check silently overturns a semantic verifier rejection.

Unit/identity/arithmetic/comparator guards operate on the sentence's cited spans,
not a bag of all numbers from the article. Coverage heuristics about unrelated
omitted specifications cannot overrule a supported sentence. Throughput
statements must retain their measured configuration and scope. These literal
checks complement semantic verification; they do not prove entailment by
themselves.

An explicit source relation such as `scores N on Metric` binds a score to that
named metric. A subtest cannot inherit the overall index score, and a single
test result cannot become one result for a list of different tests. Where an
otherwise verified score omits its metric without asserting another test, the
literal source metric can supply its scope; the original text is retained in
the audit. Ambiguous equal scores across different metrics are left to semantic
verification, rather than resolved by numeric coincidence. Unstructured tables
and other grammatical forms are not completely covered by this narrow parser.

Event grouping identifies the main product, its explicit version, brand namespace,
event type and distinct hosting provider. Generic versioned product names are
supported; a competitor in a comparison does not become the subject. Original
announcement titles establish availability events even if Russian headlines differ.
App, developer API and global notices of the same rollout can form one story;
model releases, patches, benchmarks and distinct provider launches remain separate.
The original subject title can expand a compatible abbreviated product name;
it cannot replace an unrelated entity. A company name alone is insufficient
to merge multiple product launches from that company.
Merged text is checked against original source excerpts, not earlier paraphrases.
For stories with valid claim ledgers, intact approved sentences are combined and
verified against every original and the newest state. No new prose is invented
in this path; contradictions must pass the same verifier before caching.
The verifier receives separate dated original documents in a bounded excerpt
budget; exact quotes are validated against their separate complete originals.
A short new notice does not cancel earlier details
without a contradiction. Relative "today" wording and leaked editorial
instructions are removed from generated prose, preserving date metadata.
An invalid structured merge retains the latest individually approved story;
it does not start a second merge writer/revision cascade. Legacy merges retain
their existing bounded revision behavior.
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

For ledger-backed stories, the final formatter may omit whole approved
sentences, but cannot edit their contents or detach a measurement condition
inside one sentence. Russian numeric abbreviations such as `тыс.` retain the
following unit. A source hash prevents reuse of stale ledgers, and merged
ledgers are bound to the complete group fingerprint. Concrete semantic
contradictions still fail final checks. Historical drafts without ledgers keep
the legacy final quality gate.

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
