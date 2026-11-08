"""Markdown integrity and Git object checks; no installer or home discovery."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unicodedata
from memory_core.files import atomic_write
from memory_core.learning import authored_memory, has_governance
from memory_core.lifecycle import legacy_reasoning, source_material
from memory_core.store import RecordStore, parse
from memory_core.settings import CORE_NAMES, core_path, configuration

MANIFEST = ".memory/MANIFEST.md"
LOCAL_KINDS = {"session_material", "session_cursor"}
REQUIRED = tuple(".memory/" + name for name in ("SEED.md", "PROFILE.md", "USER.md", "TIMELINE.md", "SOUL.md", "SELF-NOTES.md", "MEMORY.md"))

def markdown_payload(title, value):
    return ("# " + title + "\n\n```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```\n").encode("utf-8")

def read_payload(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    return json.loads(text.split("```json\n", 1)[1].rsplit("\n```", 1)[0])

def asset_paths(project):
    paths = memory_paths(project)
    if configuration(project).get("attachment"):
        from legacy_attachment import formal_paths
        paths.extend(formal_paths(project))
        paths.append(project / ".memory/attachment.json")
    registry = project / ".memory-tools/runtime-files.json"
    if not registry.is_file():
        raise ValueError("Runtime registry is missing; install the kit into this workspace first")
    names = json.loads(registry.read_text(encoding="utf-8"))["files"]
    for name in names:
        path = project / ".memory-tools" / name
        if not path.resolve().is_relative_to(project / ".memory-tools") or path.is_symlink():
            raise ValueError("Runtime entry leaves the workspace")
        paths.append(path)
    paths.extend([registry, project / ".memory/config.json"])
    paths.extend(project / name for name in ("AGENTS.md", "CLAUDE.md", ".gitignore", ".gitattributes") if (project / name).is_file())
    return sorted(set(paths), key=lambda path: path.relative_to(project).as_posix())

CREDENTIAL = re.compile(rb"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")

def memory_paths(project):
    paths = [project / name for name in REQUIRED if not name.startswith(".memory/")]
    records = {}
    for path in (project / ".memory").rglob("*.md"):
        if path == project / MANIFEST:
            continue
        parts = path.relative_to(project).parts
        if "records" in parts and parts[parts.index("records") + 1] in LOCAL_KINDS:
            continue
        if "records" in parts:
            record = parse(path.read_bytes(), path)
            if record["id"] in records:
                raise ValueError("Duplicate memory ID in migration source: " + record["id"])
            records[record["id"]] = record
            continue
        paths.append(path)
    pending = [record["id"] for record in records.values()
               if authored_memory(record) or has_governance(record) or legacy_reasoning(record)]
    included = set()
    while pending:
        record_id = pending.pop()
        if record_id in included:
            continue
        if record_id not in records:
            raise ValueError("Missing portable memory dependency: " + record_id)
        record = records[record_id]
        if source_material(record) and not legacy_reasoning(record) and not has_governance(record):
            raise ValueError("Unselected source dependency requires review before Git migration: " + record_id)
        included.add(record_id)
        paths.append(Path(record["path"]))
        references = [record.get("reflection_session")]
        references.extend(source["id"] for source in record.get("learning_sources", []))
        if record["kind"] == "reflection_session":
            references.extend(source["id"] for source in record.get("inputs", []))
        references.extend(source["id"] for source in record.get("evidence", [])
                          if isinstance(source, dict) and source.get("id") in records)
        references.extend(event.get("audit", {}).get("authorization") for event in record.get("history", []))
        pending.extend(reference for reference in references if reference)
    return sorted(paths, key=lambda path: unicodedata.normalize("NFC", path.relative_to(project).as_posix()))

def inspect_assets(project):
    entries, kinds = [], Counter()
    missing = [str(core_path(name, project).relative_to(project)) for name in CORE_NAMES if not core_path(name, project).is_file()]
    if missing:
        raise ValueError("Missing Markdown assets: " + ", ".join(missing))
    for path in asset_paths(project):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(project):
            raise ValueError("Missing or unsafe memory asset: " + str(path))
        raw = path.read_bytes()
        if not raw.strip():
            raise ValueError("Empty memory asset: " + str(path))
        raw.decode("utf-8-sig")
        if CREDENTIAL.search(raw):
            raise ValueError("Credential-like literal requires review in " + str(path))
        relative = unicodedata.normalize("NFC", path.relative_to(project).as_posix())
        if relative.startswith(".memory/records/"):
            record = parse(raw, path)
            if record["id"] != path.stem or record["kind"] != path.parent.name:
                raise ValueError("Record path does not match its metadata: " + relative)
            kinds[record["kind"]] += 1
        entries.append({"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return {"schema_version": 1, "files": entries, "record_files": sum(kinds.values()), "by_kind": dict(kinds)}

def verify_assets(project):
    if not (project / MANIFEST).is_file():
        raise ValueError("Migration manifest is missing; update and push it from the source workspace")
    expected = read_payload(project / MANIFEST)
    actual = inspect_assets(project)
    if expected.get("schema_version") != 1 or actual["files"] != expected.get("files"):
        raise ValueError("Markdown assets differ from the committed migration manifest; inspect local changes or synchronize the complete source")
    return actual

def write_manifest(project):
    with RecordStore(project / ".memory/records").transaction():
        if (project / MANIFEST).is_file():
            previous = read_payload(project / MANIFEST)
            missing = [entry["path"] for entry in previous.get("files", []) if not (project / entry["path"]).is_file()]
            if missing:
                raise ValueError("Previously listed memory is missing; reconcile before updating the manifest: " + ", ".join(missing[:5]))
        result = inspect_assets(project)
        for entry in result["files"]:
            if hashlib.sha256((project / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError("Memory changed while preparing its manifest; retry after the writer finishes")
        atomic_write(project / MANIFEST, markdown_payload("Git migration integrity manifest", result))
    return result

def verify_git_assets(project, assets, *, index=False, ref=None):
    """Read Git objects to catch omitted, unstaged or outdated memory files."""
    def git(*arguments):
        result = subprocess.run(["git", *arguments], cwd=project, capture_output=True, timeout=60)
        if result.returncode:
            raise ValueError("Git memory verification failed: " + result.stderr.decode(errors="replace")[:500])
        return result.stdout

    algorithm = git("rev-parse", "--show-object-format").decode().strip()
    objects = {}
    if index:
        for row in git("ls-files", "--stage", "-z").split(b"\0"):
            if row:
                info, name = row.split(b"\t", 1)
                mode, oid, stage = info.split()
                if stage == b"0":
                    objects[name.decode("utf-8")] = oid.decode()
        target = "index"
    else:
        target = git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
        for row in git("ls-tree", "-r", "-z", target).split(b"\0"):
            if row:
                info, name = row.split(b"\t", 1)
                objects[name.decode("utf-8")] = info.split()[2].decode()
    mismatches = []
    for item in assets["files"]:
        raw = (project / item["path"]).read_bytes()
        oid = hashlib.new(algorithm, b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if objects.get(item["path"]) != oid:
            mismatches.append(item["path"])
    manifest_oid = objects.get(MANIFEST)
    if manifest_oid is None or git("cat-file", "blob", manifest_oid).replace(b"\r\n", b"\n") != (project / MANIFEST).read_bytes().replace(b"\r\n", b"\n"):
        mismatches.append(MANIFEST)
    if mismatches:
        raise ValueError("Memory missing or outdated in Git " + str(ref or target) + ": " + ", ".join(mismatches[:10]))
    return {"target": target, "memory_files": len(assets["files"]), "manifest_verified": True}
