# flatmap-repo-forge: Claude Code plugin spec

**Status:** draft v0.3 · 2026-11-16 · all open questions resolved

## 1. What it does

**Use case:**
1. User installs the plugin (§9).
2. User runs `/flatmap:flatmap-repo-forge`, or the short form `/flatmap-repo-forge` when no other plugin uses that name.
3. The one command does three things, in order:
   - **a. Interview** the user (§4).
   - **b. Set up the repo:** show the plan and wait for a yes, scaffold locally and verify it runs green, create the GitHub repo, push, apply repo settings (§8).
   - **c. Configure the default agent workflow:** install the agents, hooks and gates in the new repo and check they load (§6, §8 step 9).
4. It ends with a report: repo URL, local path, what ran ✓/✗. **Last line:** "Start a new Claude Code session in `<local path>`."
5. User starts that session. Git and the remote are set up; the repo's agents, hooks and permissions load. A SessionStart hook says where things stand (multi-phase: "Phase 01 is drafted and waiting for your approval"; single-pass: "What's the first task?") and the workflow runs from there. Every later session resumes the same way. No command needed; `/workflow` exists only as an optional "where are we?".

**Scope:** project level only. Everything the forge writes goes inside the new project folder. It never writes to `~/.claude` settings or any user-level settings. Only two things live outside the folder: the optional company-brain entry (§5.8) and the plugin's own run history (§4), kept in the plugin's data folder.

The harness has two halves:
- **Tooling:** CI, linting, tests, branch protection, repo settings.
- **Workflow:** goals, phases, test-first gates, role agents, an evidence log.

Stack-agnostic core. Stack, UI, audience and build-mode choices add layers on top.

## 2. Non-goals (v1)

- Writing application code beyond a hello-world that proves the harness works.
- Real deploy pipelines (placeholder only; see §5.6).
- Retrofitting existing repos (planned as `/harness-add`, v0.3).
- Deleting or rolling back a GitHub repo. Ever. Failures after creation are reported, not undone.

## 3. Plugin layout

```
plugins/flatmap/                    # in repo flatmap-solutions/flatmap-plugins; plugin name "flatmap" → /flatmap:<skill>
├── .claude-plugin/
│   └── plugin.json                 # name: "flatmap", version, description
├── skills/
│   ├── flatmap-repo-forge/         # → /flatmap:flatmap-repo-forge (short: /flatmap-repo-forge)
│   │   ├── SKILL.md                # interview → set up repo → configure workflow
│   │   ├── interview.md            # question bank + branching rules (tool-neutral)
│   │   └── scripts/
│   │       ├── preflight.sh        # `tools`: gh/git + auth scopes; `name`: repo free, plan tier
│   │       ├── render.sh           # copy layers, substitute {{TOKENS}}, record checksums
│   │       └── github-setup.sh     # protection/ruleset, labels, repo settings
│   ├── harness-update/             # v0.3
│   ├── harness-narrowizer/         # v0.3
│   └── harness-add/                # v0.3
├── templates/                      # tool-neutral except the claude/ layer
│   ├── core/                       # always applied
│   ├── claude/                     # CLAUDE.md, .claude/ (the only Claude-specific layer)
│   ├── mode/{single-pass,multi-phase}/
│   ├── stacks/{typescript,python,go,generic}/
│   ├── ui/                         # applied if frontend = yes
│   └── audience/{solo,team,client,public}/
└── evals/                          # claude plugin eval suites
```

**Split of work:** the skill owns judgment (interview, writing prose from answers, explaining the plan). Scripts own anything that must be deterministic (copying files, checksums, gh API calls). Templates are plain files with `{{TOKEN}}` placeholders, editable without touching logic.

**Naming:** the plugin is named `flatmap` so its commands read `/flatmap:<skill>`. The product name stays flatmap-repo-forge (the main skill). Later skills join the same plugin: `/flatmap:harness-update`, etc. A skill directory is enough to create the slash command; no separate `commands/` file.

**Translatable by design:** only `skills/*/SKILL.md`, hooks and `templates/claude/` are Claude Code-specific. Everything else stays tool-neutral so a future translate plugin (§13) only rewrites that known set.

