import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["BODIEZ_SETTINGS_PATH"] = "/tmp/bodiez-local-test-settings.json"

from app.main import app  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1")


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rejects_untrusted_origin() -> None:
    response = client.get("/api/settings", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_test_endpoint_returns_task_even_for_bad_path() -> None:
    response = client.post(
        "/api/blender/test",
        json={"executable_path": "/definitely/missing/blender"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 202
    assert len(response.json()["task_id"]) == 32
