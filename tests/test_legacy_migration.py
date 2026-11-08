"""Legacy blueprint continuity checks, using synthetic Markdown only."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE / "skills/memory-l/scripts/memory.py"


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="memory-l-legacy-", dir=os.environ.get("MEMORY_L_TEST_DIR"))
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.source = self.base / "old-workspace/.claude-memory"
        self.source.mkdir(parents=True)
        self.root = self.base / "new-workspace"
        self.mapping = {"MEMORY.md": "MEMORY.md", "SEED.md": "identity/original-seed.md",
                        "PROFILE.md": "personality.md", "USER.md": "owner.md",
                        "TIMELINE.md": "growth.md", "SOUL.md": "calibration.md", "SELF-NOTES.md": "journal/days.md"}
        self.originals = {path: ("# Original " + role + "\r\nA prior jointly chosen understanding. zzlegacy71942\r\n").encode()
                          for role, path in self.mapping.items()}
        self.originals["identity/original-seed.md"] = b"\xef\xbb\xbf" + self.originals["identity/original-seed.md"]
        self.originals["refs/governance.md"] = b"# Existing governance\r\nKeep the original decisions.\r\n"
        self.originals["continuity/new.md"] = b"# Additional formal memory\r\nzzextra71943\r\n"
        self.originals["ports/raw.md"] = b"# Unselected port source\r\nzzunselected71944\r\n"
        for name, raw in self.originals.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (self.source.parent / "AGENTS.md").write_bytes(b"Read .claude-memory/MEMORY.md\r\n")
        (self.source.parent / "CLAUDE.md").write_bytes(b"@AGENTS.md\r\n")
        self.recipe = {"source_root": str(self.source), "name": "DemoAgent", "owner": "ExampleOwner",
                       "core_files": self.mapping, "formal_files": ["refs/governance.md", "continuity/new.md"],
                       "entry_files": {name: str(self.source.parent / name) for name in ("AGENTS.md", "CLAUDE.md")},
                       "exclude": {"ports/": "Unselected synthetic port sources stay at their source"}}

    def cli(self, *args, root=None, script=None, data=None, ok=True):
        result = subprocess.run([sys.executable, "-S", str(script or SCRIPT), "--workspace", str(root or self.root), *args],
            input=json.dumps(data) if data is not None else None, capture_output=True, encoding="utf-8", timeout=60,
            env={**os.environ, "PYTHONUTF8": "1"})
        if not ok:
            self.assertNotEqual(result.returncode, 0)
            return result
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def plan(self, suffix=""):
        recipe = self.base / ("recipe" + suffix + ".json")
        output = self.base / ("plan" + suffix + ".json")
        recipe.write_text(json.dumps(self.recipe), encoding="utf-8")
        status = self.cli("migrate-plan", "--input", str(recipe), "--output", str(output))
        return output, status

    def migrate(self):
        path, result = self.plan()
        self.assertTrue(result["ready_to_apply"])
        self.assertFalse(self.root.exists())
        self.cli("migrate-apply", "--plan", str(path))
        return path

    def git(self, *args, root=None):
        return subprocess.run(["git", "-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgSign=false", "-c", "core.autocrlf=true", "-c", "core.hooksPath=" + str(self.base / "no-hooks"),
            *args], cwd=root or self.root, capture_output=True, check=True, timeout=60)

    def test_original_paths_bytes_rules_and_recall_are_carried_without_promotion(self):
        plan = self.migrate()
        verified = self.cli("migrate-verify")
        self.assertEqual(verified["new_internalization_decisions"], 0)
        self.assertFalse(verified["source_directory_required"])
        for name, raw in self.originals.items():
            self.assertEqual((self.source / name).read_bytes(), raw)
            if not name.startswith("ports/"):
                self.assertEqual((self.root / ".memory" / name).read_bytes(), raw)
        status = self.cli("status")
        self.assertTrue(status["identity_ready"] and status["loader_connected"] and status["migrated"])
        self.assertEqual(status["core_files"], self.mapping)
        self.assertFalse((self.root / ".memory/SEED.md").exists())
        seed = self.cli("core-file", "SEED.md")
        self.assertEqual(seed["path"], ".memory/identity/original-seed.md")
        self.assertEqual(seed["sha256"], hashlib.sha256(self.originals[self.mapping["SEED.md"]]).hexdigest())
        self.assertTrue(self.cli("search", "zzextra71943")["items"])
        self.assertEqual(self.cli("search", "zzunselected71944")["items"], [])
        self.assertEqual(self.cli("context", "--purpose", "profile")["total"], 0)
        self.assertIn("core_files", self.cli("core-file", "MIGRATION.md")["body"])
        self.assertEqual((self.root / ".memory/previous-entries/AGENTS.md").read_bytes(), (self.source.parent / "AGENTS.md").read_bytes())
        self.assertIn("Read .claude-memory/MEMORY.md", self.cli("core-file", "PREVIOUS-AGENTS.md")["body"])
        self.cli("migrate-apply", "--plan", str(plan), ok=False)
        self.assertEqual((self.source.parent / "AGENTS.md").read_bytes(), b"Read .claude-memory/MEMORY.md\r\n")

    def test_unclassified_new_memory_blocks_switch_and_is_visible(self):
        (self.source / "another-memory.md").write_bytes(b"# Important additional memory\n")
        path, status = self.plan()
        self.assertFalse(status["ready_to_apply"])
        self.assertEqual(status["unclassified"], ["another-memory.md"])
        self.cli("migrate-apply", "--plan", str(path), ok=False)
        self.assertFalse(self.root.exists())

    def test_changed_source_inventory_or_plan_requires_a_fresh_plan(self):
        path, _ = self.plan()
        (self.source / "growth.md").write_bytes(b"# New source revision\n")
        self.cli("migrate-apply", "--plan", str(path), ok=False)
        self.assertFalse(self.root.exists())
        (self.source / "growth.md").write_bytes(self.originals["growth.md"])
        entry = self.source.parent / "AGENTS.md"
        entry.write_bytes(b"Changed original loader\n")
        self.cli("migrate-apply", "--plan", str(path), ok=False)
        self.assertFalse(self.root.exists())
        entry.write_bytes(b"Read .claude-memory/MEMORY.md\r\n")
        plan = json.loads(path.read_text())
        plan["files"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(plan), encoding="utf-8")
        self.cli("migrate-apply", "--plan", str(path), ok=False)
        self.assertFalse(self.root.exists())

    def test_existing_workspace_and_old_loader_are_never_overwritten(self):
        path, _ = self.plan()
        self.root.mkdir()
        (self.root / "important.md").write_bytes(b"Preserve this unrelated file\n")
        self.cli("migrate-apply", "--plan", str(path), ok=False)
        self.assertEqual((self.root / "important.md").read_bytes(), b"Preserve this unrelated file\n")
        self.cli("init", "--name", "DemoAgent", "--owner", "ExampleOwner", root=self.source.parent, ok=False)
        self.assertFalse((self.source.parent / ".memory").exists())

    def test_unsafe_paths_record_formats_and_credentials_require_review(self):
        for bad in ("../outside.md", "records/diary/one.md", "KIT-INTEGRATION.md"):
            with self.subTest(bad=bad):
                self.recipe["formal_files"] = [bad]
                recipe = self.base / "bad.json"
                recipe.write_text(json.dumps(self.recipe), encoding="utf-8")
                self.cli("migrate-plan", "--input", str(recipe), "--output", str(self.base / "bad-plan.json"), ok=False)
        self.recipe["formal_files"] = ["refs/governance.md", "continuity/new.md"]
        for raw in (b"<!-- companion-memory v1 -->\n```json\n{}\n```\n", ("sk-" + "a" * 32).encode()):
            (self.source / "growth.md").write_bytes(raw)
            recipe = self.base / "bad.json"
            recipe.write_text(json.dumps(self.recipe), encoding="utf-8")
            self.cli("migrate-plan", "--input", str(recipe), "--output", str(self.base / "bad-plan.json"), ok=False)

    def test_git_clone_keeps_mapping_and_publication_targets_original_diary(self):
        self.migrate()
        self.git("init")
        self.cli("stage")
        self.cli("check", "--git-index")
        self.git("commit", "-m", "Synthetic legacy migration")
        clone = self.base / "clone"
        self.git("clone", "--no-local", str(self.root), str(clone))
        installed = clone / ".memory-tools/memory.py"
        self.cli("migrate-verify", root=clone, script=installed)
        self.cli("check", "--git-ref", "HEAD", root=clone, script=installed)
        self.assertTrue(self.cli("search", "zzextra71943", root=clone, script=installed)["items"])
        record = self.cli("save", "--input", "-", data={"kind": "diary", "body": "New diary after continuity",
            "operation_id": "after-migration"}, root=clone, script=installed)
        state = self.cli("target-state", "diary", root=clone, script=installed)
        self.assertEqual(Path(state["path"]), clone / ".memory/journal/days.md")
        self.cli("publish", "--input", "-", root=clone, script=installed, data={"id": record["id"],
            "destination": "diary", "operation_id": "publish-after-migration", "expected_revision": record["revision"],
            "expected_target_revision": state["revision"], "reason": "Synthetic continuation", "evidence": ["synthetic"]})
        self.assertTrue((clone / ".memory/journal/days.md").read_bytes().startswith(self.originals["journal/days.md"]))
        self.assertFalse((clone / ".memory/SELF-NOTES.md").exists())

    def test_source_change_during_copy_does_not_leave_a_partial_target(self):
        plan, _ = self.plan()
        code = '''import os, sys
from pathlib import Path
os.environ["MEMORY_L_WORKSPACE"] = sys.argv[2]
sys.path.insert(0, sys.argv[1])
import kit, legacy_migration
original = kit.initialize
def changed(*args, **kwargs):
    result = original(*args, **kwargs)
    Path(sys.argv[4]).write_bytes(b"Changed concurrently")
    return result
kit.initialize = changed
try:
    legacy_migration.apply(sys.argv[3])
except ValueError:
    print("stopped")
else:
    raise AssertionError("A changed source was accepted")
'''
        done = subprocess.run([sys.executable, "-S", "-c", code, str(SCRIPT.parent), str(self.root), str(plan),
            str(self.source / "growth.md")], capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(self.root.exists())
        self.assertEqual(list(self.base.glob(".memory-l-migrate-*")), [])

    def test_custom_entry_filename_remains_the_actual_loader_target(self):
        raw = (self.source / "MEMORY.md").read_bytes()
        (self.source / "MEMORY.md").unlink()
        (self.source / "original-entry.md").write_bytes(raw)
        self.recipe["core_files"]["MEMORY.md"] = "original-entry.md"
        self.migrate()
        status = self.cli("status")
        self.assertTrue(status["loader_connected"])
        self.assertIn(".memory/original-entry.md", (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(self.cli("core-file", "MEMORY.md")["path"], ".memory/original-entry.md")

    def test_mcp_reads_original_core_mapping(self):
        try:
            import mcp
        except ImportError:
            self.skipTest("Optional MCP SDK is not installed")
        self.migrate()
        async def probe():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(command=sys.executable,
                args=[str(self.root / ".memory-tools/server.py"), "--workspace", str(self.root)],
                env={**os.environ, "PYTHONUTF8": "1"})
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    result = await client.call_tool("memory_l_core_file", {"name": "SEED.md"})
                    self.assertFalse(result.isError)
                    self.assertEqual(result.structuredContent["path"], ".memory/identity/original-seed.md")
                    guide = await client.call_tool("memory_l_core_file", {"name": "KIT-INTEGRATION.md"})
                    self.assertFalse(guide.isError)
                    old = await client.call_tool("memory_l_core_file", {"name": "PREVIOUS-AGENTS.md"})
                    self.assertFalse(old.isError)
        asyncio.run(probe())
