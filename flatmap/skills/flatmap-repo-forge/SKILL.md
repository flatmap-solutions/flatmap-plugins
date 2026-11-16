---
name: flatmap-repo-forge
description: Create a new GitHub repo with a full engineering harness - interview the user, scaffold CI, quality tooling, secrets protection and a test-first agent workflow, verify it runs green, create and configure the repo, then hand off to a new session. Use when the user runs /flatmap-repo-forge or /flatmap:flatmap-repo-forge, or asks to "start a new project/repo with the harness". Pass --dry-run to scaffold into a temp folder with no GitHub writes.
argument-hint: "[repo-name] [--dry-run]"
---

# flatmap-repo-forge

You set up a new project in three parts: **a.** interview, **b.** set up the repo, **c.** configure the agent workflow. Then you tell the user to start a new session in the project folder.

The engine is `${CLAUDE_SKILL_DIR}/scripts/forge.py`. Call it as:

```
python3 "${CLAUDE_SKILL_DIR}/scripts/forge.py" <subcommand> ...
```

Every subcommand prints JSON. Read the `ok` field. Never guess a result; run the command.

Arguments given: `$ARGUMENTS`. A bare word is the repo slug (still confirm it at question 4a). `--dry-run` means: do steps 1-5 of part b into a temp folder, skip every GitHub write, skip the brain entry, and report.

Work folder for this run: make a temp folder with `mktemp -d` and keep `answers.json` there. Plugin data folder for run history: `${CLAUDE_PLUGIN_DATA}` (pass it as `--data-dir`; the script falls back to `~/.flatmap` if it's empty).

## Rules

- Ask one question at a time. Use the wording and defaults in `interview.md`.
- Recommend; don't make the user pick from long lists.
- Never create, push or change anything on GitHub before the user says **yes** to the plan.
- Never type or handle the user's credentials. Sign-ins are the user's to run.
- Write only inside the new project folder, plus the brain entry (if the user opted in) and the run history.
- If a step fails, stop that part, explain it in one line, offer the fix, and resume once it passes. Never make the user rerun the command.
- Never delete a GitHub repo.

## Part a: preflight and interview

1. **Preflight tools.** Run `forge.py preflight-tools`. For each item in `failed`:
   - `kind: install` → say what's missing and offer to run the `fix` command. Run it only on the user's yes.
   - `kind: signin` → give the user the command to run themselves, prefixed with `!` (e.g. `! gh auth login`, `! gh auth refresh -h github.com -s workflow`). Wait.
   - `kind: user` → give the user the command to run with their own value.
   - Then rerun `preflight-tools`. Repeat until `ok` is true. Then continue; don't restart.
2. **Run history.** Run `forge.py history-get --data-dir "${CLAUDE_PLUGIN_DATA}"`. If `shorter_interview` is true, the `skippable` answers are this user's habits: don't ask those questions; confirm them together once (see `interview.md`).
3. **Interview.** Follow `interview.md` from the top. Build `answers.json` as you go (schema at the end of `interview.md`).
   - At 4a run `forge.py slug "<project name>"`, then `forge.py preflight-name OWNER/SLUG --visibility <vis>`. If it's taken, ask for another name now. Keep the JSON: it says whether branch protection and secret scanning are available.
   - After choosing the stack (Q7), rerun `forge.py preflight-tools --stack <stack>` and repair anything missing.
   - At Q9 run `forge.py preflight-path <path>`. If it's not ok, ask for another path now.
4. **Validate.** Run `forge.py validate answers.json`. Fix any error by re-asking only that question.

## Part b: plan, scaffold, create

5. **Plan preview.** Run `forge.py plan answers.json --owner-info '<preflight-name JSON>'`. Show the user, in this order:
   - Repo URL, display name, local path.
   - The numbered list of answers (numbers from `interview.md`), including any confirmed habits.
   - The file tree.
   - Every GitHub call.
   - Warnings (branch protection, secret scanning).
   Then ask: **"yes to create it, no to stop, or change N to change an answer."**
   - **no** → stop. Nothing was changed.
   - **change N** → re-ask only question N, rerun the checks it affects (a new owner or name → `preflight-name`; a new stack → re-recommend and `preflight-tools --stack`; a new path → `preflight-path`), then show the plan again.
   - **yes** → continue.
6. **Render.** `forge.py render answers.json`. (Dry run: add `--out <temp folder>/<slug>`.)
7. **Verify locally.** `forge.py verify <local path>`. This installs dependencies and runs lint, typecheck, test and build. If it fails, stop: show the failing step and output, fix the cause if it's in the scaffold, and rerun. Nothing touches GitHub until this passes.
   - **Dry run ends here.** Run `forge.py check-workflow <path>` and report (part c, step 12), with the last line "Dry run: nothing was created on GitHub."
8. **Git.** `forge.py git-init <local path>`. This installs the git hooks, runs the first-commit secrets check and makes the initial commit. If the secrets check finds anything, show it and stop.
9. **Create.** `forge.py create answers.json <local path>`. It re-checks the name first. If the name was taken meanwhile, ask for a new one (change 4a), then rerun `create`.
10. **Configure.** `forge.py github-setup answers.json`. If a step fails, the repo stays. Note the failure and its manual fix for the report. Don't roll back.

## Part c: agent workflow

11. **Check the workflow.** `forge.py check-workflow <local path>`. It checks the agents, hooks, skills, the session-start status and the push-to-main block. Report any failure with its detail.
12. **Company brain.** If the user opted in: `forge.py brain <local path>`. Report where the entry was written.
13. **Record the run.** `forge.py history-record answers.json --data-dir "${CLAUDE_PLUGIN_DATA}"`.

## Report

End with this, in this order:

- Repo URL and local path.
- A checklist of every step with ✓ or ✗ (and "not applied (plan limit)" where that applies).
- Things the user must do, if any (e.g. add deploy secrets, finish a failed step by hand).
- Multi-phase only: "Phase 01 is drafted and will be shown for your approval first."
- "When the new session asks whether to trust the folder, accept it. The harness hooks and permissions load only in a trusted folder. Then say anything (e.g. \"go\") and Claude reports where things stand."
- **Last line, exactly:** `Start a new Claude Code session in <local path>.`
