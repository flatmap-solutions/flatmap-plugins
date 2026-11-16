---
name: docs
description: Run Doc, the writer - update the documentation, runbook and wiki after a pull request is merged, or when the user asks. Use when the harness says docs have the green light, when the user runs /docs, or when the user asks to turn the wiki on or refresh the docs.
argument-hint: "[wiki on | refresh | <what to document>]"
---

# /docs

Doc runs only with a green light: a merged pull request that isn't documented yet, or a job the user asked for.
Docs never interrupt the build. Run them only when no working step is in progress.

Arguments: `$ARGUMENTS`.

## 0. Requests from the user

- `wiki on` → `python3 .claude/hooks/harness.py docs wiki on`. This queues the `wiki-setup` job.
- `refresh` → `python3 .claude/hooks/harness.py docs request full-refresh`.
- Anything else the user asked Doc to write → `python3 .claude/hooks/harness.py docs request "<what, in a few words>"`.

Only queue a job the user asked for. Never queue one on your own.

## 1. Check the green light

Run `python3 .claude/hooks/harness.py docs check`.

- `pending_prs` and `jobs` are both empty → tell the user the docs are up to date and stop.
- `busy` is true → a working step is in progress. Tell the user the docs will run when the step finishes and stop.

## 2. Make the docs worktree

Docs go on their own branch, in a separate worktree, so the workflow state in this checkout doesn't change.

```
git fetch origin main
git worktree remove --force .harness/worktrees/docs 2>/dev/null
git worktree add -B <branch> .harness/worktrees/docs origin/main
```

`<branch>` is the `branch` field from `docs check` (e.g. `docs/pr-12-13` or `docs/wiki-setup`).

## 3. Run Doc

Use the `doc` agent. Brief it with:

- The worktree path: `.harness/worktrees/docs` (absolute path).
- The pull requests (number and title) and jobs from `docs check`.
- Whether the wiki is on (`wiki` from `docs check`), or that this job turns it on (`wiki-setup`).

## 4. Record and open the pull request

1. Record what was covered (this writes `.harness/docs.json` in the worktree):
   `python3 .claude/hooks/harness.py docs done --root .harness/worktrees/docs --prs <n,n> [--job <job>]`
2. In the worktree: `git -C .harness/worktrees/docs add -A` and commit with `Docs: <short summary>`.
3. Push the branch: `git -C .harness/worktrees/docs push -u origin <branch>`.
4. Open the pull request from the worktree: `gh pr create --head <branch> --title "Docs: <summary>" --body "<body>"`.
   The body lists the pull requests documented (`Documents #12, #13`), the files changed, and Doc's `Needs Builder` and `Open questions`.
5. Remove the worktree: `git worktree remove .harness/worktrees/docs`.

## 5. Report

Tell the user, in plain words:

- What Doc documented, and the docs pull request link. It merges like any other pull request (you approve it).
- Doc's wiki note. If it says `recommend now`, ask: "Doc thinks a wiki would help now: <why>. Turn it on?" On yes: `/docs wiki on`.
- Each `Needs Builder` brief. Offer it as the next task (single-pass) or a phase for `PLANS.md` (multi-phase). Don't start it until the user says so.
- Doc's open questions, if any.

Docs pull requests (branches starting `docs/`) never trigger more docs.
