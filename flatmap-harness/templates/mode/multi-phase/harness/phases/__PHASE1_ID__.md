# Phase 01: {{PHASE1_NAME}}

- Status: drafted, awaiting approval
- Depends on: none

## Objective

{{PHASE1_OBJECTIVE}}

## In scope

{{PHASE1_IN_SCOPE}}

## Non-goals

{{PHASE1_OUT_OF_SCOPE}}

## Files affected

{{PHASE1_FILES}}

## Decisions needing human input

- (none yet)

## Test plan

(written by the tester, approved before the build)

## Red → green → refactor

1. Red: the approved tests fail.
2. Green: the smallest change that makes them pass.
3. Refactor: clean up with the tests still green.

## Verification commands

```
make lint
make typecheck
make test
make build
```

## Acceptance criteria

{{PHASE1_ACCEPTANCE}}

## Stop condition

Stop after the tests pass, the evidence is in the build log and the reviewer passes. Then /ship.
