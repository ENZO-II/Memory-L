"""Versioned Markdown records. Reading requires only Python's standard library."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

from .settings import workspace, namespace

from .files import atomic_write, file_lock
from .lifecycle import RAW_KINDS

MARKER = "<!-- companion-memory v1 -->"
METADATA = re.compile(re.escape(MARKER) + r"\n```json\n(.*?)\n```\n\n## 正文\n", re.S)
KINDS = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
DEFAULT_ROOT = workspace() / ".memory" / "records"


class ConflictError(ValueError):
    """The caller's source version or idempotency payload no longer matches."""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def request_digest(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def render(record):
    metadata = {k: v for k, v in record.items() if k not in {"body", "revision", "path"}}
    title = str(metadata.get("title", metadata["id"])).replace("\n", " ")
    encoded = json.dumps(metadata, ensure_ascii=False, indent=2)
    return f"# {title}\n\n{MARKER}\n```json\n{encoded}\n```\n\n## 正文\n{record['body']}".encode("utf-8")


def parse(data, path=None):
    text = data.decode("utf-8-sig")
    match = METADATA.search(text)
    if match is None:
        raise ValueError("Missing versioned memory metadata block")
    record = json.loads(match.group(1))
    if not isinstance(record, dict):
        raise ValueError("Memory metadata must be an object")
    if record.get("schema_version") != 1:
        raise ValueError("Unsupported memory schema version")
    if not isinstance(record.get("id"), str):
        raise ValueError("Memory ID must be a UUID string")
    uuid.UUID(record["id"])
    if not isinstance(record.get("kind"), str) or not KINDS.fullmatch(record["kind"]):
        raise ValueError("Invalid memory kind")
    for field in ("author", "carrier", "scope", "created_at", "review_status"):
        if not isinstance(record.get(field), str):
            raise ValueError(f"Invalid memory field type: {field}")
    if not isinstance(record.get("title"), str):
        raise ValueError("Memory title must be text")
    for field in ("history", "evidence", "relations"):
        if not isinstance(record.get(field), list):
            raise ValueError(f"Invalid memory list field: {field}")
    for field in ("operations", "legacy"):
        if not isinstance(record.get(field), dict):
            raise ValueError(f"Invalid memory object field: {field}")
    if any(not isinstance(event, dict) for event in record["history"]):
        raise ValueError("History events must be objects")
    if record.get("internalization_level") not in (None, "P2", "P1", "P0"):
        raise ValueError("Invalid internalization level")
    if record["review_status"] not in {"pending", "reviewed", "confirmed", "retracted"}:
        raise ValueError("Invalid review status")
    record["body"] = text[match.end():]
    record["revision"] = digest(data)
    if path is not None:
        record["path"] = str(path)
    return record


