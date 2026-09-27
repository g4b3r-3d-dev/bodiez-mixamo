from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.preparation_service import PreparationValidationError, create_preparation_workspace, run_blender_preparation


def make_glb_bytes() -> bytes:
    return b"glTF" + (2).to_bytes(4, "little") + (32).to_bytes(4, "little") + b"\x00" * 20


def make_ready_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    data = tmp_path / "data"
    monkeypatch.setenv("BODIEZ_DATA_DIR", str(data))
    asset_id = "a" * 32
    root = data / "assets" / asset_id
    (root / "working").mkdir(parents=True)
    source = root / "working" / "character.glb"
    source.write_bytes(make_glb_bytes())
    (root / "manifest.json").write_text(json.dumps({"asset_id": asset_id, "status": "ready", "original_name": "character.glb"}), encoding="utf-8")
    return asset_id, source


def test_existing_preparation_workspace_preserves_stage2_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_id, source = make_ready_asset(tmp_path, monkeypatch)
    before = source.read_bytes()
    workspace = asyncio.run(create_preparation_workspace(asset_id, "existing_bound"))
    assert workspace.source_model == source
    assert workspace.source_model.read_bytes() == before
    manifest = json.loads(workspace.manifest_json.read_text(encoding="utf-8"))
    assert manifest["notes"]["weight_transfer_is_not_retargeting"] is True


def test_adapt_workspace_accepts_blend_and_preserves_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_id, _ = make_ready_asset(tmp_path, monkeypatch)
    blend_bytes = b"BLENDER-v300" + b"body-data"
    base = UploadFile(filename="bodiez.blend", file=io.BytesIO(blend_bytes))
    workspace = asyncio.run(create_preparation_workspace(asset_id, "adapt_base", base=base, options={"scale": 1.1, "offset_z": 0.05, "rotation_z": 2.0}))
    assert workspace.base_original is not None and workspace.base_working is not None
    assert workspace.base_original.read_bytes() == blend_bytes
    assert workspace.base_working.read_bytes() == blend_bytes


def test_adapt_workspace_rejects_fake_blend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_id, _ = make_ready_asset(tmp_path, monkeypatch)
    base = UploadFile(filename="bodiez.blend", file=io.BytesIO(b"not-a-blend"))
    with pytest.raises(PreparationValidationError, match="cabeçalho Blender"):
        asyncio.run(create_preparation_workspace(asset_id, "adapt_base", base=base))


def test_preparation_orchestration_with_fake_blender(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_id, _ = make_ready_asset(tmp_path, monkeypatch)
    workspace = asyncio.run(create_preparation_workspace(asset_id, "existing_bound"))
    fake_blender = tmp_path / "blender"
    fake_blender.write_text(r'''#!/usr/bin/env python3
import json, pathlib, sys
if '--version' in sys.argv:
 print('Blender 4.5.3'); raise SystemExit(0)
a=sys.argv[sys.argv.index('--')+1:]; v={a[i]:a[i+1] for i in range(0,len(a),2)}
pathlib.Path(v['--preview']).parent.mkdir(parents=True,exist_ok=True); pathlib.Path(v['--preview']).write_bytes(b'glTF'+b'0'*64); pathlib.Path(v['--blend']).write_bytes(b'BLENDER-v300prepared')
r={'mode':v['--mode'],'ready_for_body_customization':True,'target_rig':{'armature':'Armature','likely_mixamo':True,'semantic_matches':{}},'base_inspection':None,'alignment':{'performed':False},'binding':{'already_bound':True,'weight_transfer_performed':False,'weight_transfer_is_retargeting':False,'meshes':[]},'preservation':{'topology_preserved':True,'shape_keys_preserved':0,'destructive_modifiers_applied':False},'joint_validation':{'all_passed':True,'regions':{}},'blockers':[],'warnings':[],'limitations':[]}
pathlib.Path(v['--report']).write_text(json.dumps(r)); print('BODIEZ_RESULT:'+json.dumps({'ok':True,'ready':True}))
''', encoding="utf-8")
    fake_blender.chmod(0o755)
    internal_script = tmp_path / "prepare_body.py"; internal_script.write_text("# internal\n")
    events: list[dict] = []
    async def publish(event: dict) -> None: events.append(event)
    asyncio.run(run_blender_preparation(str(fake_blender), internal_script, workspace, publish, timeout_seconds=5))
    assert events[-1]["type"] == "success"
    assert workspace.prepared_blend.is_file() and workspace.preview_glb.is_file()
