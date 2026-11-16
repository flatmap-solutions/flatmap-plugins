# flatmap-plugins

Claude Code plugin marketplace from flatmap-solutions.

## Plugins

| Plugin | What it does | Status |
|---|---|---|
| [`flatmap`](plugins/flatmap/) | `/flatmap:flatmap-repo-forge`: interviews you, creates a GitHub repo with an engineering harness (CI, quality tooling, secrets protection), and sets up a test-first agent workflow. | Spec only, v0.1 in progress. See [SPEC.md](plugins/flatmap/SPEC.md). |

## Install

Inside Claude Code:

```
/plugin marketplace add flatmap-solutions/flatmap-plugins
/plugin install flatmap@flatmap-plugins
```

## License

MIT
