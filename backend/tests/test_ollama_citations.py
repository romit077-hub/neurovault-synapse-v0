import json

import httpx

from app.llm.ollama import INSUFFICIENT, OllamaClient


EVIDENCE = [{
    "marker": "S1", "filename": "assignment-original.txt", "source_ref": "text",
    "text": "Machine Learning assignment deadline is 14 October 2026.",
}]
QUESTION = "What is the Machine Learning assignment deadline?"
UNCITED = "The Machine Learning assignment deadline is 14 October 2026."
CITED = UNCITED + " [S1]"


def mock_chat(monkeypatch, answers):
    requests = []
    pending = list(answers)
    real_client = httpx.Client

    def respond(request):
        assert request.url.path == "/api/chat"
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": pending.pop(0)}})

    def client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr("app.llm.ollama.httpx.Client", client)
    monkeypatch.setattr(OllamaClient, "status", lambda self: {"available": True})
    return OllamaClient("http://127.0.0.1:11434", "qwen2.5:3b"), requests, pending


def test_cited_first_answer_makes_one_request(monkeypatch):
    llm, requests, pending = mock_chat(monkeypatch, [CITED])
    assert llm.answer(QUESTION, EVIDENCE) == CITED
    assert len(requests) == 1
    assert not pending
    assert requests[0]["model"] == "qwen2.5:3b"
    assert requests[0]["options"]["temperature"] == 0
    assert "Every factual sentence" in requests[0]["messages"][0]["content"]
    assert "Available markers: [S1]" in requests[0]["messages"][1]["content"]


def test_uncited_first_answer_is_rewritten_once(monkeypatch):
    llm, requests, pending = mock_chat(monkeypatch, [UNCITED, CITED])
    assert llm.answer(QUESTION, EVIDENCE) == CITED
    assert len(requests) == 2
    assert not pending
    repair = requests[1]["messages"][1]["content"]
    assert UNCITED in repair
    assert "Available markers: [S1]" in repair
    assert EVIDENCE[0]["text"] in repair
    assert "Do not answer the question from scratch or add any new facts" in repair


def test_twice_uncited_preserves_service_safe_refusal(monkeypatch, service, sample_text):
    llm, requests, pending = mock_chat(monkeypatch, [UNCITED, UNCITED])
    service.llm = llm
    service.ingest("assignment-original.txt", "text/plain", sample_text)
    result = service.ask(QUESTION)
    assert result["answer"].startswith("The local model did not provide a verifiable citation.")
    assert result["sources"] == []
    assert result["retrieved"][0]["marker"] == "S1"
    assert len(requests) == 2
    assert not pending


def test_foreign_marker_triggers_repair(monkeypatch):
    llm, requests, pending = mock_chat(monkeypatch, [UNCITED + " [S9]", CITED])
    assert llm.answer(QUESTION, EVIDENCE) == CITED
    assert len(requests) == 2
    assert not pending


def test_valid_and_foreign_markers_together_trigger_repair(monkeypatch):
    llm, requests, pending = mock_chat(monkeypatch, [CITED + " [S9]", CITED])
    assert llm.answer(QUESTION, EVIDENCE) == CITED
    assert len(requests) == 2
    assert not pending


def test_foreign_marker_after_retry_preserves_service_safe_refusal(monkeypatch, service, sample_text):
    llm, requests, pending = mock_chat(monkeypatch, [UNCITED + " [S9]", CITED + " [S9]"])
    service.llm = llm
    service.ingest("assignment-original.txt", "text/plain", sample_text)
    result = service.ask(QUESTION)
    assert result["answer"].startswith("The local model did not provide a verifiable citation.")
    assert result["sources"] == []
    assert len(requests) == 2
    assert not pending


def test_exact_insufficient_response_does_not_retry(monkeypatch):
    llm, requests, pending = mock_chat(monkeypatch, [INSUFFICIENT])
    assert llm.answer(QUESTION, EVIDENCE) == INSUFFICIENT
    assert len(requests) == 1
    assert not pending
