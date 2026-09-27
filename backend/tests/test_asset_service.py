from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.asset_service import (
    AssetValidationError,
    create_asset_workspace,
    run_blender_import,
)


def make_glb_bytes() -> bytes:
    # Signature/version/declared length followed by harmless padding. The backend only validates the GLB header;
    # the real Blender importer performs full semantic validation during processing.
    return b"glTF" + (2).to_bytes(4, "little") + (32).to_bytes(4, "little") + b"\x00" * 20


def test_preserves_original_and_creates_working_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BODIEZ_DATA_DIR", str(tmp_path / "data"))
    upload = UploadFile(filename="character.glb", file=io.BytesIO(make_glb_bytes()))
    workspace = asyncio.run(create_asset_workspace(upload, []))

    assert workspace.original_model.read_bytes() == make_glb_bytes()
    assert workspace.working_model.read_bytes() == make_glb_bytes()
    assert workspace.original_model != workspace.working_model
    manifest = json.loads(workspace.manifest_json.read_text(encoding="utf-8"))
    assert manifest["original_preserved"] is True
    assert manifest["status"] == "queued"


def test_rejects_remote_gltf_resources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BODIEZ_DATA_DIR", str(tmp_path / "data"))
    gltf = json.dumps({
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "https://example.com/model.bin", "byteLength": 4}],
    }).encode()
    upload = UploadFile(filename="character.gltf", file=io.BytesIO(gltf))
    with pytest.raises(AssetValidationError, match="remotos/URLs"):
        asyncio.run(create_asset_workspace(upload, []))


def test_rejects_missing_flat_gltf_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BODIEZ_DATA_DIR", str(tmp_path / "data"))
    gltf = json.dumps({
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "character.bin", "byteLength": 4}],
    }).encode()
    upload = UploadFile(filename="character.gltf", file=io.BytesIO(gltf))
    with pytest.raises(AssetValidationError, match="não foram selecionados"):
        asyncio.run(create_asset_workspace(upload, []))


def test_full_import_orchestration_with_fake_blender(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BODIEZ_DATA_DIR", str(tmp_path / "data"))
    upload = UploadFile(filename="character.glb", file=io.BytesIO(make_glb_bytes()))
    workspace = asyncio.run(create_asset_workspace(upload, []))

    fake_blender = tmp_path / "blender"
    fake_blender.write_text(
        r'''#!/usr/bin/env python3
import json
import pathlib
import sys
if '--version' in sys.argv:
    print('Blender 4.5.3')
    raise SystemExit(0)
args = sys.argv[sys.argv.index('--') + 1:]
values = {args[i]: args[i + 1] for i in range(0, len(args), 2)}
pathlib.Path(values['--preview']).write_bytes(b'glTF' + b'0' * 64)
report = {
  'source': {'name': pathlib.Path(values['--source']).name, 'format': 'glb'},
  'summary': {'mesh_count': 1, 'armature_count': 1, 'material_count': 1, 'shape_key_count': 0, 'action_count': 0, 'total_vertices': 10, 'total_polygons': 8, 'likely_mixamo': True},
  'scene': {'object_count': 2, 'unit_system': 'NONE', 'scale_length': 1.0},
  'meshes': [], 'armatures': [], 'materials': [],
  'animations': {'actions': [], 'nla_tracks': [], 'scene_frame_start': 1, 'scene_frame_end': 250, 'fps': 24},
  'limitations': []
}
pathlib.Path(values['--report']).write_text(json.dumps(report), encoding='utf-8')
print('fake import complete')
print('BODIEZ_RESULT:' + json.dumps({'ok': True}))
''',
        encoding="utf-8",
    )
    fake_blender.chmod(0o755)
    internal_script = tmp_path / "import_inspect.py"
    internal_script.write_text("# fixed internal script placeholder\n", encoding="utf-8")
    events: list[dict] = []

    async def publish(event: dict) -> None:
        events.append(event)

    asyncio.run(
        run_blender_import(
            str(fake_blender),
            internal_script,
            workspace,
            publish,
            timeout_seconds=5,
        )
    )

    assert events[-1]["type"] == "success"
    assert events[-1]["result"]["asset_id"] == workspace.asset_id
    assert events[-1]["result"]["inspection"]["summary"]["likely_mixamo"] is True
    assert workspace.preview_glb.is_file()
    manifest = json.loads(workspace.manifest_json.read_text(encoding="utf-8"))
    assert manifest["status"] == "ready"