## 4. Setup interview

One question at a time; skip anything already answered in the command args (e.g. `/flatmap-repo-forge acme-api`).

| # | Question | Drives |
|---|----------|--------|
| 1 | Project name as you'd say it (e.g. "Acme Client Dashboard") + one-line purpose | display name in README, `GOALS.md`, repo description; source for the repo slug |
| 1a | Success criteria and non-goals | `GOALS.md` |
| 2 | **Who is this for?** Just me / my team / a client / public open source | audience layer (§7), visibility default |
| 3 | **Multi-phase build or single-pass project?** (default multi-phase) | mode layer (§5.1) |
| 4 | GitHub owner: personal account or which org (list from `gh api user/orgs`) | `gh repo create OWNER/NAME` |
| 4a | **Confirm repo name:** "Repo will be `OWNER/slug` at github.com/OWNER/slug. OK, or change it?" | repo name; availability checked here |
| 5 | Visibility (default from Q2: public only for open source) | `--private` / `--public` |
| 6 | **Will this build have a frontend UI?** yes / no | UI layer (§5.5) |
| 6a | If yes: **recommended framework**, e.g. "I recommend Next.js because …. Accept, or pick another?" | UI template variant |
| 7 | **Recommended language/runtime**, e.g. "I recommend Python because …. Accept, or pick another?" | stack layer; "other" → generic with TODOs |
| 8 | Deploy target, if known (none / Vercel / Fly / Cloud Run / other) | placeholder deploy (§5.6) |
| 9 | Local path (default `~/Claude/Projects/<slug>`) | where to scaffold; where the user starts the next session |
| 10 | **Do you have a company brain (a knowledge-base folder)? Should it track this project at a high level?** (default yes) | §5.8 |
| 10a | If yes: path to the brain | where the project entry goes |
| 11 | **How many times should the builder retry before stopping to ask you?** (recommend 3; allow 1–5) | `retry_limit` (§6) |

**Repo slug rule:** lowercase, spaces and underscores → hyphens, drop characters other than `a-z`, `0-9`, `-`, `.`; collapse repeated hyphens; trim leading/trailing hyphens and dots. "Acme Client Dashboard" → `acme-client-dashboard`. If you pass a name in the command args (`/flatmap-repo-forge acme-api`), it's treated as the slug and still confirmed at 4a.

**Availability check at 4a:** `gh repo view OWNER/slug`. If it exists, say so and ask for another name right then; don't continue the interview with a taken name. If the local path already exists and isn't empty, ask at Q9 the same way.

**Shorter interview for repeat users:** applies only from the 3rd run onward (the skill has been run more than 2 times).
- The plugin keeps a small run history: run count plus the answers to the "habit" questions (owner, visibility per audience, deploy target, local folder parent, brain path, retry limit). Never project content.
- From run 3: a habit question is skipped if the user gave the same answer in every previous run. Skipped answers are shown together once: "Using your usual: owner `flatmap`, private, brain at `…`, retry limit 3. OK, or change one?"
- Project-specific questions (name, purpose, goals, non-goals, audience, build mode, UI, framework, language) are always asked.
- Skipped answers still appear, numbered, in the plan preview, so `change N` works.
- Storage: the plugin's own persistent data folder (`${CLAUDE_PLUGIN_DATA}`; confirm it exists in the current Claude Code during build, else a dotfile the plugin owns). This is the plugin's data, not user settings; see §1 scope.

**Recommendations (6a, 7):** don't ask the user to choose from a list. Recommend one option with a one-line reason drawn from earlier answers (purpose, audience, UI, deploy target). The user accepts with one word or names another. Framework and language must agree: a JS framework implies TypeScript, so Q7 is confirmed, not asked again.

Team/client follow-ups: CODEOWNERS handle(s), required reviewer count.

Multi-phase follow-up: "What's the first chunk you'd want to review before going further?" → drafts phase 01.

Answers, plugin version, build mode and a checksum of every generated file are saved to `.harness/config.json`, so later skills can diff, upgrade or downgrade safely.

## 5. The harness

