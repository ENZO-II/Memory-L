"""Shared admission, promotion and explicit delegation decisions."""

from datetime import datetime, timezone

from .store import ConflictError, request_digest
from .learning import learning_allowed, source_fingerprint

LEVELS = [None, "P2", "P1", "P0"]
DECISIONS = {"admit", "promote", "adopt", "select_learning", "deselect_learning", "observe", "confirm", "reject", "retract", "demote"}
PROFILE_KINDS = {"calibration", "framework", "reflection", "relationship"}


class PolicyError(ValueError):
    pass


def internalization_eligible(record):
    selected = (
        record.get("internalization_level") == "P0"
        and record.get("review_status") == "confirmed"
        and record.get("scope") == "private"
        and bool(record.get("decision_ref"))
        and record.get("source_status", "current") == "current"
    )
    if not selected:
        return False
    for event in record.get("history", []):
        audit = event.get("audit", {})
        previous = event.get("previous", {})
        sequential = audit.get("action") == "promote" and previous.get("internalization_level") == "P1"
        adopted = audit.get("action") == "adopt" and valid_joint_review(audit.get("joint_review"))
        if not (sequential or adopted) or previous.get("body") != record.get("body"):
            continue
        if not audit.get("reason") or not audit.get("evidence"):
            continue
        if audit.get("actor") in {"owner", "joint"}:
            return True
        delegated = audit.get("authorization_at_decision", {})
        if audit.get("actor") == "companion" and delegated.get("id") == audit.get("authorization") and delegated.get("revision"):
            return True
    return False


def profile_eligible(record):
    return record.get("kind") in PROFILE_KINDS and internalization_eligible(record)


def valid_joint_review(review):
    return isinstance(review, dict) and all(isinstance(review.get(key), str) and review[key].strip()
                                           for key in ("owner", "companion", "boundary"))


def check_authority(store, record, action, target, actor, authorization):
    if action in {"select_learning", "deselect_learning"}:
        if actor not in {"owner", "joint"}:
            raise PolicyError("High-volume source selection requires Owner's explicit choice")
        return
    if action == "adopt" and actor == "owner":
        raise PolicyError("Direct adoption records an actual joint discussion, not a source-review click")
    if actor in {"owner", "joint"}:
        return
    if actor != "companion":
        raise PolicyError("Unknown decision actor")
    current = record.get("internalization_level")
    own_observation = record.get("author") == "companion" and record.get("scope") == "private"
    if own_observation and action in {"observe", "admit"}:
        return
    if own_observation and current in {None, "P2"} and action in {"reject", "retract"}:
        return
    if not authorization:
        raise PolicyError("This decision needs joint confirmation or an explicit delegation")
    grant = store.read(authorization)
    authority = grant.get("authority", {})
    authorized_event = any(
        event.get("audit", {}).get("action") == "authorize"
        and event["audit"].get("actor") in {"owner", "joint"}
        for event in grant.get("history", [])
    )
    if grant["kind"] != "authorization" or grant.get("review_status") != "confirmed" or not authorized_event:
        raise PolicyError("Delegation is unconfirmed or withdrawn")
    expiry = authority.get("expires_at")
    if expiry:
        expires = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise PolicyError("Delegation has expired or lacks a timezone")
    for field in ("kind", "scope", "carrier"):
        allowed = authority.get(field + "s", [])
        if "*" not in allowed and record.get(field) not in allowed:
            raise PolicyError(f"Decision is outside delegated {field} range")
    if action not in authority.get("actions", []):
        raise PolicyError("Decision action is outside the delegation")
    if target not in LEVELS or LEVELS.index(target) > LEVELS.index(authority.get("max_level")):
        raise PolicyError("Decision exceeds delegated level")
    return {"id": grant["id"], "revision": grant["revision"], "authority": authority}


