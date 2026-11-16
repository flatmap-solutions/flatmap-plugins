---
name: workflow
description: Show where the work stands and continue the workflow from the current step. Optional - session start does this automatically.
---

# /workflow

1. Run `python3 .claude/hooks/harness.py status`.
2. Tell the user the status in one or two sentences.
3. Do the "next" action it gives. Follow `harness/WORKFLOW.md`.
4. At an approval step, stop and wait for the user's answer.
