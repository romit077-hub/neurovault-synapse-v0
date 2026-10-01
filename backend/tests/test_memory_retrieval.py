import pytest

from app.core.config import Settings
from app.core.service import Service
from app.db.store import DuplicateDocument
from app.memory.facts import extract_facts, normalize_value
from conftest import FakeEmbedder, FakeLLM


def test_retrieval_and_persistence(service, tmp_path, sample_text):
    result = service.ingest("assignment.txt", "text/plain", sample_text)
    assert result["chunk_count"] == 1
    answer = service.ask("Machine Learning assignment deadline")
    assert "14 October" in answer["answer"]
    assert answer["sources"][0]["filename"] == "assignment.txt"
    restarted = Service(Settings(tmp_path, "http://127.0.0.1:11434", "fake", "fake"), FakeEmbedder(), FakeLLM())
    assert restarted.store.dashboard()["documents"] == 1
    assert restarted.store.dashboard()["memories"] == 1
    assert restarted.ask("Machine Learning assignment deadline")["sources"]


def test_duplicate_document_and_fact_source(service, sample_text):
    service.ingest("one.txt", "text/plain", sample_text)
    with pytest.raises(DuplicateDocument):
        service.ingest("same.txt", "text/plain", sample_text)
    second = service.ingest("two.txt", "text/plain", sample_text + b"\nAdditional note.")
    assert second["events"][0]["classification"] == "DUPLICATE"
    assert len(service.store.memories()[0]["sources"]) == 2


def test_potential_update_requires_confirmation(service, sample_text):
    service.ingest("assignment-original.txt", "text/plain", sample_text)
    result = service.ingest("assignment-update.txt", "text/plain", b"The Machine Learning assignment deadline has been extended to 18 October 2026.")
    assert result["events"][0]["classification"] == "POTENTIAL_UPDATE"
    alert = service.store.alerts()[0]
    assert alert["status"] == "pending"
    assert "14 October" in alert["existing_value"]
    assert "18 October" in alert["new_value"]
    assert alert["existing_source"].startswith("assignment-original.txt")
    assert alert["new_source"].startswith("assignment-update.txt")
    assert service.store.dashboard()["memories"] == 1
    service.store.resolve_alert(alert["id"], "accept_update")
    memories = service.store.memories()
    assert any(m["value"].startswith("18 October") and m["status"] == "active" for m in memories)
    assert any(m["value"].startswith("14 October") and m["status"] == "superseded" for m in memories)


def test_contradiction_and_keep_both(service, sample_text):
    service.ingest("old.txt", "text/plain", sample_text)
    result = service.ingest("different.txt", "text/plain", b"Machine Learning assignment deadline is 19 October 2026.")
    assert result["events"][0]["classification"] == "CONTRADICTION"
    alert_id = service.store.alerts()[0]["id"]
    service.store.resolve_alert(alert_id, "keep_both")
    assert {m["status"] for m in service.store.memories()} == {"active", "coexisting"}


def test_keep_existing_does_not_create_new_memory(service, sample_text):
    service.ingest("old.txt", "text/plain", sample_text)
    service.ingest("new.txt", "text/plain", b"Machine Learning assignment deadline changed to 18 October 2026.")
    service.store.resolve_alert(service.store.alerts()[0]["id"], "keep_existing")
    assert service.store.dashboard()["memories"] == 1
    assert service.store.alerts()[0]["status"] == "keep_existing"


def test_stale_alert_cannot_replace_newer_decision(service, sample_text):
    service.ingest("old.txt", "text/plain", sample_text)
    service.ingest("update-a.txt", "text/plain", b"Machine Learning assignment deadline changed to 18 October 2026.")
    service.ingest("update-b.txt", "text/plain", b"Machine Learning assignment deadline changed to 19 October 2026.")
    first, second = sorted(service.store.alerts(), key=lambda a: a["created_at"] + a["id"])
    service.store.resolve_alert(first["id"], "accept_update")
    with pytest.raises(ValueError, match="has changed"):
        service.store.resolve_alert(second["id"], "accept_update")


def test_related_info_and_date_normalization(service, sample_text):
    service.ingest("one.txt", "text/plain", sample_text)
    related = service.ingest("room.txt", "text/plain", b"Machine Learning assignment room is B204.")
    assert related["events"][0]["classification"] == "RELATED_INFORMATION"
    assert normalize_value("14 October 2026") == "2026-10-14"
    assert extract_facts("Unstructured prose without a supported attribute.") == []
