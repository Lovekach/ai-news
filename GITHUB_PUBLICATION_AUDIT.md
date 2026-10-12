# GitHub publication audit

Audit date: 2026-10-12. Project: **AI News**.

## Release status

Repository: https://github.com/Lovekach/ai-news

**PUBLIC.** The repository was created private, without a generated README, license or initial remote commit. The exact release tree and remote history passed review before public visibility was enabled. Anonymous API access confirmed the public repository and its complete file tree.

## Repository discovery

The local checkout initially had no remote, ordinary branches, tags or commits. GitHub API discovery examined all 37 repositories available through the existing Git credential; no AI News repository was found. The owner then explicitly authorized creation of `Lovekach/ai-news`.

Three local Codex tree references were present. All 281 local Git objects, including 193 blobs, were inspected. These internal snapshots contain old local configuration and personal paths; they are **not release history** and must never be uploaded with `push --mirror` or `push --all`. Publication pushes only the reviewed release branch. No internal refs are deleted or rewritten.

## Security checks

- Gitleaks 8.30.1 was downloaded from its official release and checked against the release SHA256 manifest.
- Gitleaks scanned a private working-directory snapshot, all exported local Git blobs/commit/tag objects, and ordinary Git history with `--all`: **zero findings**. There were no ordinary commits before preparation.
- Additional byte-pattern checks inspected 653 working files, including live configuration, staging material, raw SQLite data, archives, logs and documentation. They found credential-shaped strings in private news/staging data and personal paths in operational material. Those files stay local and are excluded from the release; no credential values appear in this report.
- Additional Git-object checks found personal paths in old internal snapshots, but no recognized credential patterns. Only newly reviewed source files are staged, without inheriting these snapshot trees as commit parents.
- Staged and downloaded remote content passed additional credential patterns, contextual entropy, private-path/address and forbidden-file checks. Exact comparison with the actual DPAPI-loaded bot token and common encodings returned **zero matches**, including in the private working snapshot. The token stayed in memory and was never printed or written to audit output.
- Live settings and encrypted secret files match the pre-edit snapshot. No secrets were rotated, changed or removed. No previously public AI News history was identified; accessible history of the new repository is checked after push.

Scanning cannot prove the absence of every unknown secret format. New confirmed credential exposure would require owner rotation and a separate safe history-remediation plan; adding an ignore rule is insufficient.

## Files excluded from publication

The ignore rules exclude live `config.json` / `watchlist.json`, `.env*`, `.secrets/`, `.state/`, `output/`, SQLite databases, logs, sessions, credential files, backups, caches, environments and model artifacts. Local operational/content reports are excluded because they contain publication history, private source text or personal paths. Existing files remain on disk.

The initial release includes **38 explicitly selected files**. Its index and downloaded remote tree agree; live data is absent. No automatic blanket staging of local changes was used. The follow-up below adds three public files.

### Published file manifest

```text
.gitattributes
.github/workflows/tests.yml
.gitignore
ARCHITECTURE.md
GITHUB_PUBLICATION_AUDIT.md
README.md
SETUP_TELEGRAM.md
ainews/__init__.py
ainews/__main__.py
ainews/daily.py
ainews/digest.py
ainews/feeds.py
ainews/lock.py
ainews/model_session.py
ainews/pipeline.py
ainews/quality.py
ainews/security.py
ainews/store.py
ainews/telegram.py
ainews/telegram_public.py
ainews/x_rss.py
config.example.json
scripts/apply_content_corrections.py
scripts/install_schedule.ps1
scripts/install_telegram_schedule.ps1
scripts/install_x_schedule.ps1
scripts/python_runtime.ps1
scripts/read_token.ps1
scripts/run_hidden.pyw
scripts/run_once.ps1
scripts/store_token.ps1
tests/test_audit_regressions.py
tests/test_core.py
tests/test_daily.py
tests/test_production_readiness.py
tests/test_security.py
tests/test_x_rss.py
watchlist.example.json
```

The private remote initially contained exactly one reviewed root commit, `main`, and no tags or other refs. Its complete Git object export and `--all` history scan returned zero Gitleaks/custom findings. Internal local Codex refs were not transported. Subsequent normal commits retain this clean release ancestry; there is no force push or history rewrite.

## Application review and changes

- Replaced stale operational README/architecture notes with setup, supported behavior, data flow, limitations and failure recovery.
- Added safe config/watchlist examples with publication disabled and no channel ID or token.
- Added credential redaction in diagnostics, Telegram API errors and task logs. Unexpected transport failures suppress sensitive request URLs; HTTP error resources are closed.
- Feed/article redirects now check HTTPS and allowed hosts before contacting the destination, rather than only checking after downloading it. Source URLs containing username/password are rejected.
- Bot identity checks can use each installation's configured username; the current production default is retained.
- Installer scripts resolve the caller's Python instead of relying on a developer's installation path. Existing tasks were not reinstalled or altered. Legacy source-task installers refuse to overwrite another checkout's task.
- Removed the other project's identity from the AI X collector's HTTP User-Agent. No other project's files, configuration or processes were changed.
- External news is parsed and passed as prompt data; no model-produced code, shell commands, pickle payloads or source scripts are executed. Command subprocesses use fixed argument lists without `shell=True`.
- SQL values use parameter binding; the dynamic daily query only constructs placeholders, not interpolated source data.

