---
name: ship
description: Ship the current work - make a branch, run the checks, commit, push the branch and open a pull request. Use when the user runs /ship and the workflow step is ready_to_ship.
---

# /ship

Run these steps in order. Stop and tell the user if any step fails.

1. Run `python3 .claude/hooks/harness.py status`. If the step isn't `ready_to_ship`, stop and tell the user what's still needed.
2. Make a branch if you're on `main`:
   - Multi-phase: `phase/<phase id>`
   - Single-pass: `task/<short-task-name>`
3. Run `make check`. If it fails, stop: tell the user, then run `python3 .claude/hooks/harness.py advance building --result fail --note "make check failed: <what>"`.
4. Stage and commit the work with a clear message. Include `.harness/state.json` and `harness/build-log.md`.
5. Push the branch: `git push -u origin <branch>`.
6. Open the pull request: `gh pr create --title "<title>" --body "<body>"`. Build the body from `.github/pull_request_template.md`, with every section filled in (what changed, work item, evidence from the build log, checklist).
7. Record it: `python3 .claude/hooks/harness.py advance awaiting_merge --pr <number>`.
8. Tell the user the PR link. Then watch CI with `gh pr checks <number> --watch`.
   - CI fails: `python3 .claude/hooks/harness.py advance building --result fail --note "CI: <what failed>"` and continue the build loop.
   - CI passes: ask the user to approve the merge.
