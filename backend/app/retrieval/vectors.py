from threading import RLock

import faiss
import numpy as np


DIM = 384


class VectorIndex:
    """Transient FAISS index rebuilt from durable SQLite vectors on every startup."""

    def __init__(self, rows: list[tuple[int, np.ndarray]]):
        self.lock = RLock()
        self.index = faiss.IndexIDMap2(faiss.IndexFlatIP(DIM))
        if rows:
            self.add([row[0] for row in rows], np.stack([row[1] for row in rows]))

    def add(self, ids: list[int], vectors: np.ndarray) -> None:
        if not ids:
            return
        matrix = np.ascontiguousarray(vectors, dtype=np.float32)
        if matrix.shape != (len(ids), DIM):
            raise ValueError("Expected 384-dimensional embeddings")
        if not np.isfinite(matrix).all():
            raise ValueError("Embedding contains a non-finite value")
        faiss.normalize_L2(matrix)
        with self.lock:
            self.index.add_with_ids(matrix, np.asarray(ids, dtype=np.int64))

    def search(self, query: np.ndarray, limit: int = 4) -> list[tuple[int, float]]:
        matrix = np.ascontiguousarray(np.asarray(query, dtype=np.float32).reshape(1, -1))
        if matrix.shape[1] != DIM:
            raise ValueError("Expected 384-dimensional query")
        faiss.normalize_L2(matrix)
        with self.lock:
            scores, ids = self.index.search(matrix, limit)
        return [(int(i), float(score)) for i, score in zip(ids[0], scores[0]) if i != -1]


class LocalEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self.lock = RLock()

    def encode(self, texts: list[str]) -> np.ndarray:
        with self.lock:
            if not texts:
                return np.empty((0, DIM), dtype=np.float32)

            try:
                if self.model is None:
                    from transformers import AutoModel, AutoTokenizer

                    try:
                        tokenizer = AutoTokenizer.from_pretrained(
                            self.model_name, trust_remote_code=False, local_files_only=True
                        )
                        model = AutoModel.from_pretrained(
                            self.model_name, trust_remote_code=False, local_files_only=True
                        )
                    except OSError:
                        # Only fetch model files when they are not already cached locally.
                        tokenizer = AutoTokenizer.from_pretrained(
                            self.model_name, trust_remote_code=False, local_files_only=False
                        )
                        model = AutoModel.from_pretrained(
                            self.model_name, trust_remote_code=False, local_files_only=False
                        )
                    self.tokenizer = tokenizer
                    self.model = model.to("cpu").eval()

                import torch

                batches = []
                for start in range(0, len(texts), 16):
                    encoded = self.tokenizer(
                        texts[start:start + 16], padding=True, truncation=True,
                        max_length=256, return_tensors="pt",
                    )
                    with torch.no_grad():
                        token_embeddings = self.model(**encoded)[0].float()
                        mask = encoded["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
                        pooled = torch.sum(token_embeddings * mask, dim=1) / torch.clamp(
                            mask.sum(dim=1), min=1e-9
                        )
                        normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
                    batch = normalized.cpu().numpy().astype(np.float32, copy=False)
                    if batch.shape != (len(texts[start:start + 16]), DIM) or not np.isfinite(batch).all():
                        raise ValueError("Embedding output has invalid dimensions or values")
                    batches.append(batch)
                return np.concatenate(batches, axis=0)
            except Exception as exc:
                raise RuntimeError(
                    "Embedding model failed to load or run. Install backend dependencies and allow the "
                    "initial all-MiniLM-L6-v2 download; later runs use the local cache."
                ) from exc
