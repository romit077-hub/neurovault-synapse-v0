from hashlib import sha256

import numpy as np
import pytest

from app.core.config import Settings
from app.core.service import Service


class FakeEmbedder:
    """Deterministic CPU vectors so tests never download a model."""

    def encode(self, texts):
        matrix = np.zeros((len(texts), 384), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in set(text.casefold().replace(".", "").split()):
                position = int.from_bytes(sha256(token.encode()).digest()[:2], "big") % 384
                matrix[row, position] += 1
            matrix[row] /= max(float(np.linalg.norm(matrix[row])), 1)
        return matrix


class FakeLLM:
    def status(self):
        return {"available": True, "running": True, "model": "fake", "message": "Ready"}

    def answer(self, question, evidence):
        return f"The indexed document says: {evidence[0]['text']} [S1]"


@pytest.fixture
def service(tmp_path):
    settings = Settings(tmp_path, "http://127.0.0.1:11434", "fake", "fake")
    return Service(settings, FakeEmbedder(), FakeLLM())


@pytest.fixture
def sample_text():
    return b"Machine Learning assignment deadline is 14 October 2026."
