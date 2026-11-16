# flatmap-plugins

Claude Code plugin marketplace from flatmap-solutions.

## Plugins

### [`flatmap`](flatmap/)

Engineering harness for new and existing projects: GitHub repo setup, CI, quality tooling, secrets protection and a test-first agent workflow. Details: [README](flatmap/README.md) · design: [SPEC.md](flatmap/SPEC.md).

| Skill | What it does | Status |
|---|---|---|
| `/flatmap:flatmap-repo-forge` | Interviews you, creates a new GitHub repo with the full harness, and sets up the agent workflow. | **v0.1** |
| `/flatmap:harness-update <single\|multi>` | Re-applies the latest harness to a repo it created, in the mode you pass: `single` keeps or switches it to single-pass (removing only unchanged multi-phase files), `multi` keeps or upgrades it to multi-phase. | planned (v0.3) |
| `/flatmap:harness-add` | Adds the harness to an existing repo: detects what's there, merges instead of overwriting. | planned (v0.3) |

Inside a repo the forge created, two more commands are available: `/ship` (branch, checks, PR) and `/workflow` (where things stand).

## Install

Inside Claude Code:

```
/plugin marketplace add flatmap-solutions/flatmap-plugins
/plugin install flatmap@flatmap-plugins
```

## License

MIT
