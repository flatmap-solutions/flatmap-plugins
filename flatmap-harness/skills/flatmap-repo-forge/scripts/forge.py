#!/usr/bin/env python3
"""flatmap-repo-forge engine.

Deterministic steps for the /flatmap-harness:flatmap-repo-forge skill. The skill owns the
interview and judgment; this script owns everything that must be exact: slugs,
preflight checks, rendering templates, checksums, git, gh calls, verification.

Every subcommand prints one JSON object to stdout. Exit code 0 = ran (check the
"ok" field), 1 = bad input or unexpected error.

Python 3.8+, standard library only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = PLUGIN_ROOT / "templates"
PLUGIN_VERSION = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]

TOKEN_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
PATH_TOKEN_RE = re.compile(r"__([A-Z0-9_]+)__")
MP_BLOCK_RE = re.compile(r"[ \t]*<!-- forge:multi-phase -->.*?<!-- /forge:multi-phase -->[ \t]*\n?", re.S)

SUPPORTED = {
    "stack": ["typescript", "python"],
    "audience": ["solo", "public"],
    "mode": ["multi-phase", "single-pass"],
    "visibility": ["private", "public"],
}

# ---------------------------------------------------------------------------
# Secret patterns: the single source for .gitignore, Claude's deny list and the
# first-commit check (spec 5.4a).
# ---------------------------------------------------------------------------

SECRET_PATTERNS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "*credentials*.json",
    "service-account*.json",
    "secrets.*",
]
SECRET_EXCEPTIONS = [".env.example"]
PERSONAL_FILES = [".claude/settings.local.json", ".harness/config.local.json", ".harness/.session.json"]
# Local working files the harness makes (not secret, never committed).
LOCAL_WORK = [".harness/.docs-queue.json", ".harness/worktrees/"]
JUNK_PATTERNS = [".DS_Store", "Icon?", ".idea/", ".vscode/*", "!.vscode/settings.json", "!.vscode/extensions.json"]

# Claude Code deny rules can't express "except .env.example", so `.env.*` is
# expanded into the common variants instead (deny always beats allow).
ENV_VARIANTS = [".env.local", ".env.development", ".env.production", ".env.staging", ".env.test", ".env.prod", ".env.dev"]


def gitignore_secret_lines() -> list[str]:
    lines = ["# Secrets (flatmap-repo-forge: never commit these)"]
    lines += SECRET_PATTERNS
    lines += ["!" + e for e in SECRET_EXCEPTIONS]
    lines += ["", "# Personal, per-developer files"] + PERSONAL_FILES
    lines += ["", "# Harness working files (docs queue, docs worktree)"] + LOCAL_WORK
    lines += ["", "# OS and editor files"] + JUNK_PATTERNS
    return lines


def deny_rules() -> list[str]:
    rules = []
    for p in SECRET_PATTERNS:
        if p == ".env.*":
            for v in ENV_VARIANTS:
                rules.append(f"Read(**/{v})")
                rules.append(f"Read(**/{v}.*)")
            continue
        rules.append(f"Read(**/{p})")
    return rules


def glob_to_regex(pattern: str) -> re.Pattern:
    """gitignore-ish glob -> regex, matched against a path or its basename."""
    i, out = 0, ""
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$")


def matches_secret(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if name in SECRET_EXCEPTIONS:
        return None
    for p in SECRET_PATTERNS:
        rx = glob_to_regex(p)
        if rx.match(name) or rx.match(path):
            return p
    for p in PERSONAL_FILES:
        if path == p:
            return p
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def out(obj: dict, code: int = 0) -> None:
    print(json.dumps(obj, indent=2))
    sys.exit(code)


def run(cmd: list[str], cwd: str | Path | None = None, timeout: int = 900, env: dict | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})}
        )
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s: {' '.join(cmd)}"


def tail(text: str, n: int = 40) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_answers(path: str) -> dict:
    return json.loads(Path(path).read_text())


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9.-]", "", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-.")


def bullets(items) -> str:
    items = [i for i in (items or []) if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else "- (none yet)"


def numbered(items) -> str:
    items = [i for i in (items or []) if str(i).strip()]
    return "\n".join(f"{n}. {i}" for n, i in enumerate(items, 1)) if items else "1. (none yet)"


# ---------------------------------------------------------------------------
# Stack facts (commands, globs, preflight tools)
# ---------------------------------------------------------------------------

STACKS = {
    "typescript": {
        "label": "TypeScript (Node.js)",
        "app_type": "TypeScript app",
        "tools": [
            ("node", ["node", "--version"], "brew install node"),
            ("npm", ["npm", "--version"], "brew install node"),
        ],
        "test_globs": ["src/**/*.test.ts", "tests/**"],
        "fmt_file": "npx --no-install biome format --write {file}",
        "fmt_exts": [".ts", ".tsx", ".js", ".jsx", ".json", ".mjs", ".cjs"],
        "codeql": "javascript-typescript",
        "dependabot": "npm",
        "version_file": "package.json",
    },
    "python": {
        "label": "Python (uv)",
        "app_type": "Python app",
        "tools": [
            ("uv", ["uv", "--version"], "brew install uv"),
        ],
        "test_globs": ["tests/**"],
        "fmt_file": "uv run --quiet ruff format {file}",
        "fmt_exts": [".py"],
        "codeql": "python",
        "dependabot": "uv",
        "version_file": "pyproject.toml",
    },
}

DEPLOY_SECRETS = {
    "vercel": ["VERCEL_TOKEN", "VERCEL_ORG_ID", "VERCEL_PROJECT_ID"],
    "fly": ["FLY_API_TOKEN"],
    "cloud-run": ["GCP_PROJECT_ID", "GCP_WORKLOAD_IDENTITY_PROVIDER", "GCP_SERVICE_ACCOUNT"],
}
DEPLOY_ASK = {
    "vercel": ["Bash(vercel:*)", "Bash(npx vercel:*)"],
    "fly": ["Bash(fly deploy:*)", "Bash(flyctl deploy:*)"],
    "cloud-run": ["Bash(gcloud run deploy:*)"],
}

BASE_TOOLS = [
    ("git", ["git", "--version"], "brew install git", "install"),
    ("gh", ["gh", "--version"], "brew install gh", "install"),
    ("python3", ["python3", "--version"], "brew install python", "install"),
    ("make", ["make", "--version"], "xcode-select --install", "install"),
    ("gitleaks", ["gitleaks", "version"], "brew install gitleaks", "install"),
    ("lefthook", ["lefthook", "version"], "brew install lefthook", "install"),
]


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------


def cmd_preflight_tools(a) -> None:
    checks = []
    for name, cmd, fix, kind in BASE_TOOLS:
        code, text = run(cmd, timeout=30)
        checks.append({"name": name, "ok": code == 0, "detail": text.splitlines()[0] if text else "", "fix": fix, "kind": kind})
    if a.stack:
        for name, cmd, fix in STACKS[a.stack]["tools"]:
            code, text = run(cmd, timeout=30)
            checks.append({"name": name, "ok": code == 0, "detail": text.splitlines()[0] if text else "", "fix": fix, "kind": "install"})

    # git identity (needed for the first commit)
    for key in ("user.name", "user.email"):
        code, text = run(["git", "config", "--get", key], timeout=10)
        checks.append({
            "name": f"git {key}", "ok": code == 0 and bool(text), "detail": text if code == 0 else "not set",
            "fix": f'git config --global {key} "<your {key.split(".")[1]}>"', "kind": "user",
        })

    # gh sign-in + scopes
    code, text = run(["gh", "auth", "status"], timeout=30)
    signed_in = code == 0
    checks.append({"name": "gh signed in", "ok": signed_in, "detail": "" if signed_in else tail(text, 3),
                   "fix": "gh auth login", "kind": "signin"})
    if signed_in:
        m = re.search(r"Token scopes:\s*(.*)", text)
        scopes = re.findall(r"[\w:]+", m.group(1)) if m else []
        for scope in ("repo", "workflow"):
            ok = scope in scopes or not m  # fine-grained tokens don't list scopes; don't block on them
            checks.append({"name": f"gh scope: {scope}", "ok": ok, "detail": ", ".join(scopes),
                           "fix": f"gh auth refresh -h github.com -s {scope}", "kind": "signin"})
    out({"ok": all(c["ok"] for c in checks), "checks": checks, "failed": [c for c in checks if not c["ok"]]})


def owner_info(owner: str) -> dict:
    info = {"owner": owner, "type": None, "plan": None, "is_self": False}
    code, login = run(["gh", "api", "user", "--jq", ".login"], timeout=30)
    me = login.strip() if code == 0 else None
    info["is_self"] = me is not None and me.lower() == owner.lower()
    code, t = run(["gh", "api", f"users/{owner}", "--jq", ".type"], timeout=30)
    info["type"] = t.strip() if code == 0 else None
    if info["is_self"]:
        code, p = run(["gh", "api", "user", "--jq", ".plan.name // empty"], timeout=30)
    else:
        code, p = run(["gh", "api", f"orgs/{owner}", "--jq", ".plan.name // empty"], timeout=30)
    info["plan"] = (p.strip() or None) if code == 0 else None
    return info


def protection_available(visibility: str, plan: str | None) -> tuple[bool, str]:
    if visibility == "public":
        return True, "public repo"
    if plan is None:
        return False, "couldn't read the GitHub plan; assuming branch protection isn't available for this private repo"
    if plan.lower() == "free":
        return False, "GitHub Free doesn't offer branch protection on private repos"
    return True, f"plan: {plan}"


def cmd_preflight_name(a) -> None:
    owner, _, slug = a.repo.partition("/")
    if not owner or not slug:
        out({"ok": False, "error": "expected OWNER/SLUG"}, 1)
    valid = slug == slugify(slug) and bool(slug)
    code, _ = run(["gh", "repo", "view", a.repo, "--json", "name"], timeout=30)
    available = code != 0
    info = owner_info(owner)
    vis = a.visibility or "private"
    bp_ok, bp_why = protection_available(vis, info["plan"])
    out({
        "ok": valid and available, "repo": a.repo, "url": f"https://github.com/{a.repo}",
        "valid_slug": valid, "available": available, "owner": info,
        "branch_protection": {"available": bp_ok, "why": bp_why},
        "secret_scanning": {"available": vis == "public",
                            "why": "free on public repos" if vis == "public" else "private repos need a paid GitHub add-on"},
    })


def cmd_preflight_path(a) -> None:
    p = Path(os.path.expanduser(a.path)).resolve()
    if p.exists() and not p.is_dir():
        out({"ok": False, "path": str(p), "reason": "a file already exists at that path"})
    if p.exists() and any(p.iterdir()):
        out({"ok": False, "path": str(p), "reason": "folder exists and isn't empty"})
    parent = p.parent
    while not parent.exists():
        parent = parent.parent
    writable = os.access(parent, os.W_OK)
    out({"ok": writable, "path": str(p), "reason": "" if writable else f"can't write to {parent}"})


def cmd_slug(a) -> None:
    out({"ok": True, "name": a.name, "slug": slugify(a.name)})


# ---------------------------------------------------------------------------
# history (repeat users; spec 4)
# ---------------------------------------------------------------------------

HABITS = ["owner", "deploy_target", "local_parent", "brain_path", "retry_limit"]


def data_dir(a) -> Path:
    d = a.data_dir or os.environ.get("FLATMAP_DATA_DIR") or ""
    if not d or "${" in d:
        d = os.path.expanduser("~/.flatmap")
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def habits_of(ans: dict) -> dict:
    brain = ans.get("brain") or {}
    return {
        "owner": ans.get("owner"),
        f"visibility:{ans.get('audience')}": ans.get("visibility"),
        "deploy_target": ans.get("deploy_target", "none"),
        "local_parent": str(Path(os.path.expanduser(ans["local_path"])).parent) if ans.get("local_path") else None,
        "brain_path": brain.get("path") if brain.get("enabled") else "off",
        "retry_limit": ans.get("retry_limit"),
    }


def cmd_history_get(a) -> None:
    f = data_dir(a) / "history.json"
    h = json.loads(f.read_text()) if f.exists() else {"runs": 0, "habits": []}
    runs = h.get("runs", 0)
    skippable = {}
    if runs >= 2:  # this will be run 3 or later
        keys = set().union(*[set(x) for x in h["habits"]]) if h["habits"] else set()
        for k in keys:
            vals = [x.get(k) for x in h["habits"] if k in x]
            if len(vals) == len(h["habits"]) and len(set(map(json.dumps, vals))) == 1 and vals[0] is not None:
                skippable[k] = vals[0]
    out({"ok": True, "runs": runs, "this_run": runs + 1, "shorter_interview": runs >= 2, "skippable": skippable,
         "file": str(f)})


def cmd_history_record(a) -> None:
    f = data_dir(a) / "history.json"
    h = json.loads(f.read_text()) if f.exists() else {"runs": 0, "habits": []}
    h["runs"] = h.get("runs", 0) + 1
    h["habits"].append(habits_of(load_answers(a.answers)))
    h["habits"] = h["habits"][-10:]
    f.write_text(json.dumps(h, indent=2))
    out({"ok": True, "runs": h["runs"], "file": str(f)})


# ---------------------------------------------------------------------------
# answers validation + tokens
# ---------------------------------------------------------------------------

REQUIRED = ["project_name", "slug", "purpose", "audience", "mode", "owner", "visibility", "stack", "local_path", "retry_limit"]


def validate(ans: dict) -> list[str]:
    errs = [f"missing: {k}" for k in REQUIRED if ans.get(k) in (None, "")]
    for k, allowed in SUPPORTED.items():
        if ans.get(k) and ans[k] not in allowed:
            errs.append(f"{k} '{ans[k]}' isn't supported in v{PLUGIN_VERSION} (supported: {', '.join(allowed)})")
    if ans.get("ui"):
        errs.append(f"UI layer isn't in v{PLUGIN_VERSION} yet (planned v0.2); set ui=false")
    if ans.get("slug") and ans["slug"] != slugify(ans["slug"]):
        errs.append(f"slug '{ans['slug']}' isn't valid; try '{slugify(ans['slug'])}'")
    rl = ans.get("retry_limit")
    if rl is not None and (not isinstance(rl, int) or not 1 <= rl <= 5):
        errs.append("retry_limit must be an integer 1-5")
    if ans.get("mode") == "multi-phase":
        p1 = ans.get("phase1") or {}
        if not p1.get("name") or not p1.get("objective"):
            errs.append("multi-phase needs phase1.name and phase1.objective")
    brain = ans.get("brain") or {}
    if brain.get("enabled") and not brain.get("path"):
        errs.append("brain.enabled needs brain.path")
    if "docs_wiki" in ans and not isinstance(ans["docs_wiki"], bool):
        errs.append("docs_wiki must be true (start the wiki now) or false (hold off)")
    lic = ans.get("license", "MIT" if ans.get("audience") == "public" else "none")
    if lic not in ("MIT", "none"):
        errs.append(f"license '{lic}' isn't templated in v{PLUGIN_VERSION} (MIT or none); add other licenses by hand after setup")
    return errs


def phase1_id(ans: dict) -> str:
    p1 = ans.get("phase1") or {}
    return "01-" + (slugify(p1.get("name", "first-phase")) or "first-phase")


def deploy_section(target: str) -> str:
    if not target or target == "none":
        return ""
    secrets = DEPLOY_SECRETS.get(target, ["<add the secrets your host needs>"])
    lines = [
        "## Deploy (not wired up yet)",
        "",
        f"Target: **{target}**. `.github/workflows/deploy.yml` is a commented-out placeholder.",
        "To finish it:",
        "",
        "1. Add these repository secrets (Settings → Secrets and variables → Actions):",
    ]
    lines += [f"   - `{s}`" for s in secrets]
    lines += ["2. Uncomment and complete the steps in `.github/workflows/deploy.yml`.", ""]
    return "\n".join(lines)


def tokens_for(ans: dict) -> dict:
    stack = STACKS[ans["stack"]]
    p1 = ans.get("phase1") or {}
    year = str(_dt.date.today().year)
    t = {
        "PROJECT_NAME": ans["project_name"],
        "SLUG": ans["slug"],
        "PY_PACKAGE": ans["slug"].replace("-", "_").replace(".", "_"),
        "OWNER": ans["owner"],
        "REPO_URL": f"https://github.com/{ans['owner']}/{ans['slug']}",
        "PURPOSE": ans["purpose"].strip(),
        "PURPOSE_TOML": json.dumps(ans["purpose"].strip()),
        "SUCCESS_CRITERIA": bullets(ans.get("success_criteria")),
        "NON_GOALS": bullets(ans.get("non_goals")),
        "AUDIENCE": ans["audience"],
        "MODE": ans["mode"],
        "VISIBILITY": ans["visibility"],
        "STACK_LABEL": stack["label"],
        "APP_TYPE": stack["app_type"],
        "RETRY_LIMIT": str(ans["retry_limit"]),
        "YEAR": year,
        "DATE": _dt.date.today().isoformat(),
        "LICENSE_HOLDER": ans.get("license_holder") or ans["owner"],
        "CODEOWNERS": ans.get("codeowners") or f"@{ans['owner']}",
        "CODEQL_LANGUAGE": stack["codeql"],
        "DEPENDABOT_ECOSYSTEM": stack["dependabot"],
        "DEPLOY_TARGET": ans.get("deploy_target") or "none",
        "DEPLOY_SECTION": deploy_section(ans.get("deploy_target") or "none"),
        "PLUGIN_VERSION": PLUGIN_VERSION,
        "PHASE1_ID": phase1_id(ans),
        "PHASE1_NAME": p1.get("name", ""),
        "PHASE1_OBJECTIVE": p1.get("objective", ""),
        "PHASE1_IN_SCOPE": bullets(p1.get("in_scope")),
        "PHASE1_OUT_OF_SCOPE": bullets(p1.get("out_of_scope")),
        "PHASE1_ACCEPTANCE": bullets(p1.get("acceptance")),
        "PHASE1_FILES": bullets(p1.get("files_affected") or ["(the planner fills this in before the build)"]),
        "TEST_GLOBS": ", ".join(f"`{g}`" for g in stack["test_globs"]),
        "DOCS_WIKI": "on" if ans.get("docs_wiki") else "off (Doc can start one later; ask for `/docs wiki on`)",
    }
    return t


# ---------------------------------------------------------------------------
# render (spec 8 step 4)
# ---------------------------------------------------------------------------


def layers_for(ans: dict) -> list[Path]:
    ls = [TEMPLATES / "core", TEMPLATES / "claude", TEMPLATES / "mode" / ans["mode"],
          TEMPLATES / "stacks" / ans["stack"], TEMPLATES / "audience" / ans["audience"]]
    if ans.get("deploy_target", "none") not in (None, "", "none"):
        ls.append(TEMPLATES / "deploy")
    if ans.get("audience") == "public" and ans.get("license", "MIT") == "MIT":
        ls.append(TEMPLATES / "license" / "mit")
    if ans.get("docs_wiki"):
        ls.append(TEMPLATES / "docs-wiki")
    return [l for l in ls if l.exists()]


def substitute(text: str, tokens: dict, where: str, missing: set) -> str:
    def rep(m):
        k = m.group(1)
        if k in tokens:
            return tokens[k]
        missing.add(f"{where}: {{{{{k}}}}}")
        return m.group(0)
    return TOKEN_RE.sub(rep, text)


def collect_files(ans: dict, tokens: dict) -> tuple[dict, list[str]]:
    """Merge layers -> {relpath: text}. Later layers override; *.append files append;
    _tokens/<NAME> files define multi-line tokens."""
    files: dict[str, str] = {}
    appends: dict[str, list[str]] = {}
    for layer in layers_for(ans):
        tok_dir = layer / "_tokens"
        if tok_dir.is_dir():
            for tf in sorted(tok_dir.iterdir()):
                tokens[tf.name] = tf.read_text().rstrip("\n")
    for layer in layers_for(ans):
        for f in sorted(layer.rglob("*")):
            if f.is_dir() or "_tokens" in f.relative_to(layer).parts or f.name in (".keep", ".DS_Store", "Icon\r"):
                continue
            rel = f.relative_to(layer).as_posix()
            rel = PATH_TOKEN_RE.sub(lambda m: tokens.get(m.group(1), m.group(0)), rel)
            text = f.read_text()
            if rel.endswith(".append"):
                appends.setdefault(rel[: -len(".append")], []).append(text)
            else:
                files[rel] = text
    for rel, parts in appends.items():
        files[rel] = files.get(rel, "") + "".join(parts)
    missing: set = set()
    rendered = {}
    for rel, text in files.items():
        text = substitute(text, tokens, rel, missing)
        if ans["mode"] == "single-pass":
            text = MP_BLOCK_RE.sub("", text)
        rendered[rel] = text
    return rendered, sorted(missing)


def settings_json(ans: dict) -> dict:
    allow = [
        "Bash(make install)", "Bash(make lint)", "Bash(make fmt)", "Bash(make typecheck)",
        "Bash(make test)", "Bash(make build)", "Bash(make check)",
        "Bash(python3 .claude/hooks/harness.py:*)",
        "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)",
        "Bash(git add:*)", "Bash(git commit:*)", "Bash(git switch:*)", "Bash(git checkout:*)",
        "Bash(git branch:*)", "Bash(git push:*)", "Bash(git fetch:*)", "Bash(git pull:*)",
        "Bash(gh pr create:*)", "Bash(gh pr view:*)", "Bash(gh pr checks:*)", "Bash(gh pr list:*)",
        "Bash(gh run view:*)", "Bash(gh run list:*)",
        "Bash(gh pr diff:*)", "Bash(git worktree:*)", "Bash(git -C .harness/worktrees/docs:*)",
    ]
    ask = ["Bash(gh pr merge:*)"]
    for v in DEPLOY_ASK.values():
        ask += v
    hook = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/harness.py" '
    return {
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "permissions": {"allow": allow, "ask": ask, "deny": deny_rules()},
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": hook + "session-start"}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": hook + "user-prompt"}]}],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": hook + "pre-bash"}]},
                {"matcher": "Agent|Task", "hooks": [{"type": "command", "command": hook + "pre-agent"}]},
                {"matcher": "Write|Edit|MultiEdit|NotebookEdit", "hooks": [{"type": "command", "command": hook + "pre-write"}]},
            ],
            "PostToolUse": [
                {"matcher": "Write|Edit|MultiEdit", "hooks": [{"type": "command", "command": hook + "post-edit"}]},
            ],
            "Stop": [{"hooks": [{"type": "command", "command": hook + "stop"}]}],
        },
    }


def config_json(ans: dict, files: dict) -> dict:
    stack = STACKS[ans["stack"]]
    return {
        "plugin": "flatmap-repo-forge",
        "plugin_version": PLUGIN_VERSION,
        "created": now_iso(),
        "project_name": ans["project_name"],
        "slug": ans["slug"],
        "repo": f"{ans['owner']}/{ans['slug']}",
        "purpose": ans["purpose"],
        "audience": ans["audience"],
        "mode": ans["mode"],
        "visibility": ans["visibility"],
        "stack": ans["stack"],
        "app_type": stack["app_type"],
        "ui": bool(ans.get("ui")),
        "deploy_target": ans.get("deploy_target") or "none",
        "retry_limit": ans["retry_limit"],
        "docs_wiki_at_setup": bool(ans.get("docs_wiki")),
        "commands": {k: f"make {k}" for k in ("install", "lint", "fmt", "typecheck", "test", "build")},
        "test_globs": stack["test_globs"],
        "fmt_file": stack["fmt_file"],
        "fmt_exts": stack["fmt_exts"],
        "version_file": stack["version_file"],
        "files": files,
    }


def initial_state(ans: dict) -> dict:
    s = {
        "mode": ans["mode"],
        "step": "awaiting_phase_approval" if ans["mode"] == "multi-phase" else "idle",
        "run": 0,
        "retry_limit": ans["retry_limit"],
        "last_result": None,
        "entered": now_iso(),
        "entered_ts": time.time(),
        "updated": now_iso(),
        "completed": [],
        "history": [],
    }
    if ans["mode"] == "multi-phase":
        s["phase"] = phase1_id(ans)
    else:
        s["task"] = None
    return s


def render_to(ans: dict, dest: Path) -> dict:
    errs = validate(ans)
    if errs:
        return {"ok": False, "errors": errs}
    tokens = tokens_for(ans)
    files, missing = collect_files(ans, tokens)
    if missing:
        return {"ok": False, "errors": ["unrendered tokens"] + missing}
    files[".gitignore"] = "\n".join(gitignore_secret_lines()) + "\n\n" + files.get(".gitignore", "")
    files[".claude/settings.json"] = json.dumps(settings_json(ans), indent=2) + "\n"

    dest.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        if rel.endswith(".py") and "/hooks/" in rel or rel.endswith(".sh"):
            p.chmod(0o755)

    checksums = {rel: sha256(dest / rel) for rel in sorted(files)}
    (dest / ".harness").mkdir(exist_ok=True)
    (dest / ".harness" / "config.json").write_text(json.dumps(config_json(ans, checksums), indent=2) + "\n")
    (dest / ".harness" / "state.json").write_text(json.dumps(initial_state(ans), indent=2) + "\n")
    (dest / ".harness" / "docs.json").write_text(json.dumps({"wiki": bool(ans.get("docs_wiki")), "documented": [], "last_run": None}, indent=2) + "\n")

    brain = ans.get("brain") or {}
    if brain.get("enabled"):
        bp = str(Path(os.path.expanduser(brain["path"])).resolve())
        (dest / ".harness" / "config.local.json").write_text(json.dumps({"brain_path": bp, "local_path": str(dest)}, indent=2) + "\n")
        (dest / ".claude" / "settings.local.json").write_text(json.dumps({"permissions": {"additionalDirectories": [bp]}}, indent=2) + "\n")

    leftovers = [str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file() and p.suffix in (".md", ".yml", ".yaml", ".json", ".toml", ".ts", ".py", "") and TOKEN_RE.search(p.read_text(errors="ignore"))]
    if leftovers:
        return {"ok": False, "errors": ["unrendered tokens in output"] + leftovers}
    return {"ok": True, "path": str(dest), "files": sorted(list(files) + [".harness/config.json", ".harness/state.json", ".harness/docs.json"])}


def cmd_render(a) -> None:
    ans = load_answers(a.answers)
    dest = Path(os.path.expanduser(a.out or ans["local_path"])).resolve()
    if dest.exists() and any(dest.iterdir()) and not a.force:
        out({"ok": False, "errors": [f"{dest} exists and isn't empty"]})
    out(render_to(ans, dest))


def tree(paths: list[str]) -> str:
    lines, seen = [], set()
    for p in sorted(paths):
        parts = p.split("/")
        for i in range(len(parts) - 1):
            d = "/".join(parts[: i + 1])
            if d not in seen:
                seen.add(d)
                lines.append("  " * i + parts[i] + "/")
        lines.append("  " * (len(parts) - 1) + parts[-1])
    return "\n".join(lines)


def cmd_plan(a) -> None:
    ans = load_answers(a.answers)
    errs = validate(ans)
    if errs:
        out({"ok": False, "errors": errs})
    with tempfile.TemporaryDirectory() as td:
        r = render_to(ans, Path(td) / "preview")
    if not r["ok"]:
        out(r)
    repo = f"{ans['owner']}/{ans['slug']}"
    oi = json.loads(a.owner_info) if a.owner_info else None
    warnings = []
    if oi:
        if not oi.get("branch_protection", {}).get("available", True):
            warnings.append(f"Branch protection won't be applied: {oi['branch_protection']['why']}. The hook that blocks pushes to main still applies.")
        if not oi.get("secret_scanning", {}).get("available", True):
            warnings.append(f"GitHub secret scanning/push protection won't be applied: {oi['secret_scanning']['why']}. gitleaks still runs before each commit and in CI.")
    gh_calls = [
        f"gh repo create {repo} --{ans['visibility']} --source <local path> --push --description \"{ans['purpose'][:80]}\"",
        "gh api -X PUT repos/" + repo + "/branches/main/protection   (if available)",
        "gh api -X PATCH repos/" + repo + "   (secret scanning + push protection, if available)",
        f"gh repo edit {repo} --enable-wiki=false --enable-projects=false --add-topic flatmap-harness --add-topic {ans['stack']}",
    ]
    if ans["audience"] == "public":
        gh_calls.append(f"gh label create ... --repo {repo}   (phase, needs-review, blocked, good first issue)")
    out({
        "ok": True, "repo_url": f"https://github.com/{repo}", "local_path": str(Path(os.path.expanduser(ans["local_path"])).resolve()),
        "files": r["files"], "tree": tree(r["files"]), "gh_calls": gh_calls, "warnings": warnings,
    })


# ---------------------------------------------------------------------------
# verify (spec 8 step 5)
# ---------------------------------------------------------------------------


def cmd_verify(a) -> None:
    d = Path(a.dir).resolve()
    steps = []
    targets = ([] if a.skip_install else ["install"]) + ["lint", "typecheck", "test", "build"]
    ok = True
    for t in targets:
        code, text = run(["make", t], cwd=d, timeout=1200)
        steps.append({"step": f"make {t}", "ok": code == 0, "output": tail(text, 25)})
        if code != 0:
            ok = False
            break
    if ok and shutil.which("actionlint"):
        code, text = run(["actionlint"], cwd=d, timeout=120)
        steps.append({"step": "actionlint", "ok": code == 0, "output": tail(text, 25)})
        ok = ok and code == 0
    elif ok:
        steps.append({"step": "actionlint", "ok": True, "output": "skipped (actionlint not installed)"})
    if ok:
        log = d / "harness" / "build-log.md"
        if log.exists():
            lines = [f"- `{st['step']}`: passed" for st in steps if st["ok"] and not st["output"].startswith("skipped")]
            log.write_text(log.read_text().rstrip("\n") + "\n- Local checks at creation (" + now_iso() + "):\n" + "\n".join("  " + l for l in lines) + "\n")
    out({"ok": ok, "steps": steps})


# ---------------------------------------------------------------------------
# git init + first-commit secrets check (spec 8 step 6, 5.4a item 7)
# ---------------------------------------------------------------------------


def staged_secret_check(d: Path) -> dict:
    code, names = run(["git", "diff", "--cached", "--name-only"], cwd=d)
    hits = [{"file": n, "pattern": matches_secret(n)} for n in names.splitlines() if n and matches_secret(n)]
    gl_code, gl_out = run(["gitleaks", "protect", "--staged", "--redact", "--no-banner"], cwd=d, timeout=120)
    gitleaks = {"ran": gl_code != 127, "ok": gl_code == 0, "output": tail(gl_out, 15)}
    return {"ok": not hits and gitleaks["ok"], "pattern_hits": hits, "gitleaks": gitleaks}


def cmd_git_init(a) -> None:
    d = Path(a.dir).resolve()
    steps = []
    if not (d / ".git").exists():
        code, text = run(["git", "init", "-b", "main"], cwd=d)
        steps.append({"step": "git init -b main", "ok": code == 0, "output": text})
        if code:
            out({"ok": False, "steps": steps})
    code, text = run(["lefthook", "install"], cwd=d, timeout=60)
    steps.append({"step": "lefthook install", "ok": code == 0, "output": tail(text, 5)})
    if code:
        out({"ok": False, "steps": steps})
    run(["git", "add", "-A"], cwd=d)
    chk = staged_secret_check(d)
    steps.append({"step": "first-commit secrets check", "ok": chk["ok"], "detail": chk})
    if not chk["ok"]:
        out({"ok": False, "steps": steps, "error": "possible secret staged; nothing committed"})
    msg = f"Initial harness from flatmap-repo-forge v{PLUGIN_VERSION}"
    code, text = run(["git", "commit", "-m", msg], cwd=d, timeout=600)
    steps.append({"step": "initial commit", "ok": code == 0, "output": tail(text, 15)})
    out({"ok": code == 0, "steps": steps})


# ---------------------------------------------------------------------------
# GitHub: create + configure (spec 8 steps 7-8)
# ---------------------------------------------------------------------------


def cmd_create(a) -> None:
    ans = load_answers(a.answers)
    d = Path(a.dir).resolve()
    repo = f"{ans['owner']}/{ans['slug']}"
    code, _ = run(["gh", "repo", "view", repo, "--json", "name"], timeout=30)
    if code == 0:
        out({"ok": False, "error": f"{repo} was taken since the preview. Pick another name (change 4a)."})
    cmd = ["gh", "repo", "create", repo, f"--{ans['visibility']}", "--source", str(d), "--push",
           "--description", ans["purpose"][:350]]
    code, text = run(cmd, timeout=300)
    out({"ok": code == 0, "repo": repo, "url": f"https://github.com/{repo}", "output": tail(text, 10)})


def gh_api(args: list[str], body: dict | None = None) -> tuple[int, str]:
    cmd = ["gh", "api"] + args
    if body is None:
        return run(cmd, timeout=60)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(body, f)
        fname = f.name
    try:
        return run(cmd + ["--input", fname], timeout=60)
    finally:
        os.unlink(fname)


def cmd_github_setup(a) -> None:
    ans = load_answers(a.answers)
    repo = f"{ans['owner']}/{ans['slug']}"
    oi = owner_info(ans["owner"])
    results = []

    bp_ok, bp_why = protection_available(ans["visibility"], oi["plan"])
    if bp_ok:
        reviewers = 1 if ans["audience"] in ("team", "client", "public") else 0
        body = {
            "required_status_checks": {"strict": True, "contexts": ["checks", "secrets"]},
            "enforce_admins": False,
            "required_pull_request_reviews": {"required_approving_review_count": reviewers, "dismiss_stale_reviews": True},
            "restrictions": None,
            "allow_force_pushes": False,
            "allow_deletions": False,
        }
        code, text = gh_api(["-X", "PUT", f"repos/{repo}/branches/main/protection"], body)
        results.append({"step": "branch protection", "ok": code == 0, "applied": code == 0,
                        "detail": f"require PR ({reviewers} approvals), checks 'checks' + 'secrets', no force-push; admins can bypass" if code == 0 else tail(text, 5)})
    else:
        results.append({"step": "branch protection", "ok": True, "applied": False, "detail": f"not applied (plan limit): {bp_why}"})

    if ans["visibility"] == "public":
        body = {"security_and_analysis": {"secret_scanning": {"status": "enabled"},
                                          "secret_scanning_push_protection": {"status": "enabled"}}}
        code, text = gh_api(["-X", "PATCH", f"repos/{repo}"], body)
        results.append({"step": "secret scanning + push protection", "ok": code == 0, "applied": code == 0,
                        "detail": "enabled" if code == 0 else tail(text, 5)})
    else:
        results.append({"step": "secret scanning + push protection", "ok": True, "applied": False,
                        "detail": "not applied (plan limit): private repos need a paid GitHub add-on"})

    code, text = run(["gh", "repo", "edit", repo, "--enable-wiki=false", "--enable-projects=false",
                      "--add-topic", "flatmap-harness", "--add-topic", ans["stack"]], timeout=60)
    results.append({"step": "repo settings (wiki/projects off, topics)", "ok": code == 0, "applied": code == 0, "detail": tail(text, 3)})

    if ans["audience"] != "solo":
        labels = [("phase", "1d76db", "A harness phase"), ("needs-review", "fbca04", "Waiting for review"),
                  ("blocked", "b60205", "Blocked on a decision or dependency")]
        if ans["audience"] == "public":
            labels.append(("good first issue", "7057ff", "Good for newcomers"))
        bad = []
        for name, color, desc in labels:
            code, text = run(["gh", "label", "create", name, "--repo", repo, "--color", color, "--description", desc, "--force"], timeout=60)
            if code:
                bad.append(f"{name}: {tail(text, 1)}")
        results.append({"step": "labels", "ok": not bad, "applied": not bad, "detail": "; ".join(bad) or ", ".join(l[0] for l in labels)})

    out({"ok": all(r["ok"] for r in results), "results": results})


# ---------------------------------------------------------------------------
# check the agent workflow (spec 8 step 9)
# ---------------------------------------------------------------------------

AGENT_TOOLS = {
    "planner": {"Read", "Grep", "Glob", "Write", "Edit"},
    "tester": {"Read", "Grep", "Glob", "Bash", "Write", "Edit"},
    "builder": {"Read", "Grep", "Glob", "Bash", "Write", "Edit"},
    "reviewer": {"Read", "Grep", "Glob"},
    "doc": {"Read", "Grep", "Glob", "Bash", "Write", "Edit"},
}


def frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    fm = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def run_hook(d: Path, sub: str, payload: dict) -> tuple[int, str]:
    p = subprocess.run(["python3", str(d / ".claude/hooks/harness.py"), sub], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=d, env={**os.environ, "CLAUDE_PROJECT_DIR": str(d)}, timeout=60)
    return p.returncode, (p.stdout + p.stderr).strip()


def cmd_check_workflow(a) -> None:
    d = Path(a.dir).resolve()
    checks = []
    for name, allowed in AGENT_TOOLS.items():
        f = d / ".claude" / "agents" / f"{name}.md"
        if not f.exists():
            checks.append({"check": f"agent {name}", "ok": False, "detail": "missing"})
            continue
        fm = frontmatter(f)
        tools = {t.strip() for t in fm.get("tools", "").split(",") if t.strip()}
        ok = fm.get("name") == name and bool(fm.get("description")) and tools and tools <= allowed
        checks.append({"check": f"agent {name}", "ok": bool(ok), "detail": f"tools: {', '.join(sorted(tools))}"})
    try:
        settings = json.loads((d / ".claude" / "settings.json").read_text())
        events = set(settings.get("hooks", {}))
        need = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}
        checks.append({"check": "hooks registered", "ok": need <= events, "detail": ", ".join(sorted(events))})
    except Exception as e:  # noqa: BLE001
        checks.append({"check": "settings.json parses", "ok": False, "detail": str(e)})
    for skill in ("ship", "workflow", "docs"):
        f = d / ".claude" / "skills" / skill / "SKILL.md"
        fm = frontmatter(f) if f.exists() else {}
        checks.append({"check": f"/{skill} skill", "ok": fm.get("name") == skill and bool(fm.get("description")), "detail": str(f.relative_to(d)) if f.exists() else "missing"})
    code, text = run_hook(d, "session-start", {"hook_event_name": "SessionStart", "source": "startup"})
    state = json.loads((d / ".harness" / "state.json").read_text())
    want = "waiting for your approval" if state["mode"] == "multi-phase" else "first task"
    checks.append({"check": "SessionStart status", "ok": code == 0 and want in text, "detail": tail(text, 3)})
    code, text = run_hook(d, "pre-bash", {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
    checks.append({"check": "push to main blocked", "ok": code == 2, "detail": tail(text, 2)})
    code, text = run_hook(d, "pre-bash", {"tool_name": "Bash", "tool_input": {"command": "git push -u origin phase/01-x"}})
    checks.append({"check": "push to a branch allowed", "ok": code == 0, "detail": tail(text, 2) or "allowed"})
    code, text = run_hook(d, "pre-agent", {"tool_name": "Agent", "tool_input": {"subagent_type": "doc"}})
    checks.append({"check": "Doc waits for a green light", "ok": code == 2, "detail": tail(text, 2)})
    docs = json.loads((d / ".harness" / "docs.json").read_text()) if (d / ".harness" / "docs.json").exists() else None
    checks.append({"check": "docs set up", "ok": bool(docs is not None and (d / "docs" / "guide" / "README.md").exists()
                                                      and (not docs.get("wiki") or (d / "wiki" / "Home.md").exists())),
                   "detail": f"wiki {'on' if docs and docs.get('wiki') else 'off'}"})
    if state["mode"] == "multi-phase":
        pf = d / "harness" / "phases" / f"{state['phase']}.md"
        checks.append({"check": "phase 01 drafted, awaiting approval", "ok": pf.exists() and state["step"] == "awaiting_phase_approval", "detail": str(pf.relative_to(d))})
    out({"ok": all(c["ok"] for c in checks), "checks": checks})


def cmd_brain(a) -> None:
    d = Path(a.dir).resolve()
    code, text = run_hook(d, "brain-sync", {})
    try:
        res = json.loads(text)
    except Exception:  # noqa: BLE001
        res = {"ok": code == 0, "output": text}
    out(res)


# ---------------------------------------------------------------------------
# dry run (spec 8: steps 1-5 into a temp dir, no GitHub writes)
# ---------------------------------------------------------------------------


def cmd_dry_run(a) -> None:
    ans = load_answers(a.answers)
    dest = Path(a.out).resolve() if a.out else Path(tempfile.mkdtemp(prefix="forge-dry-")) / ans.get("slug", "project")
    ans = {**ans, "local_path": str(dest)}
    if (ans.get("brain") or {}).get("enabled") and not a.keep_brain:
        ans["brain"] = {"enabled": False}
    r = render_to(ans, dest)
    if not r["ok"]:
        out({"ok": False, "render": r})
    result = {"ok": True, "path": str(dest), "render": {"ok": True, "files": len(r["files"])}}
    if not a.skip_verify:
        p = subprocess.run([sys.executable, __file__, "verify", str(dest)] + (["--skip-install"] if a.skip_install else []),
                           capture_output=True, text=True)
        v = json.loads(p.stdout)
        result["verify"] = v
        result["ok"] = v["ok"]
    p = subprocess.run([sys.executable, __file__, "check-workflow", str(dest)], capture_output=True, text=True)
    cw = json.loads(p.stdout)
    result["check_workflow"] = cw
    result["ok"] = result["ok"] and cw["ok"]
    out(result)


# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(prog="forge.py", description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("version"); p.set_defaults(fn=lambda a: out({"ok": True, "version": PLUGIN_VERSION}))
    p = sp.add_parser("slug"); p.add_argument("name"); p.set_defaults(fn=cmd_slug)
    p = sp.add_parser("preflight-tools"); p.add_argument("--stack", choices=list(STACKS)); p.set_defaults(fn=cmd_preflight_tools)
    p = sp.add_parser("preflight-name"); p.add_argument("repo"); p.add_argument("--visibility", choices=["private", "public"]); p.set_defaults(fn=cmd_preflight_name)
    p = sp.add_parser("preflight-path"); p.add_argument("path"); p.set_defaults(fn=cmd_preflight_path)
    p = sp.add_parser("history-get"); p.add_argument("--data-dir"); p.set_defaults(fn=cmd_history_get)
    p = sp.add_parser("history-record"); p.add_argument("answers"); p.add_argument("--data-dir"); p.set_defaults(fn=cmd_history_record)
    p = sp.add_parser("validate"); p.add_argument("answers")
    p.set_defaults(fn=lambda a: out({"ok": not validate(load_answers(a.answers)), "errors": validate(load_answers(a.answers))}))
    p = sp.add_parser("plan"); p.add_argument("answers"); p.add_argument("--owner-info", help="JSON from preflight-name"); p.set_defaults(fn=cmd_plan)
    p = sp.add_parser("render"); p.add_argument("answers"); p.add_argument("--out"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_render)
    p = sp.add_parser("verify"); p.add_argument("dir"); p.add_argument("--skip-install", action="store_true"); p.set_defaults(fn=cmd_verify)
    p = sp.add_parser("git-init"); p.add_argument("dir"); p.set_defaults(fn=cmd_git_init)
    p = sp.add_parser("create"); p.add_argument("answers"); p.add_argument("dir"); p.set_defaults(fn=cmd_create)
    p = sp.add_parser("github-setup"); p.add_argument("answers"); p.set_defaults(fn=cmd_github_setup)
    p = sp.add_parser("check-workflow"); p.add_argument("dir"); p.set_defaults(fn=cmd_check_workflow)
    p = sp.add_parser("brain"); p.add_argument("dir"); p.set_defaults(fn=cmd_brain)
    p = sp.add_parser("dry-run"); p.add_argument("answers"); p.add_argument("--out"); p.add_argument("--skip-install", action="store_true")
    p.add_argument("--skip-verify", action="store_true"); p.add_argument("--keep-brain", action="store_true"); p.set_defaults(fn=cmd_dry_run)

    a = ap.parse_args()
    try:
        a.fn(a)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        out({"ok": False, "error": f"{type(e).__name__}: {e}"}, 1)


if __name__ == "__main__":
    main()
