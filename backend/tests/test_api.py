from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from conftest import FakeEmbedder, FakeLLM


def test_api_demo_flow(tmp_path):
    app = create_app(Settings(tmp_path, "http://127.0.0.1:11434", "fake", "fake"), FakeEmbedder(), FakeLLM())
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    first = client.post("/api/documents/upload", files={"file": ("original.txt", b"Machine Learning assignment deadline is 14 October 2026.", "text/plain")})
    assert first.status_code == 201
    assert client.get("/api/documents/" + first.json()["id"]).json()["extracted_text"]
    second = client.post("/api/documents/upload", files={"file": ("update.txt", b"The Machine Learning assignment deadline has been extended to 18 October 2026.", "text/plain")})
    assert second.status_code == 201
    assert client.get("/api/dashboard").json()["pending_alerts"] == 1
    alert = client.get("/api/alerts").json()[0]
    assert client.post(f"/api/alerts/{alert['id']}/resolve", json={"action": "keep_both"}).status_code == 200
    assert client.get("/api/dashboard").json()["memories"] == 2
    assert client.post("/api/ask", json={"question": "Machine Learning assignment deadline"}).json()["sources"]


def test_api_rejects_foreign_origin_and_bad_content(tmp_path):
    app = create_app(Settings(tmp_path, "http://127.0.0.1:11434", "fake", "fake"), FakeEmbedder(), FakeLLM())
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    assert client.post("/api/ask", json={"question": "some question"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/documents/upload", files={"file": ("test.pdf", b"plain text", "application/pdf")}).status_code == 400
    assert client.get("/api/documents/missing").status_code == 404
