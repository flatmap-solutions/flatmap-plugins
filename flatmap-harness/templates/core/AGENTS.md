# {{PROJECT_NAME}}: how to work in this repo

This file is the source of rules for any coding agent (Claude Code, Codex, Cursor, Copilot) and for people.
Read it before you change files.

## Purpose

{{PURPOSE}}

Goals, scope and non-goals: `GOALS.md`.

## Commands

Use these. Don't call the underlying tools directly.

| Task | Command |
|---|---|
| Install dependencies | `make install` |
| Lint (and format check) | `make lint` |
| Format | `make fmt` |
| Type check | `make typecheck` |
| Test | `make test` |
| Build | `make build` |
| Everything CI runs | `make check` |

Stack: {{STACK_LABEL}}.

## Workflow

This repo uses a test-first workflow with approval steps. The loop is in `harness/WORKFLOW.md`.

- Tests are written and approved before code.
- The person who writes code never marks it done. A separate tester runs the checks and records evidence.
- Each approval step waits for a human answer.
- The builder retries at most {{RETRY_LIMIT}} times, then stops and asks.
<!-- forge:multi-phase -->
- Work is split into phases. The order is in `PLANS.md`. Each phase has a file in `harness/phases/`.
- Work on one phase at a time. Keep to the phase's scope and its "Files affected" list.
<!-- /forge:multi-phase -->

## Files and what each one owns

| File | Owns |
|---|---|
| `AGENTS.md` | How to work in this repo (this file) |
| `GOALS.md` | What success means; scope and non-goals |
| `harness/WORKFLOW.md` | The work loop and approval steps |
| `harness/build-log.md` | What actually happened: commands run and results |
| `docs/decisions/` | Why we decided things (ADRs) |
| `.harness/state.json` | Where the workflow is now (machine-readable; change it only with the harness command) |
<!-- forge:multi-phase -->
| `PLANS.md` | Phase order |
| `harness/phases/NN-name.md` | One phase: scope, test plan, acceptance criteria |
<!-- /forge:multi-phase -->

## Conventions

- Write small changes. One concern per change.
- Write a test for each behavior change.
- Record facts only in `harness/build-log.md`. Never log planned work as done.
- Record a material decision as an ADR in `docs/decisions/`.

## Safety limits

- Never commit secrets. `.env` and key files are ignored; copy `.env.example` to `.env` for local values.
- Never push to `main`. Work on a branch and open a pull request.
- Ask before you merge, deploy or change anything outside this repo.
- Don't change approved tests without recording why and getting approval.

## Definition of done

A change is done only when all of these are true:

1. The approved tests pass.
2. The tester recorded the evidence (exact commands and results) in `harness/build-log.md`.
3. The reviewer passed the change.
4. CI is green.
5. A pull request is open.