class RecordStore:
    def __init__(self, root=DEFAULT_ROOT):
        self.root = Path(root).resolve()

    def transaction(self):
        return file_lock(self.root / ".locks" / "writer.lock")

    def _path(self, kind, record_id):
        if not isinstance(kind, str) or not KINDS.fullmatch(kind):
            raise ValueError("Invalid memory kind")
        record_id = str(uuid.UUID(record_id))
        path = self.root / kind / f"{record_id}.md"
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Memory path leaves the store")
        return path

    def read(self, record_id):
        record_id = str(uuid.UUID(record_id))
        matches = self._find_paths(record_id)
        if len(matches) != 1:
            raise ValueError(f"Expected one memory for ID {record_id}, found {len(matches)}")
        path = matches[0]
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Memory path leaves the store")
        record = parse(path.read_bytes(), path)
        if record["id"] != record_id or record["kind"] != path.parent.name:
            raise ValueError("Record identity differs from its canonical path")
        return record

    def _find_paths(self, record_id):
        # Probe the few kind directories directly. Glob would enumerate every
        # record for each ID read, making a full migration verification quadratic.
        if not self.root.exists():
            return []
        return [directory / (record_id + ".md") for directory in self.root.iterdir()
                if directory.is_dir() and not directory.name.startswith(".")
                and (directory / (record_id + ".md")).is_file()]

    def records(self, kinds=None):
        patterns = ["*/*.md"]
        if kinds is not None:
            if any(not KINDS.fullmatch(kind) for kind in kinds):
                raise ValueError("Invalid memory kind filter")
            patterns = [kind + "/*.md" for kind in kinds]
        paths = sorted(path for pattern in patterns for path in self.root.glob(pattern))
        for path in paths:
            if path.parent.name.startswith("."):
                continue
            if not path.resolve().is_relative_to(self.root):
                raise ValueError("Memory path leaves the store")
            record = parse(path.read_bytes(), path)
            if record["id"] != path.stem or record["kind"] != path.parent.name:
                raise ValueError("Record identity differs from its canonical path")
            yield record

    def create(self, kind, body, operation_id, *, metadata=None, record_id=None):
        if not isinstance(operation_id, str) or not operation_id or not isinstance(body, str):
            raise ValueError("A stable operation_id and text body are required")
        metadata = deepcopy(metadata or {})
        if not isinstance(metadata, dict):
            raise ValueError("Memory metadata must be an object")
        protected = {"id", "schema_version", "kind", "body", "history", "operations", "revision", "path"}
        if protected.intersection(metadata):
            raise ValueError("Reserved memory fields in metadata")
        if metadata.get("internalization_level") is not None:
            raise ValueError("New records require an explicit admission decision before P2")
        record_id = record_id or str(uuid.uuid5(uuid.NAMESPACE_URL, namespace() + ":" + operation_id))
        path = self._path(kind, record_id)
        fingerprint = request_digest({"kind": kind, "body": body, "metadata": metadata})
        with file_lock(self.root / ".locks" / "writer.lock"):
            existing = self._find_paths(record_id)
            if existing:
                record = self.read(record_id)
                if record.get("operations", {}).get(operation_id) == fingerprint:
                    return record
                raise ConflictError("Record or operation ID already exists with different content")
            record = {
                "schema_version": 1, "id": record_id, "kind": kind,
                "title": kind, "author": "companion", "carrier": "unknown",
                "scope": "private", "created_at": now_iso(), "event_time": None,
                "internalization_level": None, "review_status": "pending",
                "decision_ref": None, "retention": "source_managed" if kind in RAW_KINDS else "durable", "evidence": [],
                "relations": [], "legacy": {},
                **metadata,
                "body": body, "operation_id": operation_id,
                "operations": {operation_id: fingerprint}, "history": [],
            }
            encoded = render(record)
            parse(encoded)
            atomic_write(path, encoded)
            return parse(encoded, path)

    def update(self, record_id, operation_id, expected_revision, changes, *, audit, check=None, request=None):
        """Internal mutation primitive. Public callers use revision or policy operations."""
        if not operation_id or not expected_revision:
            raise ValueError("operation_id and expected_revision are required")
        if "body" in changes and not isinstance(changes["body"], str):
            raise ValueError("Memory body must be text")
        protected = {"id", "schema_version", "kind", "history", "operations", "revision", "path", "created_at"}
        if protected.intersection(changes):
            raise ValueError("Reserved memory fields in changes")
        fingerprint = request_digest(request if request is not None else {"changes": changes, "audit": audit})
        with file_lock(self.root / ".locks" / "writer.lock"):
            record = self.read(record_id)
            old_fingerprint = record.get("operations", {}).get(operation_id)
            if old_fingerprint is not None:
                if old_fingerprint == fingerprint:
                    return record
                raise ConflictError("Operation ID reused with different content")
            if record["revision"] != expected_revision:
                raise ConflictError("Source changed. Read the latest revision and reconcile")
            if check is not None:
                check(record)
            previous = {k: v for k, v in record.items() if k not in {"history", "operations", "revision", "path"}}
            record["history"].append({
                "operation_id": operation_id, "at": now_iso(),
                "audit": deepcopy(audit), "previous": previous,
            })
            record.update(deepcopy(changes))
            record["updated_at"] = now_iso()
            record["operation_id"] = operation_id
            record["operations"][operation_id] = fingerprint
            path = Path(record["path"])
            encoded = render(record)
            parse(encoded)
            atomic_write(path, encoded)
            return parse(encoded, path)

    def revise(self, record_id, body, operation_id, expected_revision, *, reason):
        if not isinstance(body, str) or not isinstance(reason, str) or not reason.strip():
            raise ValueError("Revision reason is required")
        record = self.read(record_id)
        changes = {"body": body}
        if record["body"] != body:
            changes.update({"review_status": "pending", "decision_ref": None})
            if record.get("internalization_level") == "P0":
                changes["internalization_level"] = "P2"
        return self.update(record_id, operation_id, expected_revision, changes,
                           audit={"action": "revise", "reason": reason},
                           request={"action": "revise", "body": body, "reason": reason})
