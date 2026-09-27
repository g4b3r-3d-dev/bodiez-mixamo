from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module


def make_glb_bytes() -> bytes:
    return b"glTF" + (2).to_bytes(4, "little") + (32).to_bytes(4, "little") + b"\x00" * 20


def test_import_endpoint_accepts_valid_local_upload(tmp_path: Path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    data_dir = tmp_path / "data"
    fake_blender = tmp_path / "blender"
    fake_blender.write_text("#!/bin/sh\necho 'Blender 4.5.3'\n", encoding="utf-8")
    fake_blender.chmod(0o755)
    settings_path.write_text(json.dumps({"blender_path": str(fake_blender)}), encoding="utf-8")
    monkeypatch.setenv("BODIEZ_SETTINGS_PATH", str(settings_path))
    monkeypatch.setenv("BODIEZ_DATA_DIR", str(data_dir))

    async def fake_import(blender_path, script_path, workspace, publish, timeout_seconds=180.0):
        await publish({"type": "success", "message": "ok", "result": {"asset_id": workspace.asset_id}})

    monkeypatch.setattr(main_module, "run_blender_import", fake_import)
    client = TestClient(main_module.app, base_url="http://127.0.0.1")
    response = client.post(
        "/api/assets/import",
        files={"model": ("character.glb", make_glb_bytes(), "model/gltf-binary")},
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 202
    body = response.json()
    assert len(body["asset_id"]) == 32
    assert len(body["task_id"]) == 32
    original = data_dir / "assets" / body["asset_id"] / "original" / "character.glb"
    working = data_dir / "assets" / body["asset_id"] / "working" / "character.glb"
    assert original.read_bytes() == make_glb_bytes()
    assert working.read_bytes() == make_glb_bytes()


def test_import_endpoint_rejects_non_model_extension(tmp_path: Path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    fake_blender = tmp_path / "blender"
    fake_blender.write_text("#!/bin/sh\necho 'Blender 4.5.3'\n", encoding="utf-8")
    fake_blender.chmod(0o755)
    settings_path.write_text(json.dumps({"blender_path": str(fake_blender)}), encoding="utf-8")
    monkeypatch.setenv("BODIEZ_SETTINGS_PATH", str(settings_path))
    monkeypatch.setenv("BODIEZ_DATA_DIR", str(tmp_path / "data"))

    client = TestClient(main_module.app, base_url="http://127.0.0.1")
    response = client.post(
        "/api/assets/import",
        files={"model": ("payload.py", b"print('x')", "text/plain")},
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert response.status_code == 422
