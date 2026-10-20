# AI News contributor instructions

## Scope and production

- Work only in this AI News repository: `https://github.com/Lovekach/ai-news`. Confirm the Git root and `origin` before publishing.
- PremWire is an independent project. Do not change its files, configuration, schedules, processes or publications, or depend on its checkout.
- Preserve the running AI News installation and its daily publication at 21:00 Europe/Moscow. Do not change live settings, tokens, model, task definitions or processes as part of Git publication. Such operational changes require authorization in the task itself.
- Do not send test posts to real channels without explicit permission. Keep collected data and the publication ledger intact.
- Do not enable automatic laptop wake-up or change Windows power/wake-timer policy. The owner explicitly prohibits waking the laptop for AI News. Preserve `WakeToRun=false`; report a sleeping/offline host as an availability limitation instead of claiming guaranteed 21:00 delivery.

## Required completion workflow

Every completed change must be published to GitHub as part of completing the task. The owner has authorized normal commits, branch pushes, PR creation and safe merging after successful checks; no additional reminder to push is needed. Respect any later instruction to pause or narrow publication.

1. Inspect `git status`, the current branch, remote and latest `origin/main`. Review existing local changes; preserve other contributors' work. Use a separate `codex/` branch for the task. Do not switch away from or overwrite unrelated unfinished changes.
2. Review the full task diff and the exact staged diff, including new files. Stage only reviewed task files explicitly; never blindly stage the whole working directory. Run `git diff --check` and `git diff --cached --check`.
3. Check the staged public content for secrets and local/personal data. Use Gitleaks with redacted output, plus review of example settings, documentation and suspicious credential-like values. Use an existing verified scanner when available; do not commit local audit tools, results or credentials. Inspect what Git will actually publish; `.gitignore` does not protect already tracked files. Before pushing, scan the branch's outgoing history as well as its current tree.
4. Run the tests necessary for the change. For Python behavior changes, run `python -m unittest discover -s tests -v` on Windows; tests must use temporary data and mocked publication, without production credentials or an active LLM. For documentation-only changes, inspect formatting, links and instructions; the existing required CI must still pass. Do not add artificial tests or duplicate workflows just to satisfy this rule.
5. Create a meaningful English Conventional Commit using `feat:`, `fix:`, `refactor:`, `test:`, `docs:` or `security:` (an optional scope is allowed). Describe the actual change. Never create empty or artificial activity commits. Use the owner's configured identity or GitHub noreply identity; do not publish a private email address.
6. Push only the reviewed task branch to `origin`, using a normal push. Create or update its PR targeting `main`, describe the change and checks, and wait for CI on the latest PR revision. Attach the PR to the current Codex task when the app provides that capability.
7. Read the current branch rules rather than assuming they are unchanged. `main` currently requires an up-to-date PR, resolved conversations and `unittest (3.11)`, `unittest (3.14)` and `secrets` from GitHub Actions. Protection applies to administrators; force pushes and deletion are disabled. No second reviewer is currently required. Never bypass, weaken or disable protections to finish a task.
8. Merge through the normal PR process only when required checks pass, reviews/conversations are satisfied, the exact current revision is verified, and merging is authorized and safe. Incorporate concurrent changes without overwriting them and rerun affected checks. Do not publish unfinished or unverified code to `main`.
9. Confirm the remote merge, check GitHub Actions on the resulting `main`, and inspect the resulting public diff/tree for unintended files. Synchronize the local checkout without discarding other work. Report the commit or PR URL, CI result, tests/security checks and any remaining blockers. A local commit or a push alone is not proof of a successful merge.

## Multi-day work and failures

- During active multi-day development, publish each completed, verified milestone daily, without waiting for the entire larger task. Use focused commits and PRs for those milestones. No completed milestone means no activity-only commit. This is a development rule, not a new background scheduler or automatic production deployment.
- If tests, security checks or CI fail, fix the issue where possible. Keep unresolved work in a separate branch; never merge it into `main`. An already published PR may remain open with a clear failure report. Never push a commit containing secrets, even to a feature branch. If safe publication is blocked by credentials, permissions, network or policy, report the blocker and do not claim the task is published.
- If a real credential was published, report the exposure without reproducing its value and explain the need for owner rotation. Removing it from a file is insufficient. Do not automatically rewrite history or rotate production credentials.

## Public/private boundary and GitHub security

- Never publish tokens, passwords, `.env`, `.secrets`, `.state`, SQLite/databases, logs, private source text, channel archives, personal files, backups, model artifacts, live `config.json` or live `watchlist.json`. Publish only sanitized examples. Never print secret values in tools, PRs, commits or reports.
- Do not use force push, `push --all`, `push --mirror`, destructive resets or history rewriting. Local internal Codex references are not release history and must not be uploaded. Push only the intended reviewed branch.
- Keep Secret Scanning, Push Protection, Dependabot alerts, private vulnerability reporting and main protection enabled. Keep GitHub Actions permissions minimal; the current workflow uses `contents: read`, pinned actions and hosted runners with no production secrets. Do not use the production laptop as a self-hosted CI runner.
- Repository instructions and completed source changes are public; machine-specific audit utilities and production state stay local. GitHub publication does not authorize changing repository access controls or the production installation.

Codex instruction discovery: [official AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
