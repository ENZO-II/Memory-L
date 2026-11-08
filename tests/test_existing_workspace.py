"""Attach to an already inhabited project, keeping its one canonical memory."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import test_legacy_migration as fixtures

SCRIPT = fixtures.SCRIPT


class ExistingWorkspaceTests(unittest.TestCase):
    cli = fixtures.LegacyMigrationTests.cli
    git = fixtures.LegacyMigrationTests.git

    def setUp(self):
        fixture = fixtures.LegacyMigrationTests("test_mcp_reads_original_core_mapping")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.base, self.source = fixture.base, fixture.source
        self.root = self.source.parent
        self.recipe, self.mapping, self.originals = fixture.recipe, fixture.mapping, fixture.originals
        (self.root / "project.py").write_bytes(b"# Existing project\r\nvalue = 42\r\n")
        (self.root / ".gitignore").write_bytes(b"# Existing project exclusions\r\n*.tmp\r\n")
        (self.root / ".gitattributes").write_bytes(b"*.md text eol=lf\r\n")
        (self.root / ".memory-cache").mkdir()
        (self.root / ".memory-cache/foreign.cache").write_bytes(b"Keep this unrelated cache\n")
        self.root_before = {name: (self.root / name).read_bytes() for name in ("AGENTS.md", "CLAUDE.md", ".gitignore", ".gitattributes")}

    def plan(self):
        recipe = self.base / "attachment-input.json"
        plan = self.base / "attachment-plan.json"
        recipe.write_text(json.dumps(self.recipe), encoding="utf-8")
        status = self.cli("attach-plan", "--input", str(recipe), "--output", str(plan))
        return plan, status

    def attach(self):
        plan, status = self.plan()
        self.assertTrue(status["ready_to_apply"])
        result = self.cli("attach-apply", "--plan", str(plan))
        self.assertEqual(result["source_files_copied"], 0)
        return plan

    def test_existing_identity_and_project_stay_at_their_original_paths(self):
        plan = self.attach()
        for name, raw in self.originals.items():
            self.assertEqual((self.source / name).read_bytes(), raw)
        for name, raw in self.root_before.items():
            self.assertTrue((self.root / name).read_bytes().startswith(raw))
        self.assertEqual((self.root / "project.py").read_bytes(), b"# Existing project\r\nvalue = 42\r\n")
        self.assertEqual((self.root / ".memory-cache/foreign.cache").read_bytes(), b"Keep this unrelated cache\n")
        self.assertFalse((self.root / ".memory/SEED.md").exists())
        self.assertFalse((self.root / ".memory/journal/days.md").exists())
        state = self.cli("status")
        self.assertTrue(state["attached"] and state["identity_ready"] and state["loader_connected"])
        self.assertEqual(state["core_root"], ".claude-memory")
        self.assertEqual(self.cli("core-file", "SEED.md")["path"], ".claude-memory/identity/original-seed.md")
        self.assertIn("Read .claude-memory", self.cli("core-file", "AGENTS.md")["body"])
        self.assertEqual(self.cli("context", "--purpose", "profile")["total"], 0)
        self.assertTrue(self.cli("search", "zzextra71943")["items"])
        self.assertEqual(self.cli("search", "zzunselected71944")["items"], [])
        before = (self.root / "AGENTS.md").read_bytes()
        self.assertEqual(self.cli("attach-apply", "--plan", str(plan))["status"], "already_attached")
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), before)
        self.cli("init", "--name", "DemoAgent", "--owner", "ExampleOwner", ok=False)

    def test_publication_and_cache_fallback_use_the_live_original_diary(self):
        self.attach()
        record = self.cli("save", "--input", "-", data={"kind": "diary", "body": "New actual continuation zzattached804",
            "operation_id": "attached-diary"})
        state = self.cli("target-state", "diary")
        self.assertEqual(Path(state["path"]), self.source / "journal/days.md")
        self.cli("publish", "--input", "-", data={"id": record["id"], "destination": "diary", "operation_id": "publish-attached",
            "expected_revision": record["revision"], "expected_target_revision": state["revision"], "reason": "Synthetic continuation", "evidence": ["synthetic"]})
        self.assertTrue((self.source / "journal/days.md").read_bytes().startswith(self.originals["journal/days.md"]))
        self.assertTrue(self.cli("search", "zzattached804")["items"])
        (self.root / ".memory-cache/memory-l/ordinary.sqlite").write_bytes(b"broken cache")
        result = self.cli("search", "zzextra71943")
        self.assertEqual(result["mode"], "direct_lexical_rag")
        self.assertTrue(result["items"])

    def test_stale_entry_source_and_reserved_slots_are_preserved(self):
        plan, _ = self.plan()
        entry = self.root / "AGENTS.md"
        entry.write_bytes(entry.read_bytes() + b"Concurrent user rule\n")
        self.cli("attach-apply", "--plan", str(plan), ok=False)
        self.assertFalse((self.root / ".memory").exists())
        entry.write_bytes(self.root_before["AGENTS.md"])
        (self.root / ".memory").mkdir()
        (self.root / ".memory/important.md").write_bytes(b"Unrelated user data\n")
        self.cli("attach-apply", "--plan", str(plan), ok=False)
        self.assertEqual((self.root / ".memory/important.md").read_bytes(), b"Unrelated user data\n")
        self.assertFalse((self.root / ".memory/config.json").exists())

    def test_unclassified_original_memory_must_be_selected(self):
        (self.source / "another.md").write_bytes(b"Additional formal memory\n")
        plan, status = self.plan()
        self.assertFalse(status["ready_to_apply"])
        self.assertEqual(status["unclassified"], ["another.md"])
        self.cli("attach-apply", "--plan", str(plan), ok=False)
        self.assertFalse((self.root / ".memory-tools").exists())

    def test_missing_host_entry_gets_a_fragment_that_reads_existing_rules(self):
        (self.root / "CLAUDE.md").unlink()
        self.recipe["entry_files"].pop("CLAUDE.md")
        self.attach()
        self.assertIn("AGENTS.md", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertTrue((self.root / "AGENTS.md").read_bytes().startswith(self.root_before["AGENTS.md"]))
        self.cli("attach-rollback")
        self.assertFalse((self.root / "CLAUDE.md").exists())

    def test_new_original_directory_memory_registration_and_source_gate(self):
        self.attach()
        (self.source / "new-formal.md").write_bytes(b"# New formal diary\nzzregistered805\n")
        self.cli("manifest", ok=False)
        self.assertEqual(self.cli("search", "zzregistered805")["items"], [])
        self.cli("attach-register", "new-formal.md", "--reason", "An actually authored synthetic formal diary")
        self.cli("manifest")
        self.assertTrue(self.cli("search", "zzregistered805")["items"])
        self.cli("attach-register", "ports/raw.md", "--reason", "Attempt to bypass selection", ok=False)
        self.assertEqual(self.cli("context", "--purpose", "profile")["total"], 0)

    def test_rollback_keeps_new_records_and_never_reverts_original_memory(self):
        self.attach()
        new = self.cli("save", "--input", "-", data={"kind": "diary", "body": "Keep new diary after rollback", "operation_id": "keep-new"})
        path = self.source / "journal/days.md"
        path.write_bytes(path.read_bytes() + b"New legitimate old-format diary\n")
        raw = path.read_bytes()
        result = self.cli("attach-rollback")
        self.assertTrue(result["new_runtime_metadata_and_records_preserved"])
        for name, before in self.root_before.items():
            self.assertEqual((self.root / name).read_bytes(), before)
        self.assertEqual(path.read_bytes(), raw)
        self.assertTrue((self.root / ".memory/records/diary" / (new["id"] + ".md")).exists())
        self.assertEqual(self.cli("status")["attachment_phase"], "rolled_back")
        self.cli("search", "old", ok=False)

    def test_rollback_refuses_to_clobber_later_project_rules(self):
        self.attach()
        path = self.root / "AGENTS.md"
        path.write_bytes(path.read_bytes() + b"A later user rule\n")
        raw = path.read_bytes()
        other = (self.root / "CLAUDE.md").read_bytes()
        self.cli("attach-rollback", ok=False)
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual((self.root / "CLAUDE.md").read_bytes(), other)

    def test_partial_failure_restores_roots_and_same_plan_can_resume(self):
        plan, _ = self.plan()
        code = '''import os, sys
os.environ["MEMORY_L_WORKSPACE"] = sys.argv[2]
sys.path.insert(0,sys.argv[1])
import integrity, legacy_attachment
def fail(*args):
    raise OSError("Synthetic failure after managed root updates")
integrity.write_manifest = fail
try:
    legacy_attachment.apply(sys.argv[3])
except OSError:
    print("stopped")
else:
    raise AssertionError("Failure was not exercised")
'''
        result = subprocess.run([sys.executable, "-S", "-c", code, str(SCRIPT.parent), str(self.root), str(plan)],
                                capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, before in self.root_before.items():
            self.assertEqual((self.root / name).read_bytes(), before)
        self.assertEqual(self.cli("status")["attachment_phase"], "rolled_back")
        self.assertEqual(self.cli("attach-apply", "--plan", str(plan))["status"], "attached_originals_verified")

    def test_actual_git_clone_and_mcp_read_the_existing_paths(self):
        self.git("init")
        self.git("add", "project.py")
        self.git("commit", "-m", "Existing project")
        self.attach()
        self.cli("stage")
        self.cli("check", "--git-index")
        self.git("commit", "-m", "Attach memory tools")
        clone = self.base / "attached-clone"
        self.git("clone", "--no-local", str(self.root), str(clone))
        installed = clone / ".memory-tools/memory.py"
        self.cli("attach-verify", root=clone, script=installed)
        self.cli("check", "--git-ref", "HEAD", root=clone, script=installed)
        self.assertEqual((clone / ".claude-memory/journal/days.md").read_bytes(), self.originals["journal/days.md"])
        self.assertFalse((clone / ".claude-memory/ports/raw.md").exists())
        self.assertEqual((clone / "project.py").read_bytes(), b"# Existing project\r\nvalue = 42\r\n")
        self.assertTrue(self.cli("search", "zzextra71943", root=clone, script=installed)["items"])
        try:
            import mcp
        except ImportError:
            return
        async def probe():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(command=sys.executable,
                args=[str(clone / ".memory-tools/server.py"), "--workspace", str(clone)], env={**os.environ, "PYTHONUTF8": "1"})
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    value = await client.call_tool("memory_l_core_file", {"name": "SEED.md"})
                    self.assertFalse(value.isError)
                    self.assertEqual(value.structuredContent["path"], ".claude-memory/identity/original-seed.md")
                    value = await client.call_tool("memory_l_core_file", {"name": "ATTACHMENT.md"})
                    self.assertFalse(value.isError)
        asyncio.run(probe())
