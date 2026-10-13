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

A transient article connection/timeout failure gets one editorial retry before
review. It never approves a story or bypasses factual checks. Repeated failures
are held rather than creating an unbounded retry loop.

`editorial_audit` records state decisions, verification results and revision
reasons in the local database. Previously approved drafts, merged drafts and
shortened Telegram cards pass deterministic checks again before sending. Failed
stories are held for review; they do not make an empty post publishable.

## Edition and resources

The existing publication schedule stays at 21:00 Europe/Moscow, once per day.
Telegram's application budget is **3900 UTF-16 code units**, even if a larger
limit is configured. Primary links and complete qualifying sentences survive
compaction. The full local edition includes coverage findings and date
provenance. The transaction and uncertain-delivery ledger still prevent retries.

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
