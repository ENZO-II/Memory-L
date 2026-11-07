"""Explicit, version-checked publication to the existing authored Markdown files."""

from pathlib import Path

from .files import atomic_write, file_lock
from .store import ConflictError, digest, request_digest
from .policy import internalization_eligible
from .learning import learning_allowed

TARGETS = {"diary": "SELF-NOTES.md", "growth": "TIMELINE.md", "calibration": "SOUL.md"}


def target_state(project, destination):
    if destination not in TARGETS:
        raise ValueError("Destination must be diary, growth or calibration")
    path = Path(project).resolve() / ".memory" / TARGETS[destination]
    return {"path": str(path), "revision": digest(path.read_bytes())}


def publish(store, project, record_id, destination, *, operation_id, expected_revision,
            expected_target_revision, actor, reason, evidence):
    if not isinstance(reason, str) or not reason.strip() or not evidence or not operation_id:
        raise ValueError("Publication requires an operation ID, reason and evidence")
    target = target_state(project, destination)
    path = Path(target["path"])
    request = {"id": record_id, "destination": destination, "actor": actor, "reason": reason,
               "evidence": evidence, "record_revision": expected_revision, "target_revision": expected_target_revision}
    marker = "<!-- companion-publication " + record_id + " " + request_digest(operation_id) + " -->"
    with store.transaction(), file_lock(path.parent / ".publication.lock"):
        record = store.read(record_id)
        content = path.read_text(encoding="utf-8-sig")
        previous = record.get("operations", {}).get(operation_id)
        if previous:
            if previous != request_digest(request) or marker not in content:
                raise ConflictError("Publication retry differs or the published text was removed; reconcile explicitly")
            return {"id": record_id, "path": str(path), "status": "published", "record_revision": record["revision"]}
        if record["revision"] != expected_revision:
            raise ConflictError("Record changed before publication")
        own = record["author"] == "companion" and record["scope"] == "private"
        if destination == "diary":
            permitted = own and actor in {"companion", "joint", "owner"}
        elif destination == "calibration" and record["kind"] == "lesson":
            permitted = own and actor in {"companion", "joint", "owner"}
        else:
            permitted = (actor in {"owner", "joint"} and internalization_eligible(record)
                         and learning_allowed(store, record))
        if not permitted or record["review_status"] == "retracted":
            raise ValueError("Publication is outside the record's authorship, decision or scope")
        if marker not in content:
            original = path.read_bytes()
            if digest(original) != expected_target_revision:
                raise ConflictError("Destination changed; read its latest revision before publishing")
            title = record["title"].replace("\n", " ").replace("\r", " ")
            if destination == "calibration" and record["kind"] == "lesson":
                title = "技术经验 · " + title
            appended = "\n\n" + marker + "\n## " + title + "\n\n" + record["body"] + "\n\n<!-- /companion-publication -->\n"
            if path.read_bytes() != original:
                raise ConflictError("Destination changed while preparing publication")
            # Preserve original bytes, including its BOM and newline style.
            atomic_write(path, original + appended.encode("utf-8"))
        publications = list(record.get("publications", []))
        publications.append({"destination": destination, "path": TARGETS[destination], "operation_id": operation_id,
                             "source_revision": expected_revision})
        updated = store.update(record_id, operation_id, expected_revision, {"publications": publications},
                               audit={"action": "publish", "actor": actor, "reason": reason, "evidence": evidence}, request=request)
        return {"id": record_id, "path": str(path), "status": "published", "record_revision": updated["revision"]}
