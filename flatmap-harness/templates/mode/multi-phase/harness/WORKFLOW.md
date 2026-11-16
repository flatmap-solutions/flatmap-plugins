# Workflow (multi-phase)

Work happens one phase at a time. Each arrow is a step in `.harness/state.json`.
Steps marked **(you)** wait for a human answer.

```
awaiting_phase_approval (you)     planner drafted the phase; approve or ask for changes
  → writing_test_plan              tester writes and explains the test plan
  → awaiting_test_plan_approval (you)
  → writing_tests                  tester writes the failing tests
  → awaiting_test_approval (you)   approve, then the tests are committed
  → building                       builder writes the code
  → testing                        tester runs the checks, records evidence
  → reviewing                      reviewer checks the change
  → ready_to_ship (you)            run /ship: branch, PR, CI
  → awaiting_merge (you)           CI green, then approve the merge
  → merged                         Doc updates the docs; Claude names the next phase and waits for you
```

- A failed test, review or CI run goes back to `building`. That's one failed run.
- After {{RETRY_LIMIT}} failed runs, the workflow stops (`stopped_retry_limit`) and asks you what to do.
- The next phase starts only when you say so.
- To change the retry limit, edit `retry_limit` in `.harness/config.json`.

## Docs

When a pull request is merged, Doc (the writer) gets the green light to update the docs. This runs alongside the workflow and never changes its step.

- Doc updates `docs/guide/` (overview, one page per feature, runbook, changelog) and, if it's on, `wiki/`.
- Every feature is explained twice: in plain words, and in technical detail.
- Doc's changes go on their own `docs/...` branch and pull request. You approve the merge, as always. Docs pull requests don't trigger more docs.
- To start the wiki later, ask for it (`/docs wiki on`). Anything the docs need built (e.g. a docs website) becomes a task for the builder.
