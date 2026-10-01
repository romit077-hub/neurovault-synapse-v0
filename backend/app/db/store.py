from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

import numpy as np

from app.ingestion.chunking import Chunk
from app.memory.facts import Fact, classify


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, filename TEXT NOT NULL, uploaded_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL UNIQUE, extracted_text TEXT NOT NULL,
  char_count INTEGER NOT NULL, chunk_count INTEGER NOT NULL, fact_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL REFERENCES documents(id),
  ordinal INTEGER NOT NULL, text TEXT NOT NULL, source_ref TEXT NOT NULL,
  start_char INTEGER NOT NULL, embedding BLOB NOT NULL,
  UNIQUE(document_id, ordinal)
);
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY, subject TEXT NOT NULL, attribute TEXT NOT NULL,
  value TEXT NOT NULL, norm_value TEXT NOT NULL, status TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_sources (
  memory_id TEXT NOT NULL REFERENCES memories(id), document_id TEXT NOT NULL REFERENCES documents(id),
  source_ref TEXT NOT NULL, PRIMARY KEY(memory_id, document_id, source_ref)
);
CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY, existing_memory_id TEXT NOT NULL REFERENCES memories(id),
  existing_value TEXT NOT NULL, existing_source TEXT NOT NULL,
  new_subject TEXT NOT NULL, new_attribute TEXT NOT NULL, new_value TEXT NOT NULL,
  new_norm_value TEXT NOT NULL, new_document_id TEXT NOT NULL REFERENCES documents(id),
  new_source TEXT NOT NULL, classification TEXT NOT NULL, confidence REAL NOT NULL,
  reason TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
  resolved_at TEXT, new_memory_id TEXT REFERENCES memories(id)
);
CREATE INDEX IF NOT EXISTS memory_key ON memories(subject, attribute, status);
CREATE INDEX IF NOT EXISTS alert_status ON alerts(status);
CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
"""


class DuplicateDocument(ValueError):
    pass


class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        with closing(self.connect()) as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def vector_rows(self) -> list[tuple[int, np.ndarray]]:
        with closing(self.connect()) as conn:
            rows = conn.execute("SELECT id, embedding FROM chunks ORDER BY id").fetchall()
        vectors = []
        for row in rows:
            vector = np.frombuffer(row["embedding"], dtype=np.float32).copy()
            if vector.shape != (384,) or not np.isfinite(vector).all():
                raise ValueError(f"Stored embedding for chunk {row['id']} is corrupt")
            vectors.append((row["id"], vector))
        return vectors

    def _insert_memory(self, conn: sqlite3.Connection, fact: Fact, doc_id: str, source: str, status: str = "active") -> str:
        memory_id = str(uuid4())
        timestamp = now()
        conn.execute("INSERT INTO memories VALUES (?,?,?,?,?,?,?,?)",
                     (memory_id, fact.subject, fact.attribute, fact.value, fact.norm_value, status, timestamp, timestamp))
        conn.execute("INSERT INTO memory_sources VALUES (?,?,?)", (memory_id, doc_id, source))
        return memory_id

    def add_document(self, filename: str, digest: str, extracted_text: str,
                     chunks: list[Chunk], embeddings: np.ndarray,
                     facts: list[tuple[Fact, str]]) -> tuple[dict, list[int]]:
        if embeddings.shape != (len(chunks), 384):
            raise ValueError("Embedding dimensions do not match chunks")
        if not np.isfinite(embeddings).all():
            raise ValueError("Embedding contains a non-finite value")
        document_id = str(uuid4())
        events: list[dict] = []
        chunk_ids: list[int] = []
        with self.lock, closing(self.connect()) as conn, conn:
            if conn.execute("SELECT 1 FROM documents WHERE content_sha256=?", (digest,)).fetchone():
                raise DuplicateDocument("This exact document was already indexed")
            conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)", (
                document_id, filename, now(), digest, extracted_text, len(extracted_text), len(chunks), len(facts)))
            for ordinal, (chunk, vector) in enumerate(zip(chunks, embeddings)):
                cursor = conn.execute("""INSERT INTO chunks(document_id, ordinal, text, source_ref, start_char, embedding)
                    VALUES (?,?,?,?,?,?)""", (document_id, ordinal, chunk.text, chunk.source_ref, chunk.start_char,
                                                 np.asarray(vector, dtype=np.float32).tobytes()))
                chunk_ids.append(cursor.lastrowid)
            for fact, source_ref in facts:
                matches = conn.execute("""SELECT * FROM memories WHERE subject=? AND attribute=?
                    AND status IN ('active','coexisting') ORDER BY updated_at DESC, rowid DESC""",
                    (fact.subject, fact.attribute)).fetchall()
                duplicate = next((row for row in matches if row["norm_value"] == fact.norm_value), None)
                existing = duplicate or (matches[0] if matches else None)
                related = not matches and bool(conn.execute("""SELECT 1 FROM memories
                    WHERE subject=? AND attribute<>? AND status IN ('active','coexisting') LIMIT 1""",
                    (fact.subject, fact.attribute)).fetchone())
                old_fact = (Fact(existing["subject"], existing["attribute"], existing["value"],
                                 existing["norm_value"], False) if existing else None)
                classification, confidence, reason = classify(old_fact, fact, related)
                event = {"subject": fact.subject, "attribute": fact.attribute, "value": fact.value,
                         "classification": classification, "reason": reason}
                if classification == "DUPLICATE":
                    conn.execute("INSERT OR IGNORE INTO memory_sources VALUES (?,?,?)", (existing["id"], document_id, source_ref))
                elif classification in ("NEW_INFORMATION", "RELATED_INFORMATION"):
                    event["memory_id"] = self._insert_memory(conn, fact, document_id, source_ref)
                else:
                    original = conn.execute("""SELECT d.filename, ms.source_ref FROM memory_sources ms
                        JOIN documents d ON d.id=ms.document_id WHERE ms.memory_id=? ORDER BY d.uploaded_at LIMIT 1""",
                        (existing["id"],)).fetchone()
                    old_source = f"{original['filename']} · {original['source_ref']}" if original else "Unknown source"
                    alert_id = str(uuid4())
                    conn.execute("""INSERT INTO alerts(id, existing_memory_id, existing_value, existing_source,
                        new_subject, new_attribute, new_value, new_norm_value, new_document_id, new_source,
                        classification, confidence, reason, status, created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                        alert_id, existing["id"], existing["value"], old_source,
                        fact.subject, fact.attribute, fact.value, fact.norm_value, document_id,
                        f"{filename} · {source_ref}", classification, confidence, reason, "pending", now()))
                    event["alert_id"] = alert_id
                events.append(event)
        return {"id": document_id, "filename": filename, "chunk_count": len(chunks),
                "fact_count": len(facts), "events": events}, chunk_ids

    def dashboard(self) -> dict:
        with closing(self.connect()) as conn:
            return {
                "documents": conn.execute("SELECT count(*) FROM documents").fetchone()[0],
                "memories": conn.execute("SELECT count(*) FROM memories WHERE status IN ('active','coexisting')").fetchone()[0],
                "pending_alerts": conn.execute("SELECT count(*) FROM alerts WHERE status='pending'").fetchone()[0],
            }

    def documents(self) -> list[dict]:
        with closing(self.connect()) as conn:
            rows = conn.execute("""SELECT id, filename, uploaded_at, char_count, chunk_count, fact_count
                FROM documents ORDER BY uploaded_at DESC, rowid DESC""").fetchall()
            return [dict(row) for row in rows]

    def document(self, document_id: str) -> dict | None:
        with closing(self.connect()) as conn:
            row = conn.execute("""SELECT id, filename, uploaded_at, extracted_text, char_count, chunk_count, fact_count
                FROM documents WHERE id=?""", (document_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["sections"] = [dict(r) for r in conn.execute("""SELECT ordinal, source_ref, text FROM chunks
                WHERE document_id=? ORDER BY ordinal""", (document_id,))]
            return result

    def chunks_by_ids(self, ids: list[int]) -> dict[int, dict]:
        if not ids:
            return {}
        with closing(self.connect()) as conn:
            rows = conn.execute("""SELECT c.id, c.text, c.source_ref, d.id AS document_id, d.filename
                FROM chunks c JOIN documents d ON d.id=c.document_id
                WHERE c.id IN (""" + ",".join("?" for _ in ids) + ")", ids).fetchall()
            return {row["id"]: dict(row) for row in rows}

    def memories(self) -> list[dict]:
        with closing(self.connect()) as conn:
            rows = conn.execute("SELECT * FROM memories ORDER BY updated_at DESC, rowid DESC").fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["sources"] = [f"{r['filename']} · {r['source_ref']}" for r in conn.execute("""SELECT d.filename, ms.source_ref
                    FROM memory_sources ms JOIN documents d ON d.id=ms.document_id WHERE ms.memory_id=?
                    ORDER BY d.uploaded_at""", (row["id"],))]
                result.append(item)
            return result

    def alerts(self) -> list[dict]:
        with closing(self.connect()) as conn:
            rows = conn.execute("SELECT * FROM alerts ORDER BY (status='pending') DESC, created_at DESC, rowid DESC").fetchall()
            return [dict(row) for row in rows]

    def resolve_alert(self, alert_id: str, action: str) -> dict | None:
        if action not in {"accept_update", "keep_existing", "keep_both"}:
            raise ValueError("Invalid alert action")
        with self.lock, closing(self.connect()) as conn, conn:
            alert = conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
            if alert is None:
                return None
            if alert["status"] != "pending":
                raise ValueError("This alert has already been resolved")
            current = conn.execute("SELECT status FROM memories WHERE id=?", (alert["existing_memory_id"],)).fetchone()
            if current is None or current["status"] not in {"active", "coexisting"}:
                raise ValueError("The existing fact has changed since this alert was created; review current memory")
            new_id = None
            if action != "keep_existing":
                new_fact = Fact(alert["new_subject"], alert["new_attribute"], alert["new_value"], alert["new_norm_value"], False)
                new_id = self._insert_memory(conn, new_fact, alert["new_document_id"],
                                             alert["new_source"].rsplit(" · ", 1)[-1],
                                             "coexisting" if action == "keep_both" else "active")
            if action == "accept_update":
                conn.execute("UPDATE memories SET status='superseded', updated_at=? WHERE id=?", (now(), alert["existing_memory_id"]))
            conn.execute("UPDATE alerts SET status=?, resolved_at=?, new_memory_id=? WHERE id=?",
                         (action, now(), new_id, alert_id))
            return {"id": alert_id, "status": action, "new_memory_id": new_id}
