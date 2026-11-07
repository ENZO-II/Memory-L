"""Synthetic integration tests. No real accounts, personas or source databases."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE / "skills/memory-l/scripts/memory.py"
TEST_PARENT = Path(os.environ.get("MEMORY_L_TEST_DIR", tempfile.gettempdir()))


class KitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="md-memory-test-", dir=TEST_PARENT)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "自己的记忆 workspace"
        self.cli("init", "--name", "DemoAgent", "--owner", "ExampleOwner")

    def cli(self, *arguments, data=None, ok=True, root=None, script=None, standard_only=False):
        command = [sys.executable] + (["-S"] if standard_only else []) + [str(script or SCRIPT), "--workspace", str(root or self.root), *arguments]
        result = subprocess.run(command, input=json.dumps(data, ensure_ascii=False) if data is not None else None,
                                capture_output=True, text=True, encoding="utf-8", timeout=60,
                                env={**os.environ, "PYTHONUTF8": "1"})
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def save(self, kind="reflection", body="合成的原文与适用范围", operation="save", **metadata):
        return self.cli("save", "--input", "-", data={"kind": kind, "body": body, "operation_id": operation, "metadata": metadata})

    def decision(self, record, action, operation, actor="joint", **extra):
        return self.cli("decide", "--input", "-", data={"id": record["id"], "expected_revision": record["revision"],
            "action": action, "operation_id": operation, "actor": actor, "reason": "Synthetic explicit decision",
            "evidence": ["synthetic:discussion"], **extra})

    def git(self, *arguments, root=None):
        return subprocess.run(["git", "-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgSign=false", "-c", "core.autocrlf=true", "-c", "core.hooksPath=" + str(self.base / "no-hooks"), *arguments],
            cwd=root or self.root, check=True, capture_output=True, timeout=60)

    def test_initialization_is_stdlib_and_preserves_existing_identity(self):
        current = self.cli("status", standard_only=True)
        self.assertFalse(current["identity_ready"])
        self.assertTrue(current["loader_connected"])
        seed = self.root / ".memory/SEED.md"
        seed.write_bytes(b"# A jointly written seed\r\nOriginal bytes stay intact.\r\n")
        before = seed.read_bytes()
        self.cli("init", "--name", "DemoAgent", "--owner", "ExampleOwner")
        self.assertEqual(seed.read_bytes(), before)
        existing = self.base / "existing"
        existing.mkdir()
        door = existing / "AGENTS.md"
        door.write_bytes(b"# Existing persona rules\r\n")
        result = self.cli("init", "--name", "OtherAgent", "--owner", "OtherOwner", root=existing)
        self.assertFalse(result["loader_connected"])
        self.assertEqual(door.read_bytes(), b"# Existing persona rules\r\n")
        self.assertTrue((existing / ".memory/LOADER.md").is_file())
        self.cli("init", "--name", "WrongIdentity", "--owner", "ExampleOwner", ok=False)

    def test_independent_namespaces_and_paths(self):
        first = self.save(body="第一个工作区的独有内容 zzprivate861", operation="same-operation")
        other = self.base / "second"
        self.cli("init", "--name", "OtherAgent", "--owner", "OtherOwner", root=other)
        second = self.cli("save", "--input", "-", root=other, data={"kind": "diary", "body": "第二个工作区", "operation_id": "same-operation"})
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.cli("search", "zzprivate861", root=other)["items"], [])
        self.assertNotIn(str(self.root), json.dumps(self.cli("connections", root=other)))

    def test_public_plugin_directory_cannot_become_a_personal_memory_workspace(self):
        public = self.base / "public-plugin"
        (public / ".claude-plugin").mkdir(parents=True)
        (public / ".claude-plugin/plugin.json").write_text('{"name":"synthetic"}', encoding="utf-8")
        skill = public / "skills/memory-l/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("Synthetic plugin marker", encoding="utf-8")
        self.cli("init", "--name", "DemoAgent", "--owner", "ExampleOwner", root=public, ok=False)
        self.assertFalse((public / ".memory").exists())

    def test_retry_and_stale_revision_preserve_originals(self):
        first = self.save(operation="retry")
        self.assertEqual(self.save(operation="retry")["revision"], first["revision"])
        changed = self.cli("revise", "--input", "-", data={"id": first["id"], "body": "修改后的原文", "operation_id": "revise",
            "expected_revision": first["revision"], "reason": "Synthetic correction"})
        self.assertEqual(changed["history"][0]["previous"]["body"], first["body"])
        self.cli("revise", "--input", "-", ok=False, data={"id": first["id"], "body": "旧版本覆盖", "operation_id": "stale",
            "expected_revision": first["revision"], "reason": "Synthetic stale write"})
        self.assertEqual(self.cli("read", first["id"])["body"], "修改后的原文")

    def test_common_adoption_and_gradual_promotion(self):
        record = self.save()
        self.assertEqual(self.cli("context", "--purpose", "profile")["total"], 0)
        observed = self.decision(record, "admit", "observe", actor="companion")
        self.assertEqual(observed["internalization_level"], "P2")
        self.cli("decide", "--input", "-", ok=False, data={"id": observed["id"], "expected_revision": observed["revision"],
            "action": "promote", "operation_id": "unauthorized", "reason": "Synthetic attempt", "evidence": ["synthetic"]})
        verified = self.decision(observed, "promote", "verify")
        self.assertEqual(verified["internalization_level"], "P1")
        adopted = self.decision(verified, "promote", "adopt")
        self.assertEqual(self.cli("context", "--purpose", "profile")["items"][0]["id"], adopted["id"])
        direct = self.save(operation="direct", body="经过实际共同讨论的合成理解")
        direct = self.decision(direct, "adopt", "direct-adopt", joint_review={"owner": "Synthetic owner viewpoint", "companion": "Synthetic companion viewpoint", "boundary": "Synthetic test only"})
        self.assertEqual(direct["internalization_level"], "P0")

    def test_source_selection_withdrawal_and_default_recall(self):
        source_file = self.root / ".memory-sources/selected.md"
        source_file.parent.mkdir()
        source_file.write_text("端口原文独有词 zzsource829", encoding="utf-8")
        source = self.cli("ingest-markdown", str(source_file), "--carrier", "synthetic-port", "--source-id", "one", "--scope", "private")
        self.assertEqual(self.cli("search", "zzsource829")["items"], [])
        self.assertTrue(self.cli("search", "zzsource829", "--include-raw")["items"])
        self.assertEqual(self.cli("context", "--purpose", "learning")["items"], [])
        source = self.decision(source, "confirm", "confirm", actor="owner")
        self.assertEqual(self.cli("context", "--purpose", "learning")["items"], [])
        source = self.decision(source, "select_learning", "select", actor="owner")
        self.assertIsNone(source["internalization_level"])
        packet = self.cli("reflect-prepare", "--tier", "deep", "--operation-id", "prepare", "--query", "zzsource829")
        output = self.cli("reflect-commit", "--input", "-", data={"session_id": packet["session_id"], "operation_id": "commit",
            "outputs": [{"kind": "reflection", "title": "派生理解", "body": "经过选择后的派生独有词 zzderived712"}]})
        self.assertTrue(self.cli("search", "zzderived712")["items"])
        self.decision(source, "deselect_learning", "withdraw", actor="owner")
        self.assertEqual(self.cli("search", "zzderived712")["items"], [])
        self.assertEqual(self.cli("read", output["outputs"][0])["body"], "经过选择后的派生独有词 zzderived712")

    def test_publication_keeps_bytes_and_does_not_duplicate(self):
        target = self.root / ".memory/SELF-NOTES.md"
        original = b"\xef\xbb\xbf# Existing diary\r\nOriginal text\r\n"
        target.write_bytes(original)
        record = self.save(kind="diary", body="新的合成日记", operation="diary")
        state = self.cli("target-state", "diary")
        request = {"id": record["id"], "destination": "diary", "operation_id": "publish", "expected_revision": record["revision"],
                   "expected_target_revision": state["revision"], "reason": "Synthetic diary publication", "evidence": ["synthetic:diary"]}
        self.cli("publish", "--input", "-", data=request)
        self.cli("publish", "--input", "-", data=request)
        raw = target.read_bytes()
        self.assertTrue(raw.startswith(original))
        self.assertEqual(raw.count("新的合成日记".encode()), 1)
        self.assertIsNone(self.cli("read", record["id"])["internalization_level"])

    def test_portable_manifest_staging_and_git_clone(self):
        diary = self.save(kind="diary", body="未晋升日记也能迁移", operation="portable")
        extra = self.root / ".memory/continuity/new.md"
        extra.parent.mkdir()
        extra.write_bytes("新增正式正文\r\n".encode())
        raw_file = self.root / ".memory-sources/raw.md"
        raw_file.parent.mkdir()
        raw_file.write_text("未治理的合成来源", encoding="utf-8")
        raw = self.cli("ingest-markdown", str(raw_file), "--carrier", "synthetic", "--source-id", "raw", "--scope", "private")
        manifest = self.cli("manifest")
        self.assertEqual(manifest["record_files"], 1)
        self.git("init")
        self.cli("check", "--git-index", ok=False)
        self.cli("stage")
        self.cli("check", "--git-index")
        self.git("commit", "-m", "Synthetic memory snapshot")
        self.cli("check", "--git-ref", "HEAD")
        tracked = self.git("ls-files", "-z").stdout.decode().split("\0")
        self.assertIn(".memory/records/diary/" + diary["id"] + ".md", tracked)
        self.assertNotIn(".memory/records/external_material/" + raw["id"] + ".md", tracked)
        clone = self.base / "克隆 clone"
        self.git("clone", "--no-local", str(self.root), str(clone))
        installed = clone / ".memory-tools/memory.py"
        self.cli("check", "--git-ref", "HEAD", root=clone, script=installed, standard_only=True)
        recovered = self.cli("read", diary["id"], root=clone, script=installed, standard_only=True)
        self.assertEqual(recovered["body"], diary["body"])
        self.assertEqual((clone / ".memory/continuity/new.md").read_bytes(), extra.read_bytes())
        extra.write_text("新正文尚未提交", encoding="utf-8")
        self.cli("manifest")
        self.cli("check", "--git-ref", "HEAD", ok=False)

    def test_unselected_evidence_cannot_be_exported(self):
        path = self.root / ".memory-sources/unselected.md"
        path.parent.mkdir()
        path.write_text("合成的未选原文", encoding="utf-8")
        source = self.cli("ingest-markdown", str(path), "--carrier", "synthetic", "--source-id", "unselected", "--scope", "private")
        self.cli("save", "--input", "-", data={"kind": "reflection", "body": "还没有获准沿用的草稿", "operation_id": "draft", "source_records": [source["id"]]})
        self.cli("manifest", ok=False)

    def test_broken_cache_falls_back_to_original_markdown(self):
        record = self.save(kind="diary", body="缓存损坏后的原文独有词 zzfallback438", operation="fallback")
        (self.root / ".memory-cache/ordinary.sqlite").write_bytes(b"This is not a SQLite database")
        result = self.cli("search", "zzfallback438")
        self.assertEqual(result["mode"], "direct_lexical_rag")
        self.assertEqual(result["items"][0]["record_id"], record["id"])

    def test_expiry_is_separate_from_authored_diary_retention(self):
        code = """import json
