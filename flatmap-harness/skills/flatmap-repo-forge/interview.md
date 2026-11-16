# Interview question bank

Ask one question at a time, in this order. Keep each question short. Show the default and accept a one-word answer.
Skip a question when the command arguments already answered it.
The numbers are the ones the plan preview uses for `change N`.

## Repeat users (run 3 and later)

If `history-get` returned `shorter_interview: true`, don't ask the habit questions in `skippable`
(owner, visibility for this audience, deploy target, folder location, brain path, retry limit).
After question 3, confirm them together in one message:

> Using your usual: owner `<owner>`, `<visibility>`, deploy `<target>`, folder `<parent>/`, brain `<path or off>`, retry limit `<n>`. OK, or change one?

Questions about the project itself (1, 1a, 2, 3, 6, 6a, 7, 12) are always asked.

## Questions

**1. Project name and purpose**
"What's the project called? Use the name as you'd say it, e.g. *Acme Client Dashboard*. And in one sentence, what does it do?"
→ `project_name`, `purpose`

**1a. Success and non-goals**
"How will you know it worked? Give one to three success criteria. And what is it explicitly *not* doing?"
→ `success_criteria` (list), `non_goals` (list)

**2. Audience**
"Who is it for: just you, or public open source?"
→ `audience`: `solo` | `public`.
v0.1 supports these two. If the user says *my team* or *a client*, say those audiences arrive in v0.2 and offer `solo` (private) for now.

**3. Build mode**
"Is this a multi-phase build (you'd want to review it in chunks) or a single-pass project (one or two sittings)? Default: multi-phase."
→ `mode`: `multi-phase` | `single-pass`.
Rule of thumb to share if they're unsure: if you'd want to stop partway and review before going on, it's multi-phase.

**3a. First phase** (multi-phase only)
"What's the first chunk you'd want to review before going further?"
From the answer, draft `phase1`: `name` (3-5 words), `objective` (1-2 sentences), `in_scope`, `out_of_scope`, `acceptance` (observable criteria) and `files_affected` (paths or globs, your best guess; e.g. `src/sales/**`). Show the draft in five lines and let the user adjust it.

**4. GitHub owner**
List the options from `gh api user --jq .login` and `gh api user/memberships/orgs --jq '.[].organization.login'`.
"Which GitHub owner: `<you>` or `<org>`?"
→ `owner`

**4a. Repo name**
Run `forge.py slug "<project name>"` (or use the slug from the arguments). Then:
"The repo will be `<owner>/<slug>` at https://github.com/<owner>/<slug>. OK, or change the name?"
Run `forge.py preflight-name <owner>/<slug> --visibility <default visibility>`. If `available` is false, say it's taken and ask for another name now.
→ `slug`

**5. Visibility**
Default: `public` for public open source, otherwise `private`. "Private or public? Default: <default>."
If the answer changes visibility, rerun `preflight-name` with the new `--visibility`.
→ `visibility`

**6. Frontend UI**
"Will it have a frontend UI?"
→ `ui`. v0.1 has no UI layer: if yes, say the UI layer arrives in v0.2, and that you'll set it up without one for now (it can be added later). Set `ui: false`.

**6a. Framework** (only when a UI is in scope; from v0.2)
Recommend one with a one-line reason from the earlier answers. "I recommend <X> because <reason>. OK, or another?"

**7. Language**
Recommend one with a one-line reason drawn from the purpose and audience, e.g.:
- data work, scripts, CLIs, ML → Python: "I recommend Python because <reason>."
- web services, libraries for the JS ecosystem, anything headed for a JS frontend → TypeScript.
"I recommend <X> because <reason>. OK, or another?"
→ `stack`: `typescript` | `python` (v0.1). If they want another language, say Go and others arrive in v0.2 and ask them to pick one of the two for now.
If a framework already implies the language, only confirm it.

**8. Deploy target**
"Where will it run, if you know? Vercel, Fly, Cloud Run, other, or none yet. Default: none."
→ `deploy_target`: `none` | `vercel` | `fly` | `cloud-run` | any other short name.
Tell them deploys stay a placeholder: a commented-out workflow plus the list of secrets it will need.

**9. Local folder**
Default `~/Claude/Projects/<slug>` (or `<usual parent>/<slug>` for repeat users). "I'll put it in `<path>`. OK, or another folder?"
Run `forge.py preflight-path <path>`. If not ok, say why and ask again.
→ `local_path`

**10. Company brain**
"Do you have a company brain (a knowledge-base folder)? I can keep a high-level entry for this project there: what it's about, contributors, version, milestones and the tech at a glance. Never code changes. Default: yes, if you have one."
If yes: "What's the folder path?" Check it exists (`ls`). If it doesn't, ask again or turn tracking off.
→ `brain`: `{"enabled": true, "path": "<path>"}` or `{"enabled": false}`

**11. Retry limit**
"If the code fails its tests or review, how many times should the builder retry before stopping to ask you? I recommend 3 (1 to 5)."
→ `retry_limit` (integer 1-5)

**12. Wiki**
Recommend one with a one-line reason from the earlier answers. A wiki helps when many people will ask questions about the project (public, client or team audiences, or a long multi-phase build). For a small or early project, hold off: the guide in `docs/guide/` is enough to start.
"Doc, the project's writer, will keep a plain-language guide and runbook up to date after every merge. Would this project benefit from a wiki too, or hold off until it's more mature? I recommend <now | holding off> because <reason>. Doc can start one later with Builder's help if it needs tooling."
→ `docs_wiki`: `true` (start it now) | `false` (hold off; default)

**Public only: license and code owners**
"License: MIT (default) or none?" → `license`: `MIT` | `none`. Other licenses: add by hand after setup.
Code owners default to `@<owner>` → `codeowners`.

## answers.json schema

```json
{
  "project_name": "Acme Client Dashboard",
  "slug": "acme-client-dashboard",
  "purpose": "One sentence.",
  "success_criteria": ["..."],
  "non_goals": ["..."],
  "audience": "solo",
  "mode": "multi-phase",
  "owner": "flatmap-solutions",
  "visibility": "private",
  "ui": false,
  "stack": "typescript",
  "deploy_target": "none",
  "local_path": "/Users/me/Claude/Projects/acme-client-dashboard",
  "brain": {"enabled": true, "path": "/Users/me/ai-workspace"},
  "retry_limit": 3,
  "docs_wiki": false,
  "license": "MIT",
  "codeowners": "@flatmap-solutions",
  "phase1": {
    "name": "Sales data loader",
    "objective": "Load weekly sales from the CSV export into typed records.",
    "in_scope": ["..."],
    "out_of_scope": ["..."],
    "acceptance": ["..."],
    "files_affected": ["src/sales/**"]
  }
}
```

`license` and `codeowners` apply to public repos. `phase1` applies to multi-phase.
