"""Build a standalone release from an explicit public-file allowlist."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

PACKAGE = Path(__file__).resolve().parents[1]
VERSION = "0.2.1"
ROOT_FILES = ("README.md", "LICENSE", "VALIDATION.md", ".gitignore", ".gitattributes",
              ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
              "tools/build_release.py", "tools/verify_release.py")
TREES = ("skills/memory-l", "tests", "evaluations")


def public_files():
    paths = {PACKAGE / name for name in ROOT_FILES}
    for name in TREES:
        folder = PACKAGE / name
        for path in folder.rglob("*"):
            relative = path.relative_to(folder)
            if any(part in {"__pycache__", ".git"} for part in relative.parts):
                continue
            if path.is_file() and path.suffix in {".py", ".md", ".txt", ".yaml", ".xml", ".json"}:
                paths.add(path)
    for path in paths:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(PACKAGE):
            raise ValueError("Missing or unsafe public input: " + str(path))
    return sorted(paths, key=lambda path: path.relative_to(PACKAGE).as_posix())


def build(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    payload = {path.relative_to(PACKAGE).as_posix(): path.read_bytes().replace(b"\r\n", b"\n") for path in public_files()}
    entries = [{"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} for name, raw in payload.items()]
    identity = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()[:12]
    destination = output / ("memory-l-" + identity)
    if destination.is_symlink():
        raise ValueError("Release directory may not be a symlink")
    destination.mkdir(exist_ok=True)
    manifest = {"name": "memory-l", "version": VERSION, "release_id": identity,
                "private_data_included": False, "files": entries}
    payload["RELEASE-MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    for name, raw in payload.items():
        path = destination / name
        if not path.resolve().is_relative_to(destination) or path.is_symlink():
            raise ValueError("Unsafe release path")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("Existing release ID has different content")
        path.write_bytes(raw)
    from verify_release import verify
    result = verify(destination)
    archive = output / ("memory-l-" + VERSION + ".zip")
    descriptor, temporary = tempfile.mkstemp(prefix=".kit-release-", dir=output)
    os.close(descriptor)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as compressed:
            for name, raw in sorted(payload.items()):
                entry = ZipInfo("memory-l/" + name, date_time=(2026, 11, 8, 0, 0, 0))
                entry.compress_type = ZIP_DEFLATED
                entry.external_attr = 0o644 << 16
                compressed.writestr(entry, raw)
        with ZipFile(temporary) as compressed:
            assert set(compressed.namelist()) == {"memory-l/" + name for name in payload}
            for name, raw in payload.items():
                assert compressed.read("memory-l/" + name) == raw
        os.replace(temporary, archive)
    finally:
        Path(temporary).unlink(missing_ok=True)
    result.update(directory=str(destination), archive=str(archive), zip_files=len(payload),
                  archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), release_id=identity)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PACKAGE / "dist")
    print(json.dumps(build(parser.parse_args().output), ensure_ascii=False, indent=2))
