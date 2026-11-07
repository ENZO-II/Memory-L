"""Operator selection of high-volume sources, separate from internalization."""

from .store import request_digest
from .lifecycle import legacy_reasoning, port_source, source_expired

AUTHORED_KINDS = {"diary", "work", "fact", "reflection", "calibration", "lesson", "framework",
                  "exemplar", "tension", "relationship", "self_evaluation", "signal"}


def authored_memory(record):
    """A first-party written record remains portable before personality adoption."""
    return (record.get("kind") in AUTHORED_KINDS and record.get("author") == "companion"
            and record.get("scope") == "private" and not record.get("origin")
            and not record.get("legacy", {}).get("record") and not requires_selection(record))


def has_governance(record):
    actions = {"admit", "promote", "adopt", "observe", "confirm", "reject", "retract", "demote",
               "select_learning", "deselect_learning", "publish", "authorize"}
    return any(event.get("audit", {}).get("action") in actions
               and event["audit"].get("actor") in {"companion", "owner", "joint"}
               and event["audit"].get("reason") and event["audit"].get("evidence")
               for event in record.get("history", []))


def requires_selection(record):
    if record.get("learning_gate") == "owner_selection" or record.get("kind") in {"external_material", "session_material", "session_cursor"} or port_source(record):
        return True
    if legacy_reasoning(record):
        return False
    if record.get("author") == "unknown" and record.get("origin", {}).get("source_id") and not legacy_reasoning(record):
        return True
    return False


def source_fingerprint(record):
    return request_digest({key: record.get(key) for key in ("body", "scope", "origin")})


def selected_for_learning(record):
    selection = record.get("learning_selection")
    if not isinstance(selection, dict) or selection.get("source_fingerprint") != source_fingerprint(record):
        return False
    return any(event.get("operation_id") == selection.get("operation_id")
               and event.get("audit", {}).get("action") == "select_learning"
               and event["audit"].get("actor") in {"owner", "joint"}
               and event["audit"].get("reason") and event["audit"].get("evidence")
               and source_fingerprint(event.get("previous", {})) == source_fingerprint(record)
               for event in record.get("history", []))


def learning_allowed(store, record, seen=None):
    """Check source selection and inherited dependencies without admitting anything."""
    if source_expired(record) or record.get("review_status") == "retracted" or record.get("source_status", "current") != "current":
        return False
    legacy = record.get("legacy", {}).get("record", {})
    if legacy.get("archived") in (True, 1) or legacy.get("status") == "retired":
        return False
    if any(event.get("operation_id") == record.get("decision_ref") and event.get("audit", {}).get("action") == "reject"
           for event in record.get("history", [])):
        return False
    if requires_selection(record) and not selected_for_learning(record):
        return False
    seen = set() if seen is None else set(seen)
    if record["id"] in seen:
        return False
    seen.add(record["id"])
    references = record.get("learning_sources", [])
    if not isinstance(references, list):
        return False
    for reference in references:
        try:
            source = store.read(reference["id"])
            if source_fingerprint(source) != reference["source_fingerprint"] or not learning_allowed(store, source, seen):
                return False
        except (KeyError, TypeError, ValueError, OSError):
            return False
    return True
