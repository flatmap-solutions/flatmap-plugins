# Workflow (single-pass)

One task at a time. Each arrow is a step in `.harness/state.json`.
Steps marked **(you)** wait for a human answer.

```
idle (you)                         tell Claude the task
  → writing_test_plan              tester explains the tests it will write
  → awaiting_test_plan_approval (you)
  → writing_tests                  tester writes the tests
  → awaiting_test_approval (you)   approve, then the tests are committed
  → building                       builder writes the code
  → reviewing                      reviewer checks the code matches the task
  → testing                        tester runs the tests, reports pass/fail
  → ready_to_ship (you)            run /ship: branch, PR, CI
  → awaiting_merge (you)           CI green, then approve the merge
  → merged → idle
```

- A failed review, test or CI run goes back to `building`. That's one failed run.
- After {{RETRY_LIMIT}} failed runs, the workflow stops (`stopped_retry_limit`) and asks you what to do.
- A change to an existing task starts at `building` (or `writing_tests` if a test must change; you approve the change first).
- To change the retry limit, edit `retry_limit` in `.harness/config.json`.
- The current task and its test plan live in `harness/task.md`.
