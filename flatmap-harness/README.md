# flatmap-harness (Claude Code plugin)

## Install

```
/plugin install flatmap-harness --marketplace flatmap-solutions/flatmap-plugins
```

## Skills

| Skill | What it does | Status |
|---|---|---|
| [`/flatmap-harness:flatmap-repo-forge`](#flatmap-harnessflatmap-repo-forge) | New GitHub repo with the full harness and agent workflow. | **v0.1** |
| `/flatmap-harness:harness-update <single\|multi>` | Re-apply the latest harness to a repo it created in the given mode: `single` keeps or switches to single-pass (removing only unchanged multi-phase files); `multi` keeps or upgrades to multi-phase. | planned (v0.3) |
| `/flatmap-harness:harness-add` | Add the harness to an existing repo: detect what's there, merge instead of overwrite. | planned (v0.3) |

Short forms (`/flatmap-repo-forge`, …) work when no other installed plugin uses the same name.

Repos the forge creates also get two project commands: `/ship` (branch, checks, commit, push, PR) and `/workflow` (where things stand, and continue).

## `/flatmap-harness:flatmap-repo-forge`

One command that:

1. **Interviews you** about the project, one question at a time.
2. **Sets up the repo:** shows the plan and waits for your yes, scaffolds it locally, checks it runs green (lint, typecheck, test, build), then creates the GitHub repo, pushes and applies settings.
3. **Configures the agent workflow:** planner, tester, builder and reviewer agents, plus hooks that enforce a test-first loop with approval steps.

Then you start a new Claude Code session in the project folder, and the workflow picks up from there.

`/flatmap-harness:flatmap-repo-forge --dry-run` scaffolds into a temp folder and makes no GitHub changes.

### What v0.1 supports

| | Supported | Planned |
|---|---|---|
| Stacks | TypeScript (npm), Python (uv) | Go, generic (v0.2) |
| Audiences | solo, public | team, client (v0.2) |
| Build modes | multi-phase, single-pass | |
| UI layer | — | v0.2 |
| Existing repos | — | `/flatmap-harness:harness-add` (v0.3) |

### Prerequisites

`git`, `gh` (signed in with the `repo` and `workflow` scopes), `python3`, `make`, `gitleaks`, `lefthook`, plus the stack's tools (`node`/`npm` or `uv`). The forge checks all of these first and helps you fix anything missing.

### What a generated repo gets

- `AGENTS.md` (rules for any agent) and `CLAUDE.md` (imports it, adds Claude Code specifics)
- `GOALS.md`, `harness/WORKFLOW.md`, `harness/build-log.md`; multi-phase also gets `PLANS.md` and `harness/phases/`
- CI (lint, typecheck, test, build, gitleaks), Dependabot, PR and issue templates, an ADR
- Secrets protection: `.gitignore` patterns, `.env.example`, gitleaks before every commit and in CI, a Claude read-deny list, a first-commit check, GitHub push protection where the plan allows it
- `.harness/state.json` workflow state, enforced by `.claude/hooks/harness.py`
- Optional: a high-level entry in your company brain (never code)

Full design: [SPEC.md](SPEC.md).

## Develop

```bash
python3 evals/test_forge.py
FORGE_FULL=1 python3 evals/test_forge.py
claude plugin validate .
```
