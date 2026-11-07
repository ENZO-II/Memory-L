"""Keep authored memory, legacy reasoning and temporary sources distinct."""

from datetime import datetime, timedelta, timezone
import json
import re
from .settings import source_days


RAW_KINDS = {"session_material", "session_cursor", "external_material"}
LEGACY_REASONING = {}


def port_source(record):
    """Recognize explicit port provenance without inferring it from body text."""
    legacy = record.get("legacy", {}).get("record", {})
    legacy = legacy if isinstance(legacy, dict) else {}
    metadata = legacy.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            metadata = {}
    hints = [record.get("carrier", ""), record.get("origin", {}).get("source_id", ""),
             legacy.get("source", ""), legacy.get("carrier", "")]
    if isinstance(metadata, dict):
        hints.extend([metadata.get("source", ""), metadata.get("carrier", "")])
        if isinstance(metadata.get("tags"), list):
            hints.extend(metadata["tags"])
    if isinstance(legacy.get("tags"), list):
        hints.extend(legacy["tags"])
    return any(isinstance(hint, str) and (re.search(r"(^|[^a-z])qq($|[^a-z])", hint.casefold())
               or hint.casefold() == "angel" or any(part in hint.casefold()
               for part in ("qq_", "qq/", "astrbot", "angel_memory", "webui/qq"))) for hint in hints)


def legacy_reasoning(record):
    source = LEGACY_REASONING.get(record.get("kind"))
    return bool(source and record.get("origin", {}).get("source_id") == source
                and record.get("legacy", {}).get("source_id") == source
                and record.get("learning_gate") != "owner_selection" and not port_source(record))


def source_material(record):
    from .learning import requires_selection

    return (record.get("kind") in RAW_KINDS or record.get("learning_gate") == "owner_selection"
            or (record.get("author") == "unknown" and bool(record.get("origin", {}).get("source_id")))
            or requires_selection(record))


def timestamp(value):
    if isinstance(value, (int, float)):
        seconds = value / 1000 if abs(value) >= 100_000_000_000 else value
        return datetime.fromtimestamp(seconds, timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def source_lifecycle(record, now=None):
    from .learning import selected_for_learning

    if legacy_reasoning(record) or not source_material(record):
        return {"state": "retained", "expires_at": None}
    if record.get("internalization_level") is not None or selected_for_learning(record):
        return {"state": "selected", "expires_at": None}
    legacy = record.get("legacy", {}).get("record", {})
    expiry = record.get("expires_at", legacy.get("expires_at", legacy.get("expire_at")))
    # Owner's explicit source scope retains its original long-lived policy.
    if not expiry and record.get("scope") == "owner":
        return {"state": "source_managed", "expires_at": None}
    try:
        deadline = timestamp(expiry) if expiry else timestamp(record["created_at"]) + timedelta(days=source_days())
    except (TypeError, ValueError, OverflowError, OSError):
        return {"state": "invalid_time", "expires_at": None}
    current = datetime.now(timezone.utc) if now is None else now
    return {"state": "expired" if current >= deadline else "pending",
            "expires_at": deadline.isoformat()}


def source_expired(record, now=None):
    return source_lifecycle(record, now)["state"] in {"expired", "invalid_time"}


def recall_eligible(record):
    """Ordinary recall uses authored or explicitly admitted records."""
    return (record.get("kind") not in {"session_material", "session_cursor"} and not source_expired(record)
            and (not source_material(record) or record.get("internalization_level") is not None))
