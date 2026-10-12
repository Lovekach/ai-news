# GitHub publication audit

Audit date: 2026-10-12. Project: **AI News**.

## Release status

Repository: https://github.com/Lovekach/ai-news

**PRIVATE — release checks in progress.** The repository was created private, with no generated README, license or initial remote commit. Public visibility is gated on review of the exact commit, remote history and tests.

## Repository discovery

The local checkout initially had no remote, ordinary branches, tags or commits. GitHub API discovery examined all 37 repositories available through the existing Git credential; no AI News repository was found. The owner then explicitly authorized creation of `Lovekach/ai-news`.

Three local Codex tree references were present. All 281 local Git objects, including 193 blobs, were inspected. These internal snapshots contain old local configuration and personal paths; they are **not release history** and must never be uploaded with `push --mirror` or `push --all`. Publication pushes only the reviewed release branch. No internal refs are deleted or rewritten.

## Security checks

- Gitleaks 8.30.1 was downloaded from its official release and checked against the release SHA256 manifest.
- Gitleaks scanned a private working-directory snapshot, all exported local Git blobs/commit/tag objects, and ordinary Git history with `--all`: **zero findings**. There were no ordinary commits before preparation.
- Additional byte-pattern checks inspected 653 working files, including live configuration, staging material, raw SQLite data, archives, logs and documentation. They found credential-shaped strings in private news/staging data and personal paths in operational material. Those files stay local and are excluded from the release; no credential values appear in this report.
- Additional Git-object checks found personal paths in old internal snapshots, but no recognized credential patterns. Only newly reviewed source files are staged, without inheriting these snapshot trees as commit parents.
- Exact comparison with the actual DPAPI-loaded bot token and common encodings is part of the staged/remote review. The token is kept in memory and never printed or written to audit output.
- Live settings and encrypted secret files match the pre-edit snapshot. No secrets were rotated, changed or removed. No previously public AI News history was identified; accessible history of the new repository is checked after push.

Scanning cannot prove the absence of every unknown secret format. New confirmed credential exposure would require owner rotation and a separate safe history-remediation plan; adding an ignore rule is insufficient.

## Files excluded from publication

The ignore rules exclude live `config.json` / `watchlist.json`, `.env*`, `.secrets/`, `.state/`, `output/`, SQLite databases, logs, sessions, credential files, backups, caches, environments and model artifacts. Local operational/content reports are excluded because they contain publication history, private source text or personal paths. Existing files remain on disk.

The release includes only reviewed application modules, tests, launch/setup scripts, documentation, sanitized example settings and a CI workflow. The final manifest is verified against the index and remote tree before public access.

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

**109 unit/regression tests passed** in the installed production Python 3.14 and the independent Python test runtime. All seven PowerShell scripts parse successfully; Python path resolution was checked without running an installer. Tests use temporary databases and mocked sending: **no real Telegram test publication**.

Existing AI News tasks remain enabled with the correct project root. Collection runs every minute, Telegram scanning every five minutes, editing at 18:00 / 20:15 / 20:50 MSK, and the daily publisher at **21:00 MSK**. The live configuration, channel settings, token and SQLite ledger are retained. Production processes were not stopped for GitHub work.

Daytime collection does not start the LLM; evening processing owns a finite localhost model session. The publisher does not start Ollama. No production model was launched merely for this audit.

## Remaining limitations

- Windows-only runtime; the laptop must be awake and the configured user logged in at publication time.
- Public X mirrors can fail or omit posts; Telegram public pages expose only a recent window.
- LLM/rule verification can miss factual errors, and grouping can misidentify events.
- Only Telegram publishing is implemented. The full local archive is larger than the Telegram message and remains private.
- An ambiguous Telegram response needs manual delivery verification; a second fresh installation must not reuse the channel without migrating the ledger.
- DPAPI does not protect against code already running as the same Windows user.
- Use trusted public source hosts. Host allowlists are not a full network/DNS sandbox.
- No license was added without owner approval.

No unrelated project was modified during this publication task.
