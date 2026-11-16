@AGENTS.md

# Claude Code specifics

Everything above comes from `AGENTS.md` (shared with other agents). This part is for Claude Code only.

## You are the orchestrator

The main session runs the workflow. Call each subagent in turn and move the workflow with the harness command:

```
python3 .claude/hooks/harness.py status
python3 .claude/hooks/harness.py advance <step> [--result pass|fail] [--note "..."]
```

- Never edit `.harness/state.json` directly. Hooks block it.
- Use the `planner`, `tester`, `builder` and `reviewer` agents only in their steps. Hooks block the wrong agent.
- Use the `doc` agent only through `/docs`, when it has the green light (a merged pull request or a docs request from the user). Hooks block it otherwise.
- At each approval step, stop and wait for the user's answer. Never approve on their behalf.
- Never run the builder and tester at the same time.

## Agents

| Agent | Does | Can't |
|---|---|---|
| `planner` | Drafts phase files and `PLANS.md` | Change source code |
| `tester` | Writes the test plan and tests before the build; runs checks and records evidence after | Change source code |
| `builder` | Writes source code to pass the approved tests | Change approved tests, mark work done |
| `reviewer` | Checks the change against the phase/task and `AGENTS.md` | Edit anything |
| `doc` | Doc, the writer: docs, runbook and wiki for non-technical readers, after each merge | Change code, tests or workflow files |

## Skills

- `/ship`: branch, checks, commit, push, open a pull request. Only when the step is `ready_to_ship`.
- `/workflow`: show where the work stands and continue. Optional; the session start does this anyway.
- `/docs`: run Doc on its own branch and open a docs pull request. Run it when the harness says Doc has the green light. `/docs wiki on` starts the wiki; `/docs refresh` rewrites the docs for the whole project.

## Hooks

- Session start: tells you the current step and the next action.
- Before Bash: blocks any push to `main`.
- Before an agent call or a write: enforces the workflow steps.
- After an edit: formats the file and flags out-of-scope or test-file edits.
- On stop: keeps you going if a working step isn't finished.
- After a merge (and at session start): looks for merged pull requests that aren't documented yet and gives Doc the green light.