## Dependencies and CI

Runtime Python imports use the standard library and internal modules; there are no third-party Python runtime distributions to audit or install. Python, Windows and Ollama still require normal security updates; this audit is not a claim that their entire installations have no CVEs.

The workflow uses hosted Windows test runners and a hosted Linux Gitleaks job, `contents: read`, actions pinned to verified full commit SHAs and `persist-credentials: false`. The scanner binary is pinned by version and SHA256. It has no production/posting secrets, deployment step, `pull_request_target` or self-hosted runner. Untrusted pull requests cannot obtain production credentials from this workflow.

Action security guidance: https://docs.github.com/en/actions/reference/security/secure-use

Scanner release: https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1

## Tests and production preservation

The initial release passed **109 unit/regression tests** in the installed production Python 3.14, the independent test runtime and an export containing only release files. A final Telegram request-path redaction regression brought that release's suite to **110 passing tests**. All seven PowerShell scripts parse successfully; Python path resolution was checked without running an installer. Tests use temporary databases and mocked sending: **no real Telegram test publication**.

GitHub Actions for the first privately pushed release passed before visibility changed: Windows Python 3.11 / 3.14 tests and the Linux whole-history Gitleaks job. Evidence: https://github.com/Lovekach/ai-news/actions/runs/38232517426

Existing AI News tasks remain enabled with the correct project root. Collection runs every minute, Telegram scanning every five minutes, editing at 18:00 / 20:15 / 20:50 MSK, and the daily publisher at **21:00 MSK**. Live configuration, watchlist and encrypted-token files match the pre-edit snapshot; channel posting permission was confirmed through read-only Bot API calls. The SQLite ledger is retained. Production processes were not stopped for GitHub work. This confirms readiness and the unchanged schedule, not delivery of a future evening edition.

Daytime collection does not start the LLM; evening processing owns a finite localhost model session. The publisher does not start Ollama. No production model was launched merely for this audit.

## Remaining limitations

- Windows-only runtime; the laptop must be awake and the configured user logged in at publication time.
- Public X mirrors can fail or omit posts; Telegram public pages expose only a recent window.
- LLM/rule verification can miss factual errors, and grouping can misidentify events.
- Only Telegram publishing is implemented. The full local archive is larger than the Telegram message and remains private.
- An ambiguous Telegram response needs manual delivery verification; a second fresh installation must not reuse the channel without migrating the ledger.
- DPAPI does not protect against code already running as the same Windows user.
- Use trusted public source hosts. Host allowlists are not a full network/DNS sandbox.
- The owner approved MIT for the code in the follow-up review; third-party content and model rights remain separate.

No unrelated project was modified during this publication task.

## Repository hardening follow-up — 2026-10-12

The owner explicitly approved security settings and MIT attribution to Lovekach. The follow-up branch is `codex/github-hardening`; it adds `LICENSE`, `SECURITY.md` and `docs/DEMO_DIGEST.md`, bringing the public tree to **41 files**. The example digest is explicitly fictional and uses no production material.

Description and topics now identify the project as a local AI news collector with a daily Telegram edition. README includes the CI badge, example digest, supported behavior, limitations and a clearly unimplemented roadmap. No new runtime dependencies, workflows or production configuration are introduced.

Repository API readback confirms Secret Scanning, Push Protection, Dependabot alerts and private vulnerability reporting enabled. Open secret-scanning and Dependabot alert counts are both zero at review time. Dependabot automatic security-update PRs are a separate feature and are not enabled by this task. Actions default permissions are read-only and Actions cannot approve pull requests; existing workflow permissions remain `contents: read`.

The `main` branch requires a pull request, resolution of conversations, an up-to-date branch and all three existing checks: `unittest (3.11)`, `unittest (3.14)` and `secrets`, tied to the GitHub Actions app. Protection applies to administrators. Force pushes and deletion are disabled. No second reviewer is required, allowing the owner to merge a successful PR independently. API readback confirms these settings; no competing rulesets exist.

X mirror redirects previously used the default HTTP opener, checking HTTPS only after arrival. They now use the existing source redirect handler before each connection, while retaining the eight-second timeout and rotating public mirror destinations. The shared guard also rejects authenticated URLs, local hostnames and non-public IP literals. This is not a full DNS sandbox; configure trusted services. Feed/Telegram host allowlists remain in place.

The new redirect regression brings the full offline suite to **111 passing tests** on production Python 3.14, including a clean export containing only the 41 public files. Tests do not send Telegram messages or launch the LLM. The production task definitions were read, not changed: the daily task still points to this AI News checkout at **21:00 MSK**; source collectors remain enabled. PremWire was not modified.

Before pushing the follow-up, Gitleaks found no secrets in the staged public export or all existing remote history. Additional checks of staged files and all remote blob/commit objects found no forbidden files, credential patterns, contextual-entropy findings or personal paths. Exact comparison with the live DPAPI-loaded bot token and common encodings returned zero matches. Only the ten named source/test/documentation files are changed; live settings, private data and internal Codex references remain excluded. The same remote checks must pass again after PR publication and merge.