### 5.1 Workflow files (core + mode)

Each file has one job:

| File | Owns | Single-pass | Multi-phase |
|---|---|---|---|
| `AGENTS.md` | How to work in the repo: commands, conventions, safety limits, definition of done | ✓ | ✓ |
| `GOALS.md` | What success means; scope and non-goals | ✓ | ✓ |
| `PLANS.md` | Phase order | – | ✓ |
| `harness/phases/NN-name.md` | One phase: scope, test plan, acceptance criteria | – | ✓ (01 drafted) |
| `harness/build-log.md` | What actually happened: commands run, results, open issues | ✓ | ✓ |
| `docs/decisions/` | Why: ADRs | ✓ | ✓ |

**Phase template:** objective · non-goals · inputs and files affected · dependencies and decisions needing human input · test plan (written by tester, approved before build) · red → green → refactor plan · exact verification commands · acceptance criteria · stop condition.

**Build-log rule:** record observed facts only. Never log planned work as done.

Multi-phase-only instructions in `AGENTS.md`/`CLAUDE.md` are wrapped in `<!-- forge:multi-phase -->` … `<!-- /forge:multi-phase -->` markers.

Agent instruction files are written in short, imperative sentences, one action each.

### 5.2 Claude Code setup (claude layer)
- `CLAUDE.md`: `@AGENTS.md` import plus Claude-specific parts only (subagents, hooks, `/ship`, browser checks).
- `.claude/agents/`: roster in §6.
- `.claude/settings.json`:
  - allow the stack's `lint`/`fmt`/`test`/`build` commands, `git push` to non-main branches, `gh pr create`
  - `ask` for `gh pr merge` and deploy commands
  - deny reading every secret pattern in §5.4a (not just `.env*`); `.env.example` stays readable
- `.claude/settings.local.json` (gitignored, only if brain tracking is on): adds the brain folder to `additionalDirectories` so the entry can be written. Personal path, never committed.
- `.claude/hooks/`:
  - SessionStart → read `.harness/state.json` (§6.1); tell Claude where things stand and what the next step is (e.g. "Phase 02: test plan awaiting approval"). This is what starts and resumes the workflow without a command.
  - PostToolUse on Edit/Write → run formatter on the touched file; flag edits to files outside the current phase's list, or to approved test files.
  - PreToolUse on Agent (subagent calls) and on writes to `.harness/state.json` → enforce the allowed steps and transitions (§6.1).
  - Stop → if `state.json` shows a working step (`writing_test_plan`, `writing_tests`, `building`, `testing`, `reviewing`) that isn't finished, block the stop and send Claude on to the next step. Hooks can prompt Claude to ask for an approval; they never give one.
  - PreToolUse on Bash → block any push to `main` (incl. force-push), whatever the permission rules say. Safety net for free private repos without branch protection.
- `.claude/skills/ship/`: branch → run checks → commit → push branch → open PR with template.
- `.claude/skills/workflow/`: optional manual "where are we, keep going" (`/workflow`); never required, since the SessionStart hook does this automatically. Reads `.harness/config.json` for the mode and runs the matching loop in §6: in multi-phase, picks up the next phase in `PLANS.md` (or the one in progress) and moves it through the gates; in single-pass, takes a task description and runs build → verify → review. Always stops at each human gate.

**Definition of done** (in `AGENTS.md`): approved test plan passes, tester evidence recorded in the build log, reviewer passes, CI green, PR opened. The builder never marks its own work done.

### 5.3 CI/CD (core + stack)
- `.github/workflows/ci.yml`: lint, typecheck, test, build on PR and push to main. Job steps come from the stack layer.
- `.github/dependabot.yml`: stack ecosystem + `github-actions`.
- Branch protection on `main`: require PR, require `ci` check, no force-push, no direct push. Reviewer count from audience layer. Skipped with a warning on free-plan private repos (§8).

### 5.4 Quality tooling (stack)
- Core: `.editorconfig`, `.gitignore` (stack-merged), `lefthook.yml` (language-neutral pre-commit runner).
- TypeScript: pnpm, Biome (lint + format), Vitest, `tsc --noEmit`.
- Python: uv, Ruff (lint + format), pytest, pyright.
- Go: gofmt, golangci-lint, `go test`.
- Generic: Makefile with `lint`/`test`/`fmt` targets stubbed and marked TODO.

