# flatmap-harness (Claude Code plugin)

## What it does

*Written for founders, project managers and clients, not just engineers.*

### The problem

Most software projects start fast and add good habits later: tests, reviews, automatic checks, protection for passwords and keys. "Later" often never comes. Then the project gets harder to change and riskier to run.

flatmap-harness builds those habits in on day one. Think of it as the scaffolding and site rules that go up before construction starts. The AI does the building, but it works inside rules it can't skip.

### What happens when you run it

You type one command in Claude Code: `/flatmap-harness:flatmap-repo-forge`. Then:

1. **A short interview.** Claude asks one question at a time: the project's name and purpose, how you'll know it worked, who it's for, where the code should live. Where a choice is technical (like which programming language), it recommends one and says why. You accept or pick another.
2. **A plan for your OK.** Before it creates anything, it shows the whole plan: the repo's web address, the files, every change it will make on GitHub, and any warnings. You answer yes, no, or "change 3" to redo one answer. Nothing happens until you say yes.
3. **A test run on your computer.** It builds the project locally and checks that everything works before anything goes online.
4. **Setup on GitHub.** It creates the repository (repo: the project's home on GitHub, holding the code and its full history) and turns on:
   - **Automatic checks (CI).** CI means checks that run on every change: the code is tidy, the tests pass, the project builds. A change that fails is flagged before it's accepted.
   - **Leak protection.** Several layers stop passwords, API keys and other secrets from being saved into the project by mistake. They're checked before each save, checked again online, and hidden from the AI itself. If one layer misses, the next one catches it.
   - **Main-branch protection.** "Main" is the official version of the project. Changes go in as proposals (pull requests) that pass the checks first, never straight into main.
5. **An AI team.** The project gets four AI helpers, each with one job:
   - **Planner:** breaks the work into steps.
   - **Tester:** writes the tests *before* any code exists, so "done" is defined up front.
   - **Builder:** writes the code until those tests pass.
   - **Reviewer:** checks the work against the plan. It reads but never edits.

   A `/ship` command packages finished work into a proposal for you to review.
6. **The handoff.** It ends with a report of what worked (✓) and what didn't (✗), and tells you to open a new Claude Code session in the project folder. That session tells you where things stand and what's next. Every later session picks up the same way, so you never have to remember where you left off.

Optionally, it can also keep a short entry about the project in your company knowledge base: purpose, contributors, version, milestones. Never the code itself.

### Two build modes: which to pick

| Pick | When | How it runs |
|---|---|---|
| **Multi-phase** (default) | A bigger build you'd want to review in chunks. | Work is split into phases. You approve each phase before it starts, and Claude waits for your go before the next one. |
| **Single-pass** | A smaller project, done in one or two sittings. | You describe a task; the team tests it, builds it and proposes it. |

Rule of thumb: if you'd want to stop partway and look before going on, pick multi-phase.

### Safety rails

These are enforced by the setup itself, not just written as instructions the AI is asked to follow.

**It always asks you before:**
- creating anything on GitHub (you approve the plan first)
- the test plan, and again for the written tests, before any code is built
- starting each new phase (multi-phase)
- merging a change into the official version, or deploying it

**It never:**
- pushes changes straight to main
- marks its own work as done: done means your approved tests pass, the reviewer passes and the automatic checks are green
- keeps retrying forever: after a set number of failed attempts (you choose, 3 by default), it stops and asks you
- handles your sign-ins or passwords; you run those yourself
- deletes a GitHub repo

**It can do without asking:** work on a side copy of the project (a branch) and open a proposal (pull request) for you to review.

### Coming next

- `/flatmap-harness:harness-update <single|multi>`: brings a project up to the latest version of the harness. `multi` keeps or switches it to multi-phase; `single` keeps or switches it to single-pass. It shows what it will change and waits for your yes.
- `/flatmap-harness:harness-add`: adds the harness to a project that already exists, merging with what's there instead of overwriting it.

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