def decide(store, record_id, action, *, operation_id, expected_revision, actor,
           reason, evidence, authorization=None, joint_review=None):
    if action not in DECISIONS or not reason.strip() or not evidence:
        raise PolicyError("A known action, reason and evidence references are required")
    record = store.read(record_id)
    audit = {"action": action, "actor": actor, "reason": reason,
             "evidence": evidence, "authorization": authorization}
    if joint_review is not None:
        audit["joint_review"] = joint_review
    previous_request = record.get("operations", {}).get(operation_id)
    if previous_request is not None:
        if previous_request == request_digest(audit):
            return record
        raise ConflictError("Operation ID reused with different decision inputs")
    current = record.get("internalization_level")
    if current not in LEVELS:
        raise PolicyError("Unknown internalization level")
    target = current
    status = record.get("review_status", "pending")
    extra_changes = {}
    if action == "admit":
        if current is not None:
            raise PolicyError("Record already entered candidacy")
        target = "P2"
    elif action == "promote":
        if current not in {"P2", "P1"}:
            raise PolicyError("Promotion follows P2, P1, P0 in order")
        target = LEVELS[LEVELS.index(current) + 1]
        status = "confirmed"
    elif action == "adopt":
        if not valid_joint_review(joint_review):
            raise PolicyError("Direct adoption needs both actual viewpoints and the adopted scope/boundary")
        target, status = "P0", "confirmed"
    elif action == "select_learning":
        extra_changes["learning_selection"] = {"operation_id": operation_id,
                                               "source_fingerprint": source_fingerprint(record),
                                               "source_revision": record["revision"]}
    elif action == "deselect_learning":
        extra_changes["learning_selection"] = None
    elif action == "demote":
        if current not in {"P0", "P1"}:
            raise PolicyError("Only P0 or P1 records can be demoted")
        target = LEVELS[LEVELS.index(current) - 1]
        status = "pending"
    elif action == "confirm":
        status = "confirmed"
    elif action in {"reject", "retract"}:
        target = None
        status = "retracted" if action == "retract" else "reviewed"
    if record.get("review_status") == "retracted" and action not in {"observe", "reject", "retract"}:
        raise PolicyError("Withdrawn material needs an explicit new candidate")
    if target is not None and record.get("scope") in {"public", "unknown"}:
        raise PolicyError("Source scope does not admit personal internalization")
    if record.get("kind") == "authorization" and action not in {"retract", "observe"}:
        raise PolicyError("Use an explicit authorization operation for delegation")
    changes = {"internalization_level": target, "review_status": status, **extra_changes}
    if action not in {"select_learning", "deselect_learning"}:
        changes["decision_ref"] = operation_id
    def verify_authority(latest):
        if action in {"admit", "promote", "adopt"} and not learning_allowed(store, latest):
            raise PolicyError("Source or inherited material is not selected for learning; preserve it as reference only")
        proof = check_authority(store, latest, action, target, actor, authorization)
        if proof is not None:
            audit["authorization_at_decision"] = proof
    return store.update(record_id, operation_id, expected_revision, changes, audit=audit,
                        check=verify_authority,
                        request=audit)


def authorize(store, authority, *, operation_id, actor, reason, evidence):
    if actor not in {"owner", "joint"} or not reason.strip() or not evidence:
        raise PolicyError("Delegation requires an explicit user decision with evidence")
    if authority.get("max_level") not in {"P2", "P1", "P0"}:
        raise PolicyError("Delegation needs a maximum level")
    for field in ("kinds", "scopes", "carriers", "actions"):
        if not isinstance(authority.get(field), list) or not authority[field]:
            raise PolicyError(f"Delegation needs explicit {field}")
    if not set(authority["actions"]).issubset(DECISIONS):
        raise PolicyError("Unknown delegated decision")
    record = store.create("authorization", reason, operation_id,
                          metadata={"title": "明确交付的判断范围", "author": actor, "authority": authority,
                                    "evidence": evidence})
    return store.update(record["id"], operation_id + ":authorize", record["revision"],
                        {"review_status": "confirmed", "decision_ref": operation_id + ":authorize"},
                        audit={"action": "authorize", "actor": actor, "reason": reason, "evidence": evidence})
