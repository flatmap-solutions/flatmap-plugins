# Runbook: {{PROJECT_NAME}}

How to set up, run and look after {{PROJECT_NAME}}. Each step says what to do in plain words, then the exact command.

## Set it up

1. Get a copy of the code.
   `git clone {{REPO_URL}}`
2. Install what it needs.
   `make install`
3. Copy the example settings file and fill in your own values. Never share this file.
   `cp .env.example .env`

## Check it works

Run every check the project uses (style, types, tests, build). All of them should pass.
`make check`

## Run it

(Doc fills this in once there's something to run.)

## Check it's healthy

(Doc fills this in as features land.)

## Common problems

| What you see | What it means | What to do |
|---|---|---|
| `make check` fails | A check found a problem | Read the first error; ask a developer if it isn't clear |

## Where things live

| Thing | Where |
|---|---|
| Settings and secrets | `.env` (your copy, never committed); names listed in `.env.example` |
| How the work is organised | `AGENTS.md`, `harness/WORKFLOW.md` |

## Who to ask

The repository owner: {{OWNER}}.
