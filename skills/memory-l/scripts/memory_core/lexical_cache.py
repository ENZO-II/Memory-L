"""Disposable SQLite/FTS accelerator; Markdown remains the source of truth.

Atomic record writes change their kind directory, so normal queries inspect a
few directory stamps rather than reopening thousands of unchanged records.
Canonical documents are checked individually. Returned files are hash-verified.
"""

import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3

from .context import terms
from .files import file_lock
from .retrieval import source_chunks
from .store import MARKER, parse, RecordStore
from .lifecycle import recall_eligible, source_lifecycle
from .learning import learning_allowed

EXCLUDED = {"source_snapshot", "authorization", "reflection_session", "session_cursor"}


def encoded(term):
    return "t" + term.encode("utf-8").hex()


def stamp(path):
    info = path.stat()
    return f"{info.st_mtime_ns}:{info.st_ctime_ns}:{info.st_size}:{info.st_ino}"


class LexicalCache:
    def __init__(self, path, source_dirs, record_root, extra_files=(), include_raw=False):
        self.path = Path(path)
        self.source_dirs = [Path(folder).resolve() for folder in source_dirs]
        self.record_root = Path(record_root).resolve()
        self.extra_files = [Path(path).resolve() for path in extra_files]
        self.include_raw = include_raw

    def canonical_files(self):
        files = {path for path in self.extra_files if path.is_file()}
        for folder in self.source_dirs:
            if not folder.exists():
                continue
            for current, directories, names in os.walk(folder):
                base = Path(current)
                directories[:] = [name for name in directories if not name.startswith(".")
                                  and (base / name).resolve() != self.record_root]
                for name in names:
                    path = base / name
                    if name.endswith(".md") and name != "MANIFEST.md" and not name.startswith((".", "runtime-contract-before-")) and not path.is_symlink():
                        files.add(path.resolve())
        return sorted(files)

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS source_groups(name TEXT PRIMARY KEY,stamp TEXT);
            CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,group_name TEXT,stamp TEXT,sha TEXT,deferred INTEGER);
            CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY,file TEXT,source_sha TEXT,body TEXT,metadata TEXT,tokens TEXT);
            CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(tokens,content='chunks',content_rowid='id');
            CREATE VIRTUAL TABLE IF NOT EXISTS vocabulary USING fts5vocab(chunk_fts,'row');
        """)
        version = 3 if self.include_raw else 2
        if connection.execute("PRAGMA user_version").fetchone()[0] != version:
            with connection:
                connection.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('delete-all')")
                connection.execute("DELETE FROM chunks")
                connection.execute("DELETE FROM files")
                connection.execute("DELETE FROM source_groups")
                connection.execute("PRAGMA user_version=" + str(version))
        return connection

    def remove_file(self, connection, path):
        for row in connection.execute("SELECT id,tokens FROM chunks WHERE file=?", (str(path),)).fetchall():
            connection.execute("INSERT INTO chunk_fts(chunk_fts,rowid,tokens) VALUES('delete',?,?)", (row["id"], row["tokens"]))
        connection.execute("DELETE FROM chunks WHERE file=?", (str(path),))
        connection.execute("DELETE FROM files WHERE path=?", (str(path),))

    def update_file(self, connection, path, group, force=False):
        path = Path(path)
        previous = connection.execute("SELECT * FROM files WHERE path=?", (str(path),)).fetchone()
        current_stamp = stamp(path)
        if previous and previous["stamp"] == current_stamp and not previous["deferred"] and not force:
            return
        raw = path.read_bytes()
        fingerprint = hashlib.sha256(raw).hexdigest()
        if previous and previous["sha"] == fingerprint and not previous["deferred"] and not force:
            connection.execute("UPDATE files SET stamp=? WHERE path=?", (current_stamp, str(path)))
            return
        chunks = source_chunks(path, raw=raw, include_raw=self.include_raw)
        if stamp(path) != current_stamp:
            raise OSError("Markdown changed while building lexical cache")
        self.remove_file(connection, path)
        for chunk in chunks:
            tokens = " ".join(sorted(encoded(term) for term in terms(chunk["text"] + " " + chunk["metadata"]["heading"])))
            cursor = connection.execute("INSERT INTO chunks(file,source_sha,body,metadata,tokens) VALUES(?,?,?,?,?)",
                (str(path), fingerprint, chunk["text"], json.dumps(chunk["metadata"], ensure_ascii=False), tokens))
            connection.execute("INSERT INTO chunk_fts(rowid,tokens) VALUES(?,?)", (cursor.lastrowid, tokens))
        # Empty/incomplete records are cheap to reconsider. This also allows a
        # reflection session to finish without rewriting its output files.
        deferred = False
        if not chunks and MARKER.encode() in raw[:300]:
            record = parse(raw, path)
            if not self.include_raw and not recall_eligible(record):
                return
            deferred = bool(record.get("reflection_session") or record.get("learning_sources")) and (self.include_raw or recall_eligible(record))
        connection.execute("INSERT INTO files VALUES(?,?,?,?,?)", (str(path), group, current_stamp, fingerprint, int(deferred)))

    def refresh(self, connection, force=False):
        canonical = self.canonical_files()
        canonical_stamp = hashlib.sha256(json.dumps([(str(path), stamp(path)) for path in canonical]).encode()).hexdigest()
        groups = {"canonical": (canonical_stamp, lambda: canonical)}
        if self.record_root.exists():
            for directory in self.record_root.iterdir():
                excluded = EXCLUDED | ({"session_material"} if not self.include_raw else set())
                if directory.is_dir() and not directory.is_symlink() and not directory.name.startswith(".") and directory.name not in excluded:
                    groups["record:" + directory.name] = (stamp(directory), lambda directory=directory: sorted(directory.glob("*.md")))
        with connection:
            previous_groups = {row["name"]: row["stamp"] for row in connection.execute("SELECT * FROM source_groups")}
            for group, (signature, collect) in groups.items():
                if not force and previous_groups.get(group) == signature:
                    continue
                paths = collect()
                names = {str(path) for path in paths}
                old = [row[0] for row in connection.execute("SELECT path FROM files WHERE group_name=?", (group,))]
                for path in set(old) - names:
                    self.remove_file(connection, path)
                for path in paths:
                    self.update_file(connection, path, group, force)
                connection.execute("INSERT OR REPLACE INTO source_groups VALUES(?,?)", (group, signature))
            for group in set(previous_groups) - set(groups):
                for row in connection.execute("SELECT path FROM files WHERE group_name=?", (group,)).fetchall():
                    self.remove_file(connection, row[0])
                connection.execute("DELETE FROM source_groups WHERE name=?", (group,))
            for row in connection.execute("SELECT path,group_name FROM files WHERE deferred=1").fetchall():
                if Path(row["path"]).is_file():
                    self.update_file(connection, row["path"], row["group_name"], True)

    def ranked(self, connection, query, limit):
        query_terms = terms(query)
        if not query_terms:
            return []
        query_encoded = {encoded(term) for term in query_terms}
        frequency = {}
        for term in query_encoded:
            row = connection.execute("SELECT doc FROM vocabulary WHERE term=?", (term,)).fetchone()
            frequency[term] = row[0] if row else 0
        count = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
        expression = " OR ".join('"' + term + '"' for term in sorted(query_encoded))
        rows = connection.execute("SELECT c.* FROM chunk_fts JOIN chunks c ON c.id=chunk_fts.rowid WHERE chunk_fts MATCH ? ORDER BY c.id", (expression,))
        scored = []
        for row in rows:
            document = set(row["tokens"].split())
            overlap = query_encoded & document
            metadata = json.loads(row["metadata"])
            score = sum(math.log(1 + (count + .5) / (frequency[term] + .5)) for term in overlap)
            score /= 1 + .15 * math.log(1 + len(document))
            if query.casefold() in row["body"].casefold():
                score += 4
            if terms(metadata["heading"]) & query_terms:
                score += 1
            scored.append({**metadata, "text": row["body"], "lexical_score": score,
                           "source": "关键词", "source_sha256": row["source_sha"]})
        return sorted(scored, key=lambda item: (-item["lexical_score"], item["file"], item["line"]))[:limit]

    def search(self, query, limit=20, force=False):
        with file_lock(self.path.with_suffix(".lock"), timeout=30):
            connection = self.connect()
            try:
                self.refresh(connection, force)
                for attempt in range(3):
                    matches = self.ranked(connection, query, limit)
                    invalid = set()
                    fingerprints = {}
                    current_records = {}
                    for match in matches:
                        path = match["file"]
                        if path not in fingerprints:
                            raw = Path(path).read_bytes() if Path(path).exists() else None
                            fingerprints[path] = hashlib.sha256(raw).hexdigest() if raw is not None else None
                            if raw is not None and MARKER.encode() in raw[:300]:
                                current_records[path] = parse(raw, Path(path))
                        if fingerprints[path] != match["source_sha256"]:
                            invalid.add(path)
                        if path in current_records:
                            record = current_records[path]
                            match["lifecycle_state"] = source_lifecycle(record)["state"]
                            if not self.include_raw and (not recall_eligible(record) or not learning_allowed(RecordStore(self.record_root), record)):
                                invalid.add(path)
                    if not invalid:
                        return matches
                    with connection:
                        for path in invalid:
                            row = connection.execute("SELECT group_name FROM files WHERE path=?", (path,)).fetchone()
                            if Path(path).exists():
                                self.update_file(connection, path, row[0], True)
                            else:
                                self.remove_file(connection, path)
                raise OSError("Sources kept changing; retry lexical retrieval")
            finally:
                connection.close()
