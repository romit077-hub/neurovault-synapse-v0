from hashlib import sha256
import re
from threading import RLock

import numpy as np

from app.core.config import Settings
from app.db.store import Store
from app.ingestion.chunking import chunk_sections
from app.ingestion.files import extract_sections, validate_upload
from app.llm.ollama import OllamaClient
from app.memory.facts import extract_facts
from app.retrieval.vectors import LocalEmbedder, VectorIndex


INSUFFICIENT = "I do not have enough information in the indexed documents to answer that."


class Service:
    def __init__(self, settings: Settings, embedder=None, llm=None):
        self.store = Store(settings.data_dir / "neurovault.sqlite3")
        self.index = VectorIndex(self.store.vector_rows())
        self.embedder = embedder or LocalEmbedder(settings.embedding_model)
        self.llm = llm or OllamaClient(settings.ollama_url, settings.ollama_model)
        self.lock = RLock()

    def ingest(self, filename: str, mime: str | None, data: bytes) -> dict:
        filename, extension = validate_upload(filename, mime, data)
        sections = extract_sections(extension, data)
        text = "\n\n".join(section.text for section in sections)
        chunks = chunk_sections(sections)
        facts = [(fact, section.source_ref) for section in sections for fact in extract_facts(section.text)]
        digest = sha256(data).hexdigest()
        # Serialize commits and index mutations so search never sees half an ingestion.
        with self.lock:
            vectors = self.embedder.encode([chunk.text for chunk in chunks])
            result, ids = self.store.add_document(filename, digest, text, chunks, vectors, facts)
            try:
                self.index.add(ids, vectors)
            except Exception:
                self.index = VectorIndex(self.store.vector_rows())
        return result

    def ask(self, question: str) -> dict:
        with self.lock:
            if not self.index.index.ntotal:
                return {"answer": INSUFFICIENT, "sources": [], "retrieved": []}
            query_vector = self.embedder.encode([question])[0]
            ranked = self.index.search(query_vector, limit=4)
            ranked = [(id_, score) for id_, score in ranked if score >= 0.32]
            rows = self.store.chunks_by_ids([id_ for id_, _ in ranked])
        evidence = [{**rows[id_], "score": round(score, 3), "marker": f"S{n}"}
                    for n, (id_, score) in enumerate(ranked, start=1) if id_ in rows]
        if not evidence:
            return {"answer": INSUFFICIENT, "sources": [], "retrieved": []}
        response = self.llm.answer(question, evidence)
        cited = set(re.findall(r"\[(S\d+)\]", response))
        sources = [{k: value for k, value in item.items() if k != "text"} for item in evidence if item["marker"] in cited]
        if not sources and response != INSUFFICIENT:
            return {"answer": "The local model did not provide a verifiable citation. Try asking again or inspect the retrieved excerpts.",
                    "sources": [], "retrieved": evidence}
        return {"answer": response, "sources": sources, "retrieved": evidence}
