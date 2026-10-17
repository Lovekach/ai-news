# Architecture

The sentence-verdict changes described on this branch are experimental and
have not passed editorial acceptance. See [evaluation](docs/EVIDENCE_EVALUATION.md)
before considering deployment.

AI News is a local Windows application with separately scheduled collection, editing and publication. There is no resident Python scheduling loop.

## Modules

| Module | Responsibility |
| --- | --- |
| `__main__` | CLI, configuration and routing |
| `feeds` | Bounded HTTPS downloads, checks before redirects, HTML extraction and RSS/Atom/sitemap parsing |
| `telegram_public` | Public pages, post cursors, edited/deleted visible posts and ad filters |
| `x_rss` | RSS mirrors and canonical X URLs; isolated mirror failures |
| `store` | SQLite items, polling state, drafts, edition ledger and corrections |
| `pipeline` | Source polling, editorial prompts, evidence and model verification |
| `quality` | Semantic guards, event signatures and repetition checks |
| `evidence` | Source-bound sentence verdicts, literal identities/units, claim ledger and final sentence integrity |
| `digest` | Draft parsing, sentence-aware card compaction and legacy interval helpers |
| `daily` | Moscow day selection, grouping, verified merge cache, priority and output allocation |
| `model_session` | Independent localhost Ollama server and owned-process cleanup |
| `lock` | Windows file locks against overlapping invocations |
| `telegram` | Captured DPAPI token loading and Bot API calls |
| `security` | Redaction before diagnostic storage/output |

## Storage and states

Entries are keyed by URL. Official feeds initially establish a `baseline`; new records become `pending`. Initial Telegram/X scans can queue recent visible posts. Editing retrieves evidence and creates a `ready` draft or marks it `needs_review` / `skipped`.

An edited unpublished Telegram post invalidates its draft. Visible deleted posts can be retired. Posts beyond the public page's range cannot be exhaustively audited.

Editions use `daily:YYYY-MM-DD` keys. A `BEGIN IMMEDIATE` transaction checks availability and reserves the slot and member URLs before sending. A receipt sets `sent`; an error after the send attempt sets `send_uncertain`, preventing automatic retry. Telegram's remote server cannot participate in the database transaction: uncertain delivery needs manual investigation.

Keep the ledger when moving an installation. A second copy with a fresh database against the same channel does not inherit duplicate history.

## Editorial flow

1. Collect bounded feed/page data with timeouts, cache validators and source backoff. No LLM calls.
2. Filter stale articles, promotion, unsupported reposts, speculation and prereleases during evening editing.
3. Generate a Russian draft, then request one source-bound verifier verdict for each sentence. Daily mode skips the unconditional style rewrite. Exact quotes, identities, units and measurement relations pass deterministic guards; optional unsupported sentences can be removed without a new model request. A rejected main event requires bounded revision or review.
4. Group current-day approved records using structured entity/version/event/date/provider metadata, with legacy signatures for drafts without a valid ledger. Combine intact verified sentences and verify against separate originals; failure retains the latest approved draft.
5. Archive the longer edition, and allocate Telegram's budget by importance. Concrete details and caveats take precedence over explanatory filler. Preserve complete sentences.
6. Reserve a daily slot and send one Telegram message.

Coverage depends on source access. Checks do not independently verify every source assertion. Grouping may miss unusual wording or conflate ambiguous event descriptions.

`editorial_audit` retains decisions, verification results, source-bound claim
ledgers and revision reasons. No second database or migration is required.
`source_dates` separates publication/update/event dates; discovery stays in
`items.created_at`. Unknown dates are retained as null. Deterministic guards run
again on approved, merged and shortened cards. See
[EDITORIAL_QUALITY.md](docs/EDITORIAL_QUALITY.md) for checks and limitations.

### External input boundary

Feed/article and Telegram requests check HTTPS and their host allowlists before following redirects. X mirror dispatchers use the same redirect handler without a fixed host list, because the destination mirror can change; each hop still rejects credentials, local names and non-public IP literals. These checks do not pin DNS resolution. Configure trusted services rather than accepting arbitrary user-supplied URLs.

News and model responses remain data: structured responses pass editorial checks and never become executable commands. Subprocess arguments are controlled by the application. CI uses synthetic fixtures and mocked publishing, without production tokens or a running model.

## Scheduling and resources

Collection uses short Windows tasks every minute (official feeds/X) or five minutes (Telegram). Each official feed also has its own due time. Failed sources back off.

Editing runs at 18:00, 20:15 and 20:50 MSK with a finite budget. The model server binds to `127.0.0.1:11435`; an occupied port is refused. A Windows Job Object owns the server tree and terminates only those children when closed. The last editorial invocation stops before the publisher.

The final invocation also checks for late pending items until 20:59, sleeping
outside the Ollama session. No model is kept alive solely while waiting for an
arrival or for the publisher. Earlier editorial invocations exit when finished.

The publisher runs at 21:00 MSK, accepts 20:56–21:04 and does not start Ollama. Selection covers the current Moscow calendar date through the cutoff; another day's records are excluded. Moscow UTC+3 is explicit and independent of the computer's time zone. The implementation is fixed to this schedule.

Tasks run as an interactive Windows user without administrator elevation. The laptop must be awake and that user logged in. Publication does not catch up hours after a missed window.

## Public/private boundary

Code, tests, docs and sanitized examples can be published. Live settings, tokens, raw news, archives, SQLite files, correction manifests, schedule backups and operational audits remain local. The runtime does not depend on another project's checkout, database, settings or tasks.
