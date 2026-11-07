"""Verify the exact allowlisted release inventory, ignoring only Git/bytecode."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
    expected = {item["path"]: item for item in manifest["files"]}
    actual = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in {".git", "__pycache__"} for part in relative.parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError("Unexpected symlink in release: " + relative.as_posix())
        if path.is_file():
            actual.add(relative.as_posix())
    if actual != set(expected) | {"RELEASE-MANIFEST.json"}:
        raise ValueError("Release inventory differs: " + repr(sorted(actual.symmetric_difference(set(expected) | {"RELEASE-MANIFEST.json"}))))
    for name, item in expected.items():
        path = root / name
        if not path.resolve().is_relative_to(root):
            raise ValueError("Release path leaves its root")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("Release bytes differ: " + name)
    return {"version": manifest["version"], "files_verified": len(expected), "inventory_verified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2))
