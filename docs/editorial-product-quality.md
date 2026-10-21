# Editorial product quality candidate

This change is experimental. Passing unit tests or sending to a mocked Telegram
adapter does not establish editorial correctness. Do not deploy it until the
independent product acceptance gates pass.

## Changes

- Build on the existing event signature with named integration/benchmark scope,
  version variants, repository provenance, source publication day and explicit
  event dates. Canonical post references connect same-event echoes across
  adjacent days. A mirror hostname is not a repository owner.
- Bind percentage comparisons to their source clause. A metric's plus sign does
  not establish improvement over a previous release. Distinguish percentages
  from percentage points and retain the existing measurement verifier.
- Preserve a complete writer headline when a style rewrite fails the headline
  integrity check, including saturation of the generation schema's title limit.
- Require a retained non-commercial restriction when describing affected open
  weights.
- Audit the exact assembled public payload against its selected source groups
  before reading credentials, archiving, reserving or sending. Check source-bound
  duplicate identities, existing factual/integrity checks, links and UTF-16 size.
  Record refusal findings locally without creating an uncertain-send receipt.

The existing editor, revisions and verifier remain responsible for semantic
decisions. No model, dependency, collector, task, power setting, publication
window or Telegram format changes are included. Source URLs remain private
provenance; only the public presentation is link-free.

## Verification protocol

Run `python -m unittest discover -s tests -v` with temporary stores and mocked
publication. Synthetic regressions exercise distinct integrations, repeat
announcements, versions, source dates, benchmark identity, percentage comparison
targets, licence conditions and final-payload mutation before reservation.

For editorial evaluation, preserve immutable source snapshots privately. Run
baseline and candidate on identical inputs with the real configured model,
isolated databases and mocked Telegram. Compare the complete final payload,
including omissions and refusals; retain call, token and elapsed-time records.

Reserve control inputs before tuning, freeze the candidate before revealing
them, and annotate source facts independently of the evaluated model's outputs.
Do not tune on revealed control outcomes and report the same set as independent.
If a required category is absent, disclose the coverage gap. Real source text,
database snapshots, intermediate model replies and machine-specific replay
utilities are excluded from the public repository.

## Acceptance and limitations

The deterministic identity is a conservative heuristic, not a complete semantic
event graph. Unknown subjects retain the existing fallback. Clause-level numeric
checks cannot prove arbitrary causal relationships or resolve every ambiguity.
The final gate reuses these checks; it is not an independent factual oracle.

Deployment requires no observed critical factual errors, duplicates, false
merges or truncated text in independent final digests; at least baseline's
correct unique-event coverage; no unjustified additional false refusals; and
runtime compatible with the evening schedule. An incomplete control set or
remaining critical errors means a Draft PR, without production deployment.

Production keeps its existing daily schedule. Laptop wake remains disabled;
a sleeping or offline host cannot guarantee delivery at 21:00 Moscow time.
