from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient
import app.main as main_module


def make_glb_bytes() -> bytes:
    return b"glTF" + (2).to_bytes(4, "little") + (32).to_bytes(4, "little") + b"\x00" * 20


def setup_ready_asset(tmp_path: Path, monkeypatch) -> tuple[str, Path]:
    data_dir = tmp_path / "data"; asset_id = "b" * 32; root = data_dir / "assets" / asset_id
    (root / "working").mkdir(parents=True); (root / "working" / "character.glb").write_bytes(make_glb_bytes())
    (root / "manifest.json").write_text(json.dumps({"asset_id": asset_id, "status": "ready", "original_name": "character.glb"}), encoding="utf-8")
    fake_blender = tmp_path / "blender"; fake_blender.write_text("#!/bin/sh\necho 'Blender 4.5.3'\n", encoding="utf-8"); fake_blender.chmod(0o755)
    settings = tmp_path / "settings.json"; settings.write_text(json.dumps({"blender_path": str(fake_blender)}), encoding="utf-8")
    monkeypatch.setenv("BODIEZ_SETTINGS_PATH", str(settings)); monkeypatch.setenv("BODIEZ_DATA_DIR", str(data_dir))
    return asset_id, root


def test_existing_preparation_endpoint(tmp_path: Path, monkeypatch) -> None:
    asset_id, _ = setup_ready_asset(tmp_path, monkeypatch)
    async def fake_prepare(blender_path, script_path, workspace, publish, timeout_seconds=240.0):
        await publish({"type":"success","message":"ok","result":{"preparation_id":workspace.preparation_id}})
    monkeypatch.setattr(main_module, "run_blender_preparation", fake_prepare)
    client = TestClient(main_module.app, base_url="http://127.0.0.1")
    response = client.post(f"/api/assets/{asset_id}/prepare/existing", headers={"Origin":"http://127.0.0.1:5173"})
    assert response.status_code == 202 and len(response.json()["preparation_id"]) == 32


def test_adapt_endpoint_preserves_uploaded_base(tmp_path: Path, monkeypatch) -> None:
    asset_id, root = setup_ready_asset(tmp_path, monkeypatch)
    async def fake_prepare(blender_path, script_path, workspace, publish, timeout_seconds=240.0):
        await publish({"type":"success","message":"ok","result":{"preparation_id":workspace.preparation_id}})
    monkeypatch.setattr(main_module, "run_blender_preparation", fake_prepare)
    client = TestClient(main_module.app, base_url="http://127.0.0.1")
    blend = b"BLENDER-v300" + b"bodiez"
    response = client.post(f"/api/assets/{asset_id}/prepare/adapt", files={"base":("base.blend",blend,"application/octet-stream")}, data={"scale":"1.0","offset_x":"0","offset_y":"0","offset_z":"0","rotation_z":"0"}, headers={"Origin":"http://127.0.0.1:5173"})
    assert response.status_code == 202
    pid=response.json()["preparation_id"]
    assert (root/"preparations"/pid/"input"/"original"/"base.blend").read_bytes()==blend
