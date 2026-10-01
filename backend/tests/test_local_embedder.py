from unittest.mock import patch

import numpy as np
import pytest
import torch

from app.retrieval.vectors import DIM, LocalEmbedder, VectorIndex


class MockTokenizer:
    def __init__(self):
        self.calls = []

    def __call__(self, texts, **options):
        self.calls.append((len(texts), options))
        counts = [len(text.split()) + 2 for text in texts]
        width = max(counts)
        ids = torch.zeros((len(texts), width), dtype=torch.long)
        mask = torch.zeros_like(ids)
        for row, count in enumerate(counts):
            ids[row, :count] = torch.arange(1, count + 1)
            mask[row, :count] = 1
        return {"input_ids": ids, "attention_mask": mask}


class MockModel:
    def __init__(self):
        self.device = None
        self.eval_called = False
        self.grad_enabled_during_call = None

    def to(self, device):
        self.device = device
        return self

    def eval(self):
        self.eval_called = True
        return self

    def __call__(self, input_ids, attention_mask):
        self.grad_enabled_during_call = torch.is_grad_enabled()
        vectors = torch.nn.functional.one_hot(input_ids, num_classes=DIM).float()
        return (vectors,)


def test_embeds_single_and_multiple_inputs_without_downloading():
    tokenizer, model = MockTokenizer(), MockModel()
    with patch("transformers.AutoTokenizer.from_pretrained", return_value=tokenizer) as load_tokenizer, \
         patch("transformers.AutoModel.from_pretrained", return_value=model) as load_model:
        embedder = LocalEmbedder("sentence-transformers/all-MiniLM-L6-v2")
        single = embedder.encode(["NeuroVault test"])
        many = embedder.encode(["one", "two words", "three words here"] * 6)

    assert single.shape == (1, DIM)
    assert many.shape == (18, DIM)
    assert single.dtype == many.dtype == np.float32
    assert np.isfinite(single).all() and np.isfinite(many).all()
    np.testing.assert_allclose(np.linalg.norm(single, axis=1), 1.0, atol=1e-6)
    np.testing.assert_allclose(np.linalg.norm(many, axis=1), 1.0, atol=1e-6)
    assert [size for size, _ in tokenizer.calls] == [1, 16, 2]
    assert all(options == {"padding": True, "truncation": True, "max_length": 256, "return_tensors": "pt"}
               for _, options in tokenizer.calls)
    assert model.device == "cpu" and model.eval_called and model.grad_enabled_during_call is False
    assert load_tokenizer.call_count == load_model.call_count == 1
    assert load_tokenizer.call_args.kwargs == {"trust_remote_code": False, "local_files_only": True}
    assert load_model.call_args.kwargs == {"trust_remote_code": False, "local_files_only": True}


def test_padding_is_excluded_from_mean_pooling():
    tokenizer, model = MockTokenizer(), MockModel()
    with patch("transformers.AutoTokenizer.from_pretrained", return_value=tokenizer), \
         patch("transformers.AutoModel.from_pretrained", return_value=model):
        result = LocalEmbedder("sentence-transformers/all-MiniLM-L6-v2").encode(["one", "two words here"])
    expected = np.zeros(DIM, dtype=np.float32)
    expected[1:4] = 1 / np.sqrt(3)
    np.testing.assert_allclose(result[0], expected, atol=1e-6)
    assert result[1][0] == pytest.approx(0)


def test_cache_miss_downloads_once_and_empty_list_does_not_load():
    tokenizer, model = MockTokenizer(), MockModel()
    calls = []

    def load_tokenizer(name, **kwargs):
        calls.append(kwargs["local_files_only"])
        if kwargs["local_files_only"]:
            raise OSError("not cached")
        return tokenizer

    with patch("transformers.AutoTokenizer.from_pretrained", side_effect=load_tokenizer), \
         patch("transformers.AutoModel.from_pretrained", return_value=model) as load_model:
        embedder = LocalEmbedder("sentence-transformers/all-MiniLM-L6-v2")
        empty = embedder.encode([])
        assert empty.shape == (0, DIM) and empty.dtype == np.float32
        embedder.encode(["hello"])
        embedder.encode(["again"])
    assert calls == [True, False]
    assert load_model.call_args.kwargs["local_files_only"] is False


def test_load_failure_has_clear_runtime_error():
    with patch("transformers.AutoTokenizer.from_pretrained", side_effect=OSError("offline")):
        with pytest.raises(RuntimeError, match="Embedding model failed to load or run"):
            LocalEmbedder("sentence-transformers/all-MiniLM-L6-v2").encode(["test"])


def test_embeddings_remain_compatible_with_faiss():
    tokenizer, model = MockTokenizer(), MockModel()
    with patch("transformers.AutoTokenizer.from_pretrained", return_value=tokenizer), \
         patch("transformers.AutoModel.from_pretrained", return_value=model):
        vector = LocalEmbedder("sentence-transformers/all-MiniLM-L6-v2").encode(["retrieval test"])
    index = VectorIndex([(11, vector[0])])
    assert index.search(vector[0], limit=1)[0][0] == 11
    assert index.search(vector[0], limit=1)[0][1] == pytest.approx(1.0, abs=1e-5)
