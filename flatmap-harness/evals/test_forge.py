#!/usr/bin/env python3
"""Deterministic tests for flatmap-repo-forge (spec section 11).

    python3 evals/test_forge.py            # fast: render, hooks, state, secrets, brain, scope, history
    FORGE_FULL=1 python3 evals/test_forge.py   # also installs deps and runs lint/typecheck/test/build (network)

No GitHub calls are made. Standard library only.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
FORGE = PLUGIN / "skills" / "flatmap-repo-forge" / "scripts" / "forge.py"
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(FORGE.parent))
import forge  # noqa: E402

BASE = json.loads((FIXTURES / "ts-solo-multi.json").read_text())


def answers(stack="typescript", audience="solo", mode="multi-phase", **kw) -> dict:
    a = json.loads(json.dumps(BASE))
    a.update(stack=stack, audience=audience, mode=mode,
             visibility="public" if audience == "public" else "private", **kw)
    if mode == "single-pass":
        a.pop("phase1", None)
    return a


def render(ans: dict, dest: Path) -> dict:
    return forge.render_to(ans, dest)


def sh(cmd, cwd, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, **kw)


def hook(repo: Path, sub: str, payload: dict | None = None, args: list[str] | None = None):
    return subprocess.run(["python3", str(repo / ".claude/hooks/harness.py"), sub] + (args or []),
                          input=json.dumps(payload or {}), capture_output=True, text=True, cwd=repo,
                          env={**os.environ, "CLAUDE_PROJECT_DIR": str(repo)})


def git_repo(path: Path) -> None:
    sh(["git", "init", "-q", "-b", "main"], path)
    sh(["git", "config", "user.name", "Test User"], path)
    sh(["git", "config", "user.email", "test@example.invalid"], path)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="forge-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------


class TestSlugAndValidate(Base):
    def test_slug_rule(self):
        cases = {"Acme Client Dashboard": "acme-client-dashboard", "  my__app  v2 ": "my-app-v2",
                 "Tidy-Names!!": "tidy-names", "--x..": "x", "a.b c": "a.b-c"}
        for name, want in cases.items():
            self.assertEqual(forge.slugify(name), want, name)

    def test_validate_rejects_unsupported(self):
        errs = forge.validate(answers(stack="go"))
        self.assertTrue(any("stack" in e for e in errs))
        errs = forge.validate(answers(audience="client"))
        self.assertTrue(any("audience" in e for e in errs))
        errs = forge.validate(answers(retry_limit=9))
        self.assertTrue(any("retry_limit" in e for e in errs))
        errs = forge.validate({**answers(), "ui": True})
        self.assertTrue(any("UI" in e for e in errs))

    def test_validate_multi_phase_needs_phase1(self):
        a = answers()
        a.pop("phase1")
        self.assertTrue(any("phase1" in e for e in forge.validate(a)))


class TestRenderMatrix(Base):
    """{TS, Python} x {solo, public} x {multi-phase, single-pass}"""

    def test_matrix(self):
        for stack, audience, mode in itertools.product(["typescript", "python"], ["solo", "public"],
                                                       ["multi-phase", "single-pass"]):
            with self.subTest(stack=stack, audience=audience, mode=mode):
                dest = self.tmp / f"{stack}-{audience}-{mode}"
                r = render(answers(stack, audience, mode), dest)
                self.assertTrue(r["ok"], r)
                files = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}

                for f in ["AGENTS.md", "CLAUDE.md", "GOALS.md", "README.md", "Makefile", ".gitignore", ".env.example",
                          "lefthook.yml", ".editorconfig", ".github/workflows/ci.yml", ".github/dependabot.yml",
                          ".github/pull_request_template.md", "harness/WORKFLOW.md", "harness/build-log.md",
                          "docs/decisions/0001-record-architecture-decisions.md", ".claude/settings.json",
                          ".claude/hooks/harness.py", ".claude/skills/ship/SKILL.md", ".claude/skills/workflow/SKILL.md", ".claude/skills/docs/SKILL.md",
                          "docs/guide/README.md", "docs/guide/runbook.md", "docs/guide/changelog.md",
                          "docs/guide/features/README.md", ".harness/docs.json",
                          ".harness/config.json", ".harness/state.json"] + [f".claude/agents/{n}.md" for n in forge.AGENT_TOOLS]:
                    self.assertIn(f, files)

                multi = {"PLANS.md", "harness/phases/_template.md", "harness/phases/01-sales-data-loader.md"}
                if mode == "multi-phase":
                    self.assertTrue(multi <= files, multi - files)
                else:
                    self.assertFalse(multi & files)
                    self.assertIn("harness/task.md", files)

                public = {"LICENSE", "CONTRIBUTING.md", "SECURITY.md", ".github/CODEOWNERS", ".github/workflows/codeql.yml"}
                if audience == "public":
                    self.assertTrue(public <= files, public - files)
                else:
                    self.assertFalse(public & files)

                stack_files = {"package.json", "biome.json", "tsconfig.json"} if stack == "typescript" else {"pyproject.toml", ".python-version"}
                self.assertTrue(stack_files <= files)

                # no unrendered tokens, no Finder icon files
                for f in files:
                    text = (dest / f).read_text(errors="ignore")
                    self.assertIsNone(forge.TOKEN_RE.search(text), f"unrendered token in {f}")
                    self.assertNotIn("Icon\r", f)

                # markers balanced; stripped in single-pass
                agents = (dest / "AGENTS.md").read_text()
                opens, closes = agents.count("<!-- forge:multi-phase -->"), agents.count("<!-- /forge:multi-phase -->")
                self.assertEqual(opens, closes)
                self.assertEqual(opens > 0, mode == "multi-phase")
                self.assertEqual("PLANS.md" in agents, mode == "multi-phase")

                # checksums recorded and correct
                cfg = json.loads((dest / ".harness/config.json").read_text())
                self.assertEqual(cfg["mode"], mode)
                self.assertEqual(cfg["plugin_version"], forge.PLUGIN_VERSION)
                for rel, digest in cfg["files"].items():
                    self.assertEqual(forge.sha256(dest / rel), digest, rel)

                # json and python files parse
                json.loads((dest / ".claude/settings.json").read_text())
                compile((dest / ".claude/hooks/harness.py").read_text(), "harness.py", "exec")
                if stack == "typescript":
                    json.loads((dest / "package.json").read_text())

                # tester agent got the stack's test locations
                self.assertIn(forge.STACKS[stack]["test_globs"][0], (dest / ".claude/agents/tester.md").read_text())

    def test_deploy_placeholder(self):
        dest = self.tmp / "d"
        render(answers(deploy_target="fly"), dest)
        self.assertTrue((dest / ".github/workflows/deploy.yml").exists())
        self.assertIn("FLY_API_TOKEN", (dest / "README.md").read_text())
        dest2 = self.tmp / "n"
        render(answers(deploy_target="none"), dest2)
        self.assertFalse((dest2 / ".github/workflows/deploy.yml").exists())
        self.assertNotIn("## Deploy", (dest2 / "README.md").read_text())

    def test_purpose_with_quotes_is_valid_toml_and_json(self):
        dest = self.tmp / "q"
        r = render(answers("python", "public", "single-pass", purpose='Renames "date-place" files\\ fast.'), dest)
        self.assertTrue(r["ok"], r)
        line = [l for l in (dest / "pyproject.toml").read_text().splitlines() if l.startswith("description")][0]
        self.assertEqual(json.loads(line.split("=", 1)[1].strip()), 'Renames "date-place" files\\ fast.')

    def test_check_workflow(self):
        for mode in ("multi-phase", "single-pass"):
            with self.subTest(mode=mode):
                dest = self.tmp / mode
                render(answers(mode=mode), dest)
                git_repo(dest)
                p = sh([sys.executable, str(FORGE), "check-workflow", str(dest)], dest)
                res = json.loads(p.stdout)
                self.assertTrue(res["ok"], json.dumps(res, indent=2))


# ---------------------------------------------------------------------------


class TestPushToMainHook(Base):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "r"
        render(answers(), self.repo)
        git_repo(self.repo)
        sh(["git", "commit", "-q", "--allow-empty", "-m", "init"], self.repo)

    def pre_bash(self, cmd):
        return hook(self.repo, "pre-bash", {"tool_name": "Bash", "tool_input": {"command": cmd}}).returncode

    def test_blocks_main(self):
        for cmd in ["git push origin main", "git push", "git push -f origin main", "git push origin HEAD:main",
                    "git push origin +main", "git push origin feature:refs/heads/main", "git push --all origin",
                    "make test && git push origin main", "git -C . push origin main", "git push origin master"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.pre_bash(cmd), 2, cmd)

    def test_allows_branches(self):
        sh(["git", "switch", "-q", "-c", "phase/01-x"], self.repo)
        for cmd in ["git push -u origin phase/01-x", "git push", "git push origin HEAD", "git status", "echo main",
                    "git push origin main-docs"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.pre_bash(cmd), 0, cmd)

    def test_blocks_direct_state_edits(self):
        self.assertEqual(self.pre_bash("echo '{}' > .harness/state.json"), 2)
        self.assertEqual(self.pre_bash("sed -i '' s/a/b/ .harness/state.json"), 2)
        self.assertEqual(self.pre_bash("cat .harness/state.json"), 0)
        self.assertEqual(self.pre_bash("python3 .claude/hooks/harness.py advance writing_test_plan"), 0)
        r = hook(self.repo, "pre-write", {"tool_name": "Write", "tool_input": {"file_path": str(self.repo / ".harness/state.json")}})
        self.assertEqual(r.returncode, 2)
        r = hook(self.repo, "pre-write", {"tool_name": "Write", "tool_input": {"file_path": str(self.repo / "src/x.ts")}})
        self.assertEqual(r.returncode, 0)


# ---------------------------------------------------------------------------


class StateMachine(Base):
    mode = "multi-phase"

    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "r"
        render(answers(mode=self.mode, retry_limit=2), self.repo)
        git_repo(self.repo)
        sh(["git", "add", "-A"], self.repo)
        sh(["git", "commit", "-q", "-m", "init"], self.repo)

    def user(self):
        time.sleep(0.01)
        self.assertEqual(hook(self.repo, "user-prompt", {"prompt": "yes"}).returncode, 0)
        time.sleep(0.01)

    def adv(self, *args):
        return hook(self.repo, "advance", args=list(args))

    def ok(self, *args):
        r = self.adv(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def refused(self, *args):
        r = self.adv(*args)
        self.assertNotEqual(r.returncode, 0, f"expected refusal: {args}\n{r.stdout}")
        self.assertIn("REFUSED", r.stdout)
        return r

    def state(self):
        return json.loads((self.repo / ".harness/state.json").read_text())

    def agent(self, name):
        return hook(self.repo, "pre-agent", {"tool_name": "Agent", "tool_input": {"subagent_type": name}}).returncode

    def stop_blocks(self):
        r = hook(self.repo, "stop", {"stop_hook_active": False})
        return r.stdout.strip() and json.loads(r.stdout).get("decision") == "block"

    def commit_tests(self):
        (self.repo / "src").mkdir(exist_ok=True)
        (self.repo / "src" / "loader.test.ts").write_text("// approved test\n")
        sh(["git", "add", "-A"], self.repo)
        sh(["git", "commit", "-q", "-m", "tests"], self.repo)


class TestMultiPhaseStateMachine(StateMachine):
    def test_full_loop_with_gates(self):
        # approval steps refuse to move until the user has answered
        self.refused("writing_test_plan")
        self.assertEqual(self.agent("planner"), 0)
        self.assertEqual(self.agent("builder"), 2)
        self.user()
        self.refused("building")  # not an allowed next step
        self.ok("writing_test_plan")
        self.assertEqual(self.agent("tester"), 0)
        self.assertEqual(self.agent("builder"), 2)
        self.assertEqual(self.agent("Explore"), 0)  # non-harness agents are never blocked
        self.assertTrue(self.stop_blocks())
        self.ok("awaiting_test_plan_approval")
        self.assertFalse(self.stop_blocks())
        self.refused("writing_tests")
        self.user()
        self.ok("writing_tests")
        self.ok("awaiting_test_approval")
        self.user()
        (self.repo / "src").mkdir(exist_ok=True)
        (self.repo / "src" / "loader.test.ts").write_text("// uncommitted test\n")
        self.refused("building")  # approved tests must be committed first
        self.commit_tests()
        self.ok("building")
        self.assertEqual(self.state()["run"], 1)
        self.assertEqual(self.agent("builder"), 0)
        self.assertEqual(self.agent("tester"), 2)
        self.ok("testing")
        self.assertEqual(self.agent("builder"), 2)  # builder can't act during testing
        self.refused("reviewing")  # needs --result pass
        self.ok("reviewing", "--result", "pass")
        self.assertEqual(self.agent("reviewer"), 0)
        self.ok("ready_to_ship", "--result", "pass")
        self.refused("awaiting_merge")  # needs --pr
        self.ok("awaiting_merge", "--pr", "7")
        self.assertEqual(self.state()["pr"], "7")
        # merged needs the PR to be merged (no gh here) or a user answer
        self.refused("merged")
        self.user()
        self.ok("merged")
        st = self.state()
        self.assertEqual(st["completed"][0]["id"], "01-sales-data-loader")
        # next phase only when the user says so, and only once it's drafted
        self.refused("awaiting_phase_approval", "--phase", "02-next")
        self.user()
        self.refused("awaiting_phase_approval", "--phase", "02-next")  # file doesn't exist yet
        (self.repo / "harness/phases/02-next.md").write_text("# Phase 02\n")
        self.ok("awaiting_phase_approval", "--phase", "02-next")
        self.assertEqual(self.state()["phase"], "02-next")
        self.assertEqual(self.state()["run"], 0)

    def go_to_testing(self):
        self.user(); self.ok("writing_test_plan"); self.ok("awaiting_test_plan_approval")
        self.user(); self.ok("writing_tests"); self.ok("awaiting_test_approval")
        self.user(); self.commit_tests(); self.ok("building"); self.ok("testing")

    def test_retry_limit_stops(self):
        self.go_to_testing()  # retry_limit = 2
        self.ok("building", "--result", "fail", "--note", "test x failed")
        self.assertEqual(self.state()["run"], 2)
        self.ok("testing")
        r = self.ok("building", "--result", "fail", "--note", "still failing")
        st = self.state()
        self.assertEqual(st["step"], "stopped_retry_limit", r.stdout)
        self.assertEqual(st["run"], 2)
        self.assertEqual(self.agent("builder"), 2)
        self.refused("building")  # waits for the user
        self.user()
        self.ok("building")
        self.assertEqual(self.state()["run"], 1)

    def test_ci_failure_counts_as_a_run(self):
        self.go_to_testing()
        self.ok("reviewing", "--result", "pass")
        self.ok("ready_to_ship", "--result", "pass")
        self.ok("awaiting_merge", "--pr", "3")
        self.ok("building", "--result", "fail", "--note", "CI red")  # no user answer needed for CI failures
        self.assertEqual(self.state()["run"], 2)

    def test_retry_limit_read_from_config(self):
        cfg_path = self.repo / ".harness/config.json"
        cfg = json.loads(cfg_path.read_text()); cfg["retry_limit"] = 1; cfg_path.write_text(json.dumps(cfg))
        self.go_to_testing()
        self.ok("building", "--result", "fail")
        self.assertEqual(self.state()["step"], "stopped_retry_limit")

    def test_session_start_reports_status(self):
        r = hook(self.repo, "session-start", {"source": "startup"})
        out = json.loads(r.stdout)
        self.assertIn("waiting for your approval", out["systemMessage"])
        self.assertIn("advance writing_test_plan", out["hookSpecificOutput"]["additionalContext"])

    def test_post_edit_flags_test_and_scope_changes(self):
        self.go_to_testing()
        self.ok("building", "--result", "fail")  # back in building, run 2
        r = hook(self.repo, "post-edit", {"tool_name": "Edit", "tool_input": {"file_path": str(self.repo / "src/loader.test.ts")}})
        self.assertIn("test file", json.loads(r.stdout)["reason"])
        r = hook(self.repo, "post-edit", {"tool_name": "Edit", "tool_input": {"file_path": str(self.repo / "README.md")}})
        self.assertIn("Files affected", json.loads(r.stdout)["reason"])
        r = hook(self.repo, "post-edit", {"tool_name": "Edit", "tool_input": {"file_path": str(self.repo / "src/sales/load.ts")}})
        self.assertEqual(r.stdout.strip(), "")


class TestSinglePassStateMachine(StateMachine):
    mode = "single-pass"

    def test_loop_order(self):
        self.assertIn("first task", json.loads(hook(self.repo, "session-start").stdout)["systemMessage"])
        self.user()
        self.refused("writing_test_plan")  # needs --task
        self.ok("writing_test_plan", "--task", "rename by date")
        self.ok("awaiting_test_plan_approval"); self.user()
        self.ok("writing_tests"); self.ok("awaiting_test_approval"); self.user()
        self.commit_tests()
        self.ok("building")
        self.refused("testing")  # single-pass reviews before testing
        self.ok("reviewing")
        self.ok("testing", "--result", "pass")
        self.refused("reviewing", "--result", "pass")
        self.ok("ready_to_ship", "--result", "pass")
        self.ok("awaiting_merge", "--pr", "1"); self.user(); self.ok("merged")
        self.user(); self.ok("idle")
        self.assertIn("next task", json.loads(hook(self.repo, "session-start").stdout)["systemMessage"])

    def test_rework_starts_at_building(self):
        self.user()
        self.ok("building", "--task", "fix the date parser")
        self.assertEqual(self.state()["run"], 1)


# ---------------------------------------------------------------------------


class TestSecrets(Base):
    def test_patterns_single_source(self):
        dest = self.tmp / "r"
        render(answers(), dest)
        gi = (dest / ".gitignore").read_text().splitlines()
        for p in forge.SECRET_PATTERNS + ["!.env.example"] + forge.PERSONAL_FILES:
            self.assertIn(p, gi)
        deny = json.loads((dest / ".claude/settings.json").read_text())["permissions"]["deny"]
        self.assertEqual(deny, forge.deny_rules())
        self.assertNotIn("Read(**/.env.example)", deny)
        for p in forge.SECRET_PATTERNS:
            if p != ".env.*":
                self.assertIn(f"Read(**/{p})", deny)

    def test_matcher(self):
        for path in [".env", "config/.env.production", "certs/server.pem", "id_rsa", "gcp-credentials.json",
                     "service-account-prod.json", "secrets.yaml", ".harness/config.local.json"]:
            self.assertIsNotNone(forge.matches_secret(path), path)
        for path in [".env.example", "src/env.ts", "README.md", "keys.md"]:
            self.assertIsNone(forge.matches_secret(path), path)

    def test_gitignore_keeps_secrets_out_and_example_in(self):
        dest = self.tmp / "r"
        render(answers(), dest)
        git_repo(dest)
        (dest / ".env").write_text("API_KEY=x\n")
        (dest / "server.key").write_text("k\n")
        sh(["git", "add", "-A"], dest)
        staged = sh(["git", "diff", "--cached", "--name-only"], dest).stdout.split()
        self.assertNotIn(".env", staged)
        self.assertNotIn("server.key", staged)
        self.assertIn(".env.example", staged)

    def test_first_commit_check_blocks_forced_secret(self):
        dest = self.tmp / "r"
        render(answers(), dest)
        git_repo(dest)
        (dest / ".env").write_text("API_KEY=x\n")
        sh(["git", "add", "-f", ".env"], dest)
        chk = forge.staged_secret_check(dest)
        self.assertFalse(chk["ok"])
        self.assertEqual(chk["pattern_hits"][0]["file"], ".env")

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks not installed")
    def test_gitleaks_blocks_key_in_source(self):
        dest = self.tmp / "r"
        render(answers(), dest)
        git_repo(dest)
        (dest / "src" / "config.ts").write_text('export const token = "ghp_' + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8" + '";\n')
        sh(["git", "add", "-A"], dest)
        chk = forge.staged_secret_check(dest)
        self.assertFalse(chk["gitleaks"]["ok"], chk)


# ---------------------------------------------------------------------------


class TestBrain(Base):
    def test_entry_high_level_only(self):
        brain = self.tmp / "brain"
        (brain / "wiki" / "projects").mkdir(parents=True)
        (brain / "wiki" / "index.md").write_text("# Index\n\n- [Other](projects/other.md)\n")
        (brain / "wiki" / "other.md").write_text("untouched\n")
        dest = self.tmp / "r"
        render(answers(brain={"enabled": True, "path": str(brain)}), dest)
        git_repo(dest)
        sh(["git", "add", "-A"], dest)
        sh(["git", "commit", "-q", "-m", "init"], dest)
        res = json.loads(hook(dest, "brain-sync").stdout)
        self.assertTrue(res["ok"], res)
        entry = brain / "wiki" / "projects" / "acme-client-dashboard.md"
        text = entry.read_text()
        for want in ["Acme Client Dashboard", "About:", "Contributors:** Test User", "Version:** 0.1.0",
                     "TypeScript app", "host: vercel", "repo created", "## Milestones"]:
            self.assertIn(want, text)
        body = "\n".join(l for l in text.splitlines() if not l.startswith("<!--"))
        for banned in ["src/", ".ts", "diff", "test@example.invalid", "build-log"]:
            self.assertNotIn(banned, body)
        idx = (brain / "wiki" / "index.md").read_text()
        self.assertEqual(idx.count("projects/acme-client-dashboard.md"), 1)
        hook(dest, "brain-sync")
        self.assertEqual((brain / "wiki" / "index.md").read_text().count("acme-client-dashboard.md"), 1)
        self.assertEqual((brain / "wiki" / "other.md").read_text(), "untouched\n")
        # personal files are gitignored
        for f in (".harness/config.local.json", ".claude/settings.local.json"):
            self.assertEqual(sh(["git", "check-ignore", f], dest).returncode, 0, f)

    def test_off_by_default_when_disabled(self):
        dest = self.tmp / "r"
        render(answers(brain={"enabled": False}), dest)
        self.assertFalse((dest / ".harness/config.local.json").exists())
        self.assertIn("off", json.loads(hook(dest, "brain-sync").stdout)["skipped"])


class TestScopeAndHistory(Base):
    def test_render_writes_only_inside_project(self):
        home = self.tmp / "home"
        home.mkdir()
        dest = self.tmp / "proj"
        p = subprocess.run([sys.executable, str(FORGE), "render", str(FIXTURES / "ts-solo-multi.json"), "--out", str(dest)],
                           capture_output=True, text=True, env={**os.environ, "HOME": str(home)})
        self.assertTrue(json.loads(p.stdout)["ok"], p.stdout)
        self.assertEqual(list(home.iterdir()), [])
        siblings = {x.name for x in self.tmp.iterdir()}
        self.assertEqual(siblings, {"home", "proj"})

    def test_history_shortens_from_run_three(self):
        dd = self.tmp / "data"
        f = self.tmp / "a.json"
        f.write_text(json.dumps(answers()))
        def get():
            return json.loads(sh([sys.executable, str(FORGE), "history-get", "--data-dir", str(dd)], self.tmp).stdout)
        def rec(path=f):
            sh([sys.executable, str(FORGE), "history-record", str(path), "--data-dir", str(dd)], self.tmp)
        self.assertFalse(get()["shorter_interview"])
        rec()
        self.assertFalse(get()["shorter_interview"])
        rec()
        g = get()
        self.assertTrue(g["shorter_interview"])
        self.assertEqual(g["this_run"], 3)
        self.assertEqual(g["skippable"]["owner"], "example-owner")
        self.assertEqual(g["skippable"]["retry_limit"], 3)
        # a habit that changed is asked again
        f2 = self.tmp / "b.json"
        f2.write_text(json.dumps(answers(retry_limit=4)))
        rec(f2)
        self.assertNotIn("retry_limit", get()["skippable"])
        self.assertIn("owner", get()["skippable"])
        self.assertNotIn("project_name", json.dumps(json.loads((dd / "history.json").read_text())))


@unittest.skipUnless(os.environ.get("FORGE_FULL"), "set FORGE_FULL=1 to install deps and run the scaffold's checks")
class TestFullDryRun(Base):
    def test_dry_runs(self):
        for fx in ("ts-solo-multi.json", "py-public-single.json"):
            with self.subTest(fixture=fx):
                dest = self.tmp / fx.split(".")[0]
                dest.parent.mkdir(exist_ok=True)
                p = subprocess.run([sys.executable, str(FORGE), "dry-run", str(FIXTURES / fx), "--out", str(dest)],
                                   capture_output=True, text=True, timeout=1800)
                res = json.loads(p.stdout)
                self.assertTrue(res["ok"], json.dumps(res, indent=2)[-3000:])


# ---------------------------------------------------------------------------


class TestDocs(StateMachine):
    """Doc, the writer: green light after a merge, gated otherwise, wiki opt-in."""

    def setUp(self):
        super().setUp()
        self.stub = self.tmp / "gh.json"
        created = json.loads((self.repo / ".harness/config.json").read_text())["created"]
        self.gh({"merged": [
            {"number": 1, "title": "Before setup", "headRefName": "x", "mergedAt": "2000-01-01T00:00:00Z"},
            {"number": 4, "title": "Sales loader", "headRefName": "phase/01-sales", "mergedAt": created},
            {"number": 5, "title": "Docs: sales", "headRefName": "docs/pr-3", "mergedAt": created},
            {"number": 6, "title": "Fix totals", "headRefName": "task/fix", "mergedAt": created},
        ], "open": [{"number": 7, "headRefName": "docs/pr-6"}]})

    def gh(self, data):
        self.stub.write_text(json.dumps(data))

    def docs(self, *args):
        r = subprocess.run(["python3", str(self.repo / ".claude/hooks/harness.py"), "docs", *args], capture_output=True, text=True,
                           cwd=self.repo, env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.repo), "HARNESS_GH_STUB": str(self.stub)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_no_green_light_blocks_doc(self):
        self.assertEqual(self.agent("doc"), 2)
        self.gh({"merged": [], "open": []})
        self.assertFalse(self.docs("check")["green_light"])
        self.assertEqual(self.agent("doc"), 2)

    def test_merged_pr_gives_green_light(self):
        d = self.docs("check")
        # #1 predates setup, #5 is a docs PR, #6 is already covered by the open docs PR #7
        self.assertEqual([p["pr"] for p in d["pending_prs"]], [4])
        self.assertEqual(d["branch"], "docs/pr-4")
        self.assertTrue(d["green_light"])
        self.assertEqual(self.agent("doc"), 0)

    def test_done_records_in_worktree_and_clears_queue(self):
        self.docs("check")
        wt = self.tmp / "wt"
        (wt / ".harness").mkdir(parents=True)
        (wt / ".harness/docs.json").write_text(json.dumps({"wiki": False, "documented": [2]}))
        r = self.docs("done", "--root", str(wt), "--prs", "4")
        self.assertEqual(json.loads((wt / ".harness/docs.json").read_text())["documented"], [2, 4])
        self.assertEqual(r["still_queued"], {"pending_prs": [], "jobs": []})
        self.assertEqual(self.agent("doc"), 2)

    def test_doc_never_runs_during_a_working_step(self):
        self.docs("check")
        self.user()
        self.ok("writing_test_plan")
        self.assertEqual(self.agent("doc"), 2)

    def test_requests_and_wiki_on(self):
        self.gh({"merged": [], "open": []})
        self.docs("check")
        self.assertEqual(self.docs("wiki", "on")["queued"], "wiki-setup")
        d = self.docs("status")
        self.assertEqual(d["jobs"], ["wiki-setup"])
        self.assertEqual(d["branch"], "docs/wiki-setup")
        self.assertEqual(self.agent("doc"), 0)
        wt = self.tmp / "wt"
        (wt / ".harness").mkdir(parents=True)
        self.docs("done", "--root", str(wt), "--job", "wiki-setup")
        self.assertTrue(json.loads((wt / ".harness/docs.json").read_text())["wiki"])
        self.docs("request", "explain the export settings")
        self.assertEqual(self.docs("status")["jobs"], ["explain the export settings"])

    def test_wiki_layer_follows_interview(self):
        for wiki in (True, False):
            with self.subTest(wiki=wiki):
                dest = self.tmp / f"w{wiki}"
                render(answers(docs_wiki=wiki), dest)
                self.assertEqual((dest / "wiki/Home.md").exists(), wiki)
                self.assertEqual(json.loads((dest / ".harness/docs.json").read_text())["wiki"], wiki)
                gi = (dest / ".gitignore").read_text()
                self.assertIn(".harness/worktrees/", gi)
                self.assertIn(".harness/.docs-queue.json", gi)
        self.assertIn("docs_wiki must be", " ".join(forge.validate(answers(docs_wiki="yes"))))


if __name__ == "__main__":
    unittest.main(verbosity=1)