All stacks expose the same four entry points (`lint`, `fmt`, `test`, `build`) so CI, hooks and `AGENTS.md` stay stack-neutral.

### 5.4a Secrets protection (core, every repo)

Layered so one miss doesn't leak a secret:

1. **`.gitignore` secret patterns** (core; stack layer appends its own like `node_modules/`, `.venv/`, build output):
   - `.env`, `.env.*`, with `!.env.example`
   - `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`
   - `*credentials*.json`, `service-account*.json`, `secrets.*`
   - `.claude/settings.local.json`, `.harness/config.local.json`
   - `.DS_Store`, `.idea/`, `.vscode/*` with `!.vscode/settings.json` and `!.vscode/extensions.json`
2. **`.env.example`:** committed; variable names with placeholder values only. README says: copy to `.env` and fill in.
3. **Pre-commit scan:** `gitleaks` in `lefthook.yml` blocks any commit containing a key or token, including ones pasted into source files.
4. **CI scan:** `gitleaks` job in `ci.yml` as a backstop for anyone who skips local hooks.
5. **GitHub secret scanning + push protection:** enabled in step 8 where the plan allows (free on public repos; private repos need a paid add-on). If unavailable: warn in the plan preview, skip, report "not applied (plan limit)".
6. **Claude Code deny list:** Claude can't read any file matching the patterns in item 1 (see §5.2).
7. **First-commit check:** before the initial commit (§8 step 6), confirm no staged file matches the patterns and gitleaks finds nothing. If something matches, stop and show it.

The same pattern list is the single source for items 1, 6 and 7, so they can't drift apart.

### 5.5 UI layer (only if Q6 = yes)
- Playwright e2e with one smoke test; `e2e` job in CI.
- Accessibility lint (stack-appropriate, e.g. `eslint-plugin-jsx-a11y` or axe in Playwright).
- `CLAUDE.md` section: "verify UI changes in the browser before calling them done", with the dev-server command and `.claude/launch.json` so the browser preview works.
- Preview deploy placeholder if a deploy target was given.

### 5.6 Deploy (placeholder)
If a target is named: a commented-out `.github/workflows/deploy.yml` with TODOs, and a README section listing the secrets it will need. A real deploy layer (one target first) is revisited after v0.2.

### 5.7 Docs & process (core + audience)
- `README.md`, ADR template (`docs/decisions/0001-record-architecture-decisions.md`).
- `.github/pull_request_template.md` (links the phase file and build-log entry), issue templates (bug, feature).

### 5.8 Company brain tracking (optional; Q10, default yes)

Logs the project in the user's company brain **at a high level only**.

