# Continuous daily coverage

## Defect and policy

The old daily selector started at Moscow midnight and ended at publication.
An item posted after 21:00 was too late for that edition and too early for the
next calendar-day selector. All eight pending evening records in the saved
October 18 audit reproduced this gap. It occurred before the editor was called.

The daily slot remains `daily:YYYY-MM-DD`. Its nominal source interval is now
**[previous day 21:00, edition day 21:00)** in Europe/Moscow. Exactly 21:00 belongs
to the following edition. Early invocations cannot see future material; late
invocations within the existing tolerance cannot extend the fixed cutoff.
The Windows trigger remains 21:00; no task definitions change.

Two dates are used without substituting one for the other:

- `items.published`: the source's publication timestamp.
- `items.created_at`: first insertion, stored by SQLite in UTC.

Both dates must be valid and earlier than the effective cutoff. A source
published in the interval is eligible, as is a previously published source
first discovered in the interval. Fresh unconsumed backlog is also eligible
before the next cutoff, covering interrupted editing and missed editions.
The selector independently excludes every URL in `digest_items`, regardless of
its current item state. Sending or uncertain receipts must never be retried
by resetting a news row.

## Freshness and recovery limits

Eligibility is not approval. The existing editor still checks the source's
24-hour age, original-article dates, evidence, relevance and factual claims.
The final composer additionally checks ready drafts against that same source
age limit: late discovery cannot make a stale draft fresh. Event grouping and
published-fact deduplication remain unchanged.

After a missed edition, fresh unpublished news can reach the next normal run.
Old news does not receive an unlimited catch-up allowance. In particular,
late-discovered news can expire before the next send; this is a freshness
rejection, not silent exclusion by the calendar boundary. No historical edition
is reconstructed, and no post is sent outside the existing publishing window.

No schema migration, ledger checkpoint reset or source-date rewrite is required.
Old calendar-based receipts retain their IDs, text and delivery state. The
private archive adds the effective UTC coverage interval; its original source
and discovery timestamps remain intact. Reservation and uncertain-send handling
continue to use the existing atomic ledger transaction.

## Verification

- Fourteen new offline regressions cover adjacent cutoffs, 20:59:59 / 21:00:00 /
  21:05, late discovery, fresh backlog, stale material, future/invalid dates,
  old-ledger transition, uncertain delivery and repeat runs.
- Existing synthetic historical fixtures now set their discovery clock
  explicitly rather than inheriting the test machine's current date. Their
  source text is unchanged. A merge fixture's last update now precedes 21:00,
  respecting the newly fixed cutoff.
- The full Windows Python 3.14 suite passed: **297 tests**.
- A private replay used all eight unchanged saved source rows and their original
  timestamps. The old selector returned **0/8**; the new selector returned **8/8**
  for the next evening editor. The normal source-age, missing-evidence and
  insufficient-text guards still ran.
- A separate SQLite and mock LLM/API exercised prepare, compose, archive,
  reservation, send completion and a repeated publish call. Only the official
  announcement had a supplied positive mock editorial decision. Other model
  decisions were negative controls, not judgments of their real news value.
  There was **one mock Telegram API call**, **zero real model calls**, and no
  real send. Publication/discovery/source fields and the prior receipt remained
  unchanged. Current HTTP retrieval was used; it does not establish historical
  availability of those page bodies.

This verifies temporal coverage and publication guards, not LLM quality or a
promise that eight records should produce eight stories. The model, prompts,
verifier, collectors and public Telegram formatting are unchanged. Source
inputs, replay databases and audit output stay private and outside Git.