from memory_core import RecordStore
from memory_core.lifecycle import source_lifecycle
s=RecordStore()
old={'created_at':'2000-01-01T00:00:00Z'}
raw=s.create('external_material','zzexpired538','expired',metadata={**old,'author':'unknown'})
owner=s.create('external_material','zzowner539','owner-source',metadata={**old,'author':'unknown','scope':'owner'})
diary=s.create('diary','zzdiary540','old-diary',metadata=old)
print(json.dumps([source_lifecycle(r)['state'] for r in (raw,owner,diary)]))
"""
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", check=True, timeout=30,
            env={**os.environ, "MEMORY_L_WORKSPACE": str(self.root), "PYTHONPATH": str(self.root / ".memory-tools"), "PYTHONUTF8": "1"})
        self.assertEqual(json.loads(result.stdout), ["expired", "source_managed", "retained"])
        self.assertEqual(self.cli("search", "zzexpired538")["items"], [])
        self.assertEqual(self.cli("search", "zzexpired538", "--include-raw")["items"][0]["lifecycle_state"], "expired")

    def test_mcp_round_trip_and_path_boundary(self):
        try:
            import mcp
        except ImportError:
            self.skipTest("Optional MCP SDK is not installed")
        async def probe():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            parameters = StdioServerParameters(command=sys.executable, args=[str(self.root / ".memory-tools/server.py"), "--workspace", str(self.root)],
                                              env={**os.environ, "PYTHONUTF8": "1"})
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    self.assertIn("memory_l_save", {tool.name for tool in tools.tools})
                    saved = await client.call_tool("memory_l_save", {"params": {"kind": "diary", "body": "MCP 合成全文", "operation_id": "mcp"}})
                    self.assertFalse(saved.isError)
                    read = await client.call_tool("memory_l_read", {"record_id": saved.structuredContent["id"]})
                    self.assertEqual(read.structuredContent["body"], "MCP 合成全文")
                    core = await client.call_tool("memory_l_core_file", {"name": "SEED.md", "max_chars": 10})
                    self.assertTrue(core.structuredContent["has_more"])
                    escaped = await client.call_tool("memory_l_ingest_markdown", {"path": "../outside.md", "carrier": "synthetic", "source_id": "escape"})
                    self.assertTrue(escaped.isError)
                    profile = await client.call_tool("memory_l_context", {"purpose": "profile"})
                    self.assertEqual(profile.structuredContent["total"], 0)
        asyncio.run(probe())


if __name__ == "__main__":
    unittest.main()
