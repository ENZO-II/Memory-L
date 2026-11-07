"""Bring back Markdown from phone/other endpoints without absorbing it."""

import hashlib
from pathlib import Path
import uuid

from .settings import namespace

from .store import ConflictError


def ingest_markdown(store, path, *, carrier, source_id, scope="unknown"):
    path = Path(path).resolve()
    if path.suffix.casefold() != ".md" or not path.is_file():
        raise ValueError("Expected an existing Markdown export")
    if not all(isinstance(value, str) and value.strip() for value in (carrier, source_id, scope)):
        raise ValueError("Carrier, stable source_id and scope are required")
    raw = path.read_bytes()
    fingerprint = hashlib.sha256(raw).hexdigest()
    encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
    operation_id = "ingest:" + carrier + ":" + source_id + ":" + fingerprint
    record_id = str(uuid.uuid5(uuid.NAMESPACE_URL, namespace() + ":" + operation_id))
    if store._find_paths(record_id):
        existing = store.read(record_id)
        if existing["scope"] != scope or existing["body"].encode(encoding) != raw:
            raise ConflictError("The existing source has different scope or text; reconcile explicitly")
        return existing
    return store.create("external_material", raw.decode(encoding), operation_id,
                        metadata={"title": path.stem, "author": "unknown", "carrier": carrier, "scope": scope,
                                  "internalization_level": None, "retention": "source_managed", "origin": {"source_id": source_id, "path": str(path),
                                     "source_sha256": fingerprint, "source_encoding": encoding}})
