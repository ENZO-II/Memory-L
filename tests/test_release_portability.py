"""An actual release clone with Git CRLF conversion enabled."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]


class ReleasePortabilityTests(unittest.TestCase):
    def test_release_inventory_survives_autocrlf_clone(self):
        with tempfile.TemporaryDirectory(prefix="memory-l-release-", dir=os.environ.get("MEMORY_L_TEST_DIR")) as temporary:
            base = Path(temporary).resolve()
            built = subprocess.run([sys.executable, "-X", "utf8", str(PACKAGE / "tools/build_release.py"),
                "--output", str(base / "release")], capture_output=True, encoding="utf-8", check=True, timeout=60)
            source = Path(json.loads(built.stdout)["directory"])
            clone = base / "clone"
            def git(*args, cwd=source):
                return subprocess.run(["git", "-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid",
                    "-c", "commit.gpgSign=false", "-c", "core.autocrlf=true", "-c", "core.hooksPath=" + str(base / "no-hooks"),
                    *args], cwd=cwd, capture_output=True, check=True, timeout=60)
            git("init")
            git("add", ".")
            git("commit", "-m", "Synthetic release")
            git("clone", "--no-local", str(source), str(clone))
            checked = subprocess.run([sys.executable, "-S", str(clone / "tools/verify_release.py"), str(clone)],
                                    capture_output=True, encoding="utf-8", check=True, timeout=60)
            self.assertTrue(json.loads(checked.stdout)["inventory_verified"])
            for name in (".gitattributes", ".gitignore", "LICENSE", "evaluations/questions.xml"):
                self.assertEqual((clone / name).read_bytes(), (source / name).read_bytes())