**Tracked:**
- What the project is about (purpose, audience)
- Who contributes (names from git authors; no emails)
- Current version (from the stack's manifest, e.g. `package.json`/`pyproject.toml`, or the latest git tag)
- Major milestones (repo created, phase completed, release, deploy target set)
- Very high-level tech: app type and language (e.g. "Python app", "TS web app"), UI yes/no, app host
- Repo URL and local path

**Never tracked:** code changes, diffs, file names, build-log or test detail, review notes, secrets, client-confidential content.

**Where it goes:** one entry per project in the brain. If the brain has an index (e.g. `wiki/index.md`), start there to find the projects area and add one link line to the index; otherwise write `<brain>/projects/<slug>.md`. Never edit other brain pages.

**When it updates:**
- End of onboarding: create the entry.
- Milestones: a phase is merged, a version is tagged or bumped, a new contributor's first merge, host/tech changes. The workflow triggers the update at those points.
- SessionStart also compares the entry with the repo (version, contributors, phases done) and fixes drift.

**Where the setting lives:** brain path in `.harness/config.local.json` (gitignored), so teammates and clients who clone the repo don't inherit it; for them tracking is simply off. Turning it off later: delete that file.

## 6. Agents and workflow

| Role | Who | Tools | Writes |
|---|---|---|---|
| Coordinator | main session | all | phase state, build log |
| Planner | subagent | read + write phase files | `PLANS.md`, phase files |
| Tester | subagent | read, Bash, write tests | test plan + failing tests (before build); evidence (after) |
| Builder | subagent (both modes) | read, write, Bash | source code |
| Reviewer | subagent | read-only | review notes |
| Release | `/ship` skill, run by the user | — | commits, branch push, PR |

**Multi-phase loop:**

```
Planner drafts phase → user approves phase
→ Tester writes and explains the test plan → user approves test plan
→ Tester writes the failing tests, shows them → user approves tests → tests committed
Build loop (max N runs):
  → Builder implements (brief = phase file + test plan; on a rerun, plus the failure report)
  → Tester runs checks, records evidence in build log
  → Reviewer checks diff vs phase file + AGENTS.md; fails if approved tests changed without a recorded reason
     test or review fail → back to Builder
     pass → user runs /ship → PR → CI → user merges (ask)
After N failed runs: stop. Report what failed each time and ask the user how to proceed.
After merge: report "Phase NN merged. Next: phase NN+1 (<name>)." and wait for the user. Never start the next phase on its own.
```

**Retry limit (N):** same rule in both modes. Set during onboarding (Q11), stored in `.harness/config.json` as `retry_limit`, editable there later. A run = one builder attempt plus its test and review. CI failing after `/ship` counts as a failed run.

**Single-pass loop** (per task):

```
New task:
  Tester shows and explains the test(s) it will write → user approves the plan
  → Tester writes the tests, shows them → user approves tests → tests committed
Build loop (max N runs; N = retry limit, see below):
  → Builder writes the task code
  → Reviewer checks the code matches the task
  → Tester runs the tests, reports pass/fail, records evidence in build log
     fail → back to Builder, with the failure report as input
     pass → /ship (branch + PR) → CI → user approves merge when asked
After N failed runs: stop. Report what failed each time and ask the user how to proceed.
```

A PR only opens once the tests pass locally.

Rework on an existing task skips test writing and starts at the build loop. If a test itself needs to change, the tester shows the change and the user approves it first.

### 6.1 Orchestration and state

**Orchestrator = the main session.** Claude Code subagents can't start other subagents, so no orchestrator subagent. The main session runs the loop, calls each subagent in turn, and updates the state file after every step.

**State file:** `.harness/state.json`, the machine-readable record. Markdown files (`PLANS.md`, phase files, build log) stay the human-readable record.

```json
{
  "mode": "multi-phase",
  "phase": "02-data-connection",
  "step": "awaiting_test_approval",
  "run": 1,
  "retry_limit": 3,
  "last_result": null,
  "updated": "2026-11-16T15:04:00Z"
}
```

Single-pass uses `"task"` in place of `"phase"`. `retry_limit` is copied from `config.json`.

**Steps, in order:**

| Step | Who acts | Next |
|---|---|---|
| `awaiting_phase_approval` (multi-phase only) | user | `writing_test_plan` |
| `writing_test_plan` | tester | `awaiting_test_plan_approval` |
| `awaiting_test_plan_approval` | user | `writing_tests` (or back to `writing_test_plan` on changes) |
| `writing_tests` | tester | `awaiting_test_approval` |
| `awaiting_test_approval` | user | `building` (or back to `writing_tests`) |
| `building` | builder | `testing` (multi-phase) / `reviewing` (single-pass) |
| `testing` | tester | `reviewing` (multi-phase) / `ready_to_ship` (single-pass); fail → `building` with `run`+1 |
| `reviewing` | reviewer | `ready_to_ship` (multi-phase) / `testing` (single-pass); fail → `building` with `run`+1 |
| `ready_to_ship` | user runs `/ship` | `awaiting_merge` |
| `awaiting_merge` | CI, then user | `merged`; CI fail → `building` with `run`+1 |
| `merged` | user | multi-phase: `awaiting_phase_approval` for next phase, only when the user says go. Single-pass: idle until the next task |
| `stopped_retry_limit` | user | whatever the user decides |

Rework on an existing task enters at `building` (or `writing_tests` if a test must change).

**Enforced by hooks, not just instructions:**
- A transition not in the table is blocked (PreToolUse on writes to `state.json`).
- Calling a subagent that doesn't match the step is blocked (e.g. builder when step ≠ `building`; PreToolUse on Agent).
- `awaiting_*` steps can only be left after the user answers in the session; Claude can't move past them by itself.
- When a fail would make `run` exceed `retry_limit`, the only allowed next step is `stopped_retry_limit`.

**Committed to git:** yes, so state travels with the branch and survives a fresh clone. It changes on the working branch only; `main` holds the state as of the last merge.

**Gates:**
- Approve phase, approve test plan, approve written tests, run `/ship`, merge, start next phase, deploy: each is a separate human decision.
- Branch pushes and PR creation need no prompt; merges and deploys always ask.
- Direct push to `main` is blocked by hook and (where the plan allows) branch protection.
- No release agent: running `/ship` is the approval, and gates are enforced by permissions, hooks and branch protection, not agent instructions.
- Builder subagent trade-off accepted: no mid-build steering in multi-phase mode.

Run the security and test reviewers in parallel only when both are read-only. Never run builder and tester at the same time.

## 7. Audience matrix

| | Solo | Team | Client | Public |
|---|---|---|---|---|
| Default visibility | private | private | private | public |
| Required reviewers | 0 | 1 | 1 | 1 |
| CODEOWNERS | – | ✓ | ✓ | ✓ |
| CONTRIBUTING.md | – | ✓ | – | ✓ |
| LICENSE | – | – | – (ask) | ✓ (ask which; default MIT) |
| SECURITY.md, CodeQL | – | – | – | ✓ |
| Handoff doc (`docs/HANDOFF.md`) | – | – | ✓ | – |
| Labels set | minimal | full | full | full + `good first issue` |

## 8. Execution flow

1. **Preflight, tools** (`preflight.sh tools`): `gh` and `git` installed; `gh auth status` has `repo` + `workflow` scopes. Runs before the interview. On a failure, don't stop and don't make the user rerun the command. **Guided repair:**
   - Explain the problem in one line and the fix.
   - Install steps (e.g. `brew install gh`): offer to run them; run on the user's yes.
   - Sign-in steps (`gh auth login`, `gh auth refresh -s workflow`): these are interactive and the credentials are the user's, so the user runs them (in Claude Code: type `! gh auth login`). Claude waits.
   - Verify: rerun the failed check. Pass → resume where the forge left off. Fail → explain what's still wrong and repeat.
2. **Interview** (§4). Runs `preflight.sh name OWNER/slug` at Q4a and the local-path check at Q9.
3. **Plan preview:** opens with the repo URL (`github.com/OWNER/slug`), display name and local path, then file tree, every `gh` call, visibility, build mode, and any warnings (e.g. no branch protection, detected from the owner's plan). Each interview answer in the preview is numbered. **Stop for an answer:**
   - **yes:** continue.
   - **no:** stop; nothing is changed.
   - **change N:** re-ask question N only, re-run any check it affects (e.g. a new owner or name re-checks availability; a new language re-recommends the framework), then show the updated plan again.

   Re-check name availability just before step 7 in case it was taken meanwhile.
4. **Render** (`render.sh`): core → claude → mode → stack → ui → audience; later layers override earlier. Substitute tokens, record checksums. Skill then writes `AGENTS.md`, `GOALS.md`, README and (multi-phase) phase 01 from interview answers.
5. **Install + verify locally:** install deps, run `lint`, `test`, `build`. Must pass before anything touches GitHub. If `actionlint` is present, lint workflows.
6. **Git:** `git init -b main`, stage files, run the first-commit secrets check (§5.4a item 7), initial commit.
7. **Create:** `gh repo create OWNER/NAME --private|--public --source . --push --description "..."`.
8. **Configure** (`github-setup.sh`): branch protection or ruleset, secret scanning + push protection (where the plan allows), labels, disable wiki/projects if unused, set topics.
9. **Configure the agent workflow:** in the new repo, check that every agent in `.claude/agents/` parses and names only allowed tools, the hooks are registered, the SessionStart hook produces the right status, the push-to-`main` hook blocks a test push (dry, no network), and `/workflow` and `/ship` load. Multi-phase: confirm phase 01 is drafted and marked "awaiting approval".
10. **Company brain** (if Q10 = yes): create the project entry (§5.8).
11. **Report:** repo URL, local path, checklist of what ran ✓/✗, next steps (e.g. add deploy secrets). Last line: "Start a new Claude Code session in `<local path>`." Multi-phase adds: "It will show phase 01 for your approval first."

**Partial failure rule:** if step 8 fails, the repo stays; report the failure and the manual fix.

**Free-plan private repos:** branch protection needs GitHub Pro/Team. Warn in the plan preview, skip protection in step 8, report it as "not applied (plan limit)". The push-to-main hook still applies. Same for every audience.

**Dry run:** `/flatmap-repo-forge --dry-run` does steps 1–5 into a temp dir and skips all GitHub writes. Used by evals.

## 9. Install & distribution

**Prerequisites:** Claude Code, `git`, and `gh` signed in with `repo` + `workflow` scopes. Preflight checks these and prints the fix command.

**Install** (inside Claude Code):

```
/plugin marketplace add flatmap-solutions/flatmap-plugins
/plugin install flatmap@flatmap-plugins
```

Then run `/flatmap:flatmap-repo-forge` (or `/flatmap-repo-forge`).

**Marketplace:** public repo `flatmap-solutions/flatmap-plugins` (MIT). It is both the marketplace (`.claude-plugin/marketplace.json` at the root) and the plugin's source (`plugins/flatmap/`). Only the maintainer pushes to it; consumers only install (read). Other plugins, like the future translate plugin, go under `plugins/`.

**Updates:** bump `version` in `plugin.json` and tag a release; users pick it up with `/plugin marketplace update` and reinstall. Generated repos record the plugin version in `.harness/config.json`, so `/flatmap:harness-update` knows what changed.

## 10. Follow-on skills (v0.3)

- **`/flatmap:harness-update`:** re-apply templates from `.harness/config.json`; also upgrades single-pass → multi-phase.
- **`/flatmap:harness-narrowizer`:** downgrades multi-phase → single-pass.
  - Removes only plugin-generated files whose checksum is unchanged; lists edited ones and keeps them unless the user says otherwise.
  - Strips `forge:multi-phase` marker blocks from `AGENTS.md`/`CLAUDE.md`, leaving hand-written text alone.
  - Removes multi-phase-only agent instructions, hooks, CI steps and permissions.
  - Shows the full removal list and waits for a yes; runs on a new branch as one commit, so it can be reverted.
  - Sets `mode: single-pass` in `.harness/config.json`.
- **`/flatmap:harness-add`:** apply the harness to an existing repo.

## 11. Testing the plugin

- `claude plugin eval` suites in `evals/`, one per combination that matters: {TS, Python, generic} × {UI, no UI} × {solo, public} × {single-pass, multi-phase}, all in dry-run.
- Each eval asserts: expected files exist for the mode, no unrendered `{{TOKEN}}` left, checksums recorded, marker blocks balanced, `lint`/`test` pass in the scaffold, no GitHub calls made.
- Hook test: a push to `main` is blocked. Workflow test: agents parse, `/workflow` and `/ship` load, phase 01 is drafted in multi-phase, SessionStart reports the right next step.
- State test: every allowed transition passes; an invalid one (e.g. `awaiting_test_approval` → `building` without an answer, or builder called during `testing`) is blocked; the run after `retry_limit` goes to `stopped_retry_limit`.
- Scope test: nothing written outside the project folder except the brain entry; no writes to `~/.claude`.
- Secrets test: a fixture `.env` and a fake key pasted into a source file are both blocked at commit; `.env.example` is committed; Claude's deny list matches the `.gitignore` patterns.
- Brain test (fixture brain folder): entry created with only the tracked fields; no code, file names or diffs in it; `config.local.json` is gitignored.
- One manual end-to-end against a throwaway org before each release.

## 12. Milestones

- **v0.1:** `/flatmap:flatmap-repo-forge` with interview, repo setup and agent workflow config (incl. `/workflow`, `/ship`); core + claude layers, both build modes, TS + Python stacks, solo + public audiences, no UI layer, dry-run + evals. Checksums and `forge:` markers from day one, so v0.3 skills work on v0.1 repos.
- **v0.2:** UI layer, team + client audiences, Go + generic stacks.
- **v0.3:** `/harness-update`, `/harness-narrowizer`, `/harness-add`.

## 13. Future

- **Translate plugin:** converts this plugin and generated `.claude/` setups into Codex, Cursor and Copilot equivalents. Separate project; relies on the tool-neutral split in §3.

## 14. Decision log (2026-11-16)

1. Product name `flatmap-repo-forge`. Plugin is named `flatmap`; the command is `/flatmap:flatmap-repo-forge` (short: `/flatmap-repo-forge`). One command does interview → repo setup → agent workflow configuration.
2. Distribution: public marketplace repo `flatmap-solutions/flatmap-plugins` from the start (MIT). Maintainer-only pushes; consumers install read-only.
3. Free-plan branch protection: warn and skip, all audiences.
4. Company brain: conventions are not pulled from it (they live in templates). Tracking the project in it is optional and on by default (see #16).
5. Deploy: placeholder only.
6. `AGENTS.md` in every repo as the tool-neutral rules; `CLAUDE.md` imports it. Clients may use Codex, Cursor or Copilot.
7. Claude-first, with tool-specific parts isolated for a future translate plugin.
8. Build mode asked in the interview; default multi-phase.
9. `/harness-narrowizer` for multi-phase → single-pass downgrades.
10. Tester writes the test plan (and failing tests) before the build; user approves it.
11. Agents: planner, tester, builder (subagent; see #20), reviewer; `/ship` instead of a release agent.
12. Gates: push branches and open PRs freely; merges and deploys ask; hook blocks any push to `main`.
13. Vetted against a ChatGPT session on engineering harnesses: adopted single-ownership files, phase template, evidence-only build log, separate gates. Dropped coordinator subagent, handoff files and the six-agent default.
14. Repo naming: Q1 takes a display name; a slug is derived, shown as the full `OWNER/slug` URL, confirmed or edited, and checked for availability before the interview continues.
15. Handoff: the forge ends by telling the user to start a new session in the project folder. A SessionStart hook there starts and resumes the workflow; `/workflow` is optional. No same-session handoff, no plugin-side copies of agents or hooks.
16. Company brain: interview asks if one exists and whether to track the project (default yes). High-level only (purpose, contributors, version, milestones, high-level tech); never code changes. Brain path is gitignored, per user.
17. Scope: project level only. Nothing written to `~/.claude` or user settings; the brain entry is the only write outside the project folder.
18. Preflight failures: guided repair (offer to run installs; user runs sign-ins), verify, resume. Never make the user rerun the command.
19. Framework and language: recommended with a reason; user accepts or picks another.
20. Single-pass: tester explains and writes tests first (user approves), then builder → reviewer → tester runs tests → `/ship` only on pass. Fail loops back to builder. Builder is a subagent in both modes.
21. Retry limit: applies to both modes. Asked during onboarding (recommend 3, range 1–5); after N failed runs, stop and ask.
22. Two test approvals in both modes: the test plan, then the written tests.
23. After a multi-phase merge, Claude reports the next phase and waits for the user.
24. Plan preview accepts `yes`, `no` or `change N`.
25. Repeat users: from the 3rd run, habit questions with an unchanged answer are skipped and confirmed together. Run history lives in the plugin's data folder.
26. Secrets: layered protection in every repo (§5.4a): `.gitignore` patterns, `.env.example`, gitleaks pre-commit and in CI, GitHub secret scanning + push protection where the plan allows (else warn and skip), matching Claude deny list, first-commit check.
27. Orchestration: the main session is the orchestrator. Workflow state lives in `.harness/state.json` with a fixed step list; hooks read it and block invalid transitions, wrong-step subagent calls and runs past the retry limit.
