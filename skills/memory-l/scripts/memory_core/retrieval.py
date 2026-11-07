"""Portable Chinese lexical retrieval and exact source coordinates."""

from collections import Counter
import math
from pathlib import Path
import re

from .context import terms
from .policy import profile_eligible
from .store import MARKER, parse, RecordStore
from .lifecycle import recall_eligible, source_lifecycle
from .learning import learning_allowed


def source_chunks(path, max_chars=500, raw=None, include_raw=False):
    path = Path(path).resolve()
    raw = path.read_bytes() if raw is None else raw
    text = raw.decode("utf-8-sig")
    base = 0
    labels = {"purpose": "source_evidence", "internalization_level": "", "review_status": "canonical_document"}
    if MARKER in text[:300]:
        record = parse(raw, path)
        if not include_raw and (not recall_eligible(record) or not learning_allowed(RecordStore(path.parent.parent), record)):
            return []
        if record.get("reflection_session"):
            session = RecordStore(path.parent.parent).read(record["reflection_session"])
            if session.get("phase") != "completed":
                return []
        if record["kind"] in {"source_snapshot", "authorization", "reflection_session", "session_cursor"} or record["review_status"] == "retracted":
            return []
        legacy = record.get("legacy", {}).get("record", {})
        if record.get("source_status", "current") != "current" or legacy.get("archived") in (True, 1) or legacy.get("status") == "retired":
            return []
        if any(event.get("operation_id") == record.get("decision_ref") and event.get("audit", {}).get("action") == "reject"
               for event in record.get("history", [])):
            return []
        base = len(text) - len(record["body"])
        labels = {"record_id": record["id"], "scope": record["scope"], "kind": record["kind"],
                  "internalization_level": record.get("internalization_level") or "",
                  "review_status": record["review_status"], "profile_eligible": profile_eligible(record),
                  "purpose": "source_evidence", "lifecycle_state": source_lifecycle(record)["state"]}
    body = text[base:]
    heading = record["title"] if "record_id" in labels else "(文件开头)"
    sections = []
    start = 0
    for match in re.finditer(r"(?m)^#{1,2} .*$", body):
        if match.start() > start:
            sections.append((start, match.start(), heading))
        start = match.start()
        heading = match.group().strip()
    sections.append((start, len(body), heading))
    result = []
    for begin, end, heading in sections:
        cursor = begin
        while cursor < end:
            stop = min(cursor + max_chars, end)
            if stop < end:
                boundary = body.rfind("\n", cursor, stop)
                if boundary > cursor + max_chars // 2:
                    stop = boundary + 1
            piece = body[cursor:stop]
            if piece.strip():
                absolute = base + cursor
                result.append({"text": piece, "metadata": {
                    "file": str(path), "line": text.count("\n", 0, absolute) + 1,
                    "end_line": text.count("\n", 0, base + stop - 1) + 1,
                    "char_start": absolute, "char_end": base + stop,
                    "heading": heading, "chunk_index": len(result), **labels}})
            cursor = stop
    return result


def lexical_rank(query, chunks, limit=20):
    query_terms = terms(query)
    if not query_terms or not chunks:
        return []
    documents = [terms(chunk["text"] + " " + chunk["metadata"]["heading"]) for chunk in chunks]
    frequency = Counter(term for document in documents for term in document)
    scored = []
    for chunk, document in zip(chunks, documents):
        overlap = query_terms & document
        if not overlap:
            continue
        score = sum(math.log(1 + (len(chunks) + .5) / (frequency[term] + .5)) for term in overlap)
        score /= 1 + .15 * math.log(1 + len(document))
        if query.casefold() in chunk["text"].casefold():
            score += 4
        if terms(chunk["metadata"]["heading"]) & query_terms:
            score += 1
        scored.append({**chunk["metadata"], "text": chunk["text"], "lexical_score": score, "source": "关键词"})
    return sorted(scored, key=lambda item: (-item["lexical_score"], item["file"], item["line"]))[:limit]


def reciprocal_rank_fusion(rankings, limit=10, k=60):
    combined = {}
    for ranking in rankings:
        seen = set()
        for position, item in enumerate(ranking, 1):
            key = (item["file"], item.get("char_start", item["line"]))
            if key in seen:
                continue
            seen.add(key)
            merged = combined.setdefault(key, {**item, "rrf_score": 0, "retrievers": []})
            merged["rrf_score"] += 1 / (k + position)
            merged["retrievers"].append(item.get("source", "语义"))
    return sorted(combined.values(), key=lambda item: (-item["rrf_score"], item["file"], item["line"]))[:limit]
