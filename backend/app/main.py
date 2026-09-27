from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .asset_service import (
    AssetValidationError,
    create_asset_workspace,
    load_asset_inspection,
    load_asset_manifest,
    resolve_asset_root,
    run_blender_import,
)
from .blender_service import BlenderValidationError, run_blender_connection_test, validate_blender_path
from .config import DEFAULT_FRONTEND_ORIGINS, discover_blender, load_settings, save_settings
from .models import AssetTaskResponse, BlenderPathRequest, BlenderTaskResponse, PreparationTaskResponse, SettingsResponse
from .preparation_service import (
    PreparationValidationError,
    create_preparation_workspace,
    load_preparation_report,
    resolve_preparation_root,
    run_blender_preparation,
)
from .task_store import store

app = FastAPI(title="Bodiez Local API", version="0.3.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
app.add_middleware(CORSMiddleware, allow_origins=sorted(DEFAULT_FRONTEND_ORIGINS), allow_credentials=False, allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type"])

BACKEND_DIR = Path(__file__).resolve().parents[1]
BLENDER_DIAGNOSTIC_SCRIPT = BACKEND_DIR / "blender_scripts" / "detect_blender.py"
BLENDER_IMPORT_SCRIPT = BACKEND_DIR / "blender_scripts" / "import_inspect.py"
BLENDER_PREPARATION_SCRIPT = BACKEND_DIR / "blender_scripts" / "prepare_body.py"


def _assert_http_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in DEFAULT_FRONTEND_ORIGINS:
        raise HTTPException(status_code=403, detail="Origem não permitida.")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings(request: Request) -> SettingsResponse:
    _assert_http_origin(request)
    settings = load_settings()
    return SettingsResponse(blender_path=settings.get("blender_path"), detected_path=discover_blender())


@app.put("/api/settings", response_model=SettingsResponse)
async def update_settings(request: Request, body: BlenderPathRequest) -> SettingsResponse:
    _assert_http_origin(request)
    try:
        path = validate_blender_path(body.executable_path)
    except BlenderValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_settings(str(path))
    return SettingsResponse(blender_path=str(path), detected_path=discover_blender())


@app.post("/api/blender/test", response_model=BlenderTaskResponse, status_code=202)
async def test_blender(request: Request, body: BlenderPathRequest) -> BlenderTaskResponse:
    _assert_http_origin(request)
    task_id = uuid.uuid4().hex
    await store.create(task_id)
    async def publish(event: dict) -> None: await store.publish(task_id, event)
    asyncio.create_task(run_blender_connection_test(body.executable_path, BLENDER_DIAGNOSTIC_SCRIPT, publish))
    return BlenderTaskResponse(task_id=task_id)


@app.post("/api/assets/import", response_model=AssetTaskResponse, status_code=202)
async def import_asset(request: Request, model: UploadFile = File(...), resources: list[UploadFile] = File(default=[])) -> AssetTaskResponse:
    _assert_http_origin(request)
    blender_path = load_settings().get("blender_path")
    if not blender_path:
        raise HTTPException(status_code=409, detail="Configure e teste o Blender antes de importar um personagem.")
    try:
        validate_blender_path(blender_path)
        workspace = await create_asset_workspace(model, resources)
    except (AssetValidationError, BlenderValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    task_id = uuid.uuid4().hex
    await store.create(task_id)
    async def publish(event: dict) -> None: await store.publish(task_id, event)
    asyncio.create_task(run_blender_import(blender_path, BLENDER_IMPORT_SCRIPT, workspace, publish))
    return AssetTaskResponse(asset_id=workspace.asset_id, task_id=task_id)


@app.get("/api/assets/{asset_id}")
async def get_asset(request: Request, asset_id: str) -> dict:
    _assert_http_origin(request)
    try:
        manifest = load_asset_manifest(asset_id); inspection = load_asset_inspection(asset_id)
    except AssetValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset não encontrado.") from exc
    return {"manifest": manifest, "inspection": inspection}


@app.get("/api/assets/{asset_id}/preview.glb")
async def get_asset_preview(request: Request, asset_id: str) -> FileResponse:
    _assert_http_origin(request)
    try: root = resolve_asset_root(asset_id)
    except AssetValidationError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc: raise HTTPException(status_code=404, detail="Asset não encontrado.") from exc
    preview = root / "preview" / "model.glb"
    if not preview.is_file(): raise HTTPException(status_code=404, detail="Visualização ainda não disponível.")
    return FileResponse(preview, media_type="model/gltf-binary", filename="model.glb", headers={"Cache-Control": "no-store"})


@app.post("/api/assets/{asset_id}/prepare/existing", response_model=PreparationTaskResponse, status_code=202)
async def prepare_existing_asset(request: Request, asset_id: str) -> PreparationTaskResponse:
    _assert_http_origin(request)
    blender_path = load_settings().get("blender_path")
    if not blender_path: raise HTTPException(status_code=409, detail="Configure e teste o Blender antes de preparar a base corporal.")
    try:
        validate_blender_path(blender_path); workspace = await create_preparation_workspace(asset_id, "existing_bound")
    except (PreparationValidationError, BlenderValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    task_id = uuid.uuid4().hex; await store.create(task_id)
    async def publish(event: dict) -> None: await store.publish(task_id, event)
    asyncio.create_task(run_blender_preparation(blender_path, BLENDER_PREPARATION_SCRIPT, workspace, publish))
    return PreparationTaskResponse(asset_id=asset_id, preparation_id=workspace.preparation_id, task_id=task_id)


@app.post("/api/assets/{asset_id}/prepare/adapt", response_model=PreparationTaskResponse, status_code=202)
async def prepare_adapted_base(request: Request, asset_id: str, base: UploadFile = File(...), resources: list[UploadFile] = File(default=[]), scale: float = Form(default=1.0), offset_x: float = Form(default=0.0), offset_y: float = Form(default=0.0), offset_z: float = Form(default=0.0), rotation_z: float = Form(default=0.0)) -> PreparationTaskResponse:
    _assert_http_origin(request)
    blender_path = load_settings().get("blender_path")
    if not blender_path: raise HTTPException(status_code=409, detail="Configure e teste o Blender antes de preparar a base corporal.")
    try:
        validate_blender_path(blender_path)
        workspace = await create_preparation_workspace(asset_id, "adapt_base", base=base, resources=resources, options={"scale": scale, "offset_x": offset_x, "offset_y": offset_y, "offset_z": offset_z, "rotation_z": rotation_z})
    except (PreparationValidationError, BlenderValidationError, AssetValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    task_id = uuid.uuid4().hex; await store.create(task_id)
    async def publish(event: dict) -> None: await store.publish(task_id, event)
    asyncio.create_task(run_blender_preparation(blender_path, BLENDER_PREPARATION_SCRIPT, workspace, publish))
    return PreparationTaskResponse(asset_id=asset_id, preparation_id=workspace.preparation_id, task_id=task_id)


@app.get("/api/assets/{asset_id}/preparations/{preparation_id}")
async def get_preparation(request: Request, asset_id: str, preparation_id: str) -> dict:
    _assert_http_origin(request)
    try: report = load_preparation_report(asset_id, preparation_id)
    except PreparationValidationError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc: raise HTTPException(status_code=404, detail="Preparação não encontrada.") from exc
    if report is None: raise HTTPException(status_code=404, detail="Relatório de preparação ainda não disponível.")
    return report


@app.get("/api/assets/{asset_id}/preparations/{preparation_id}/preview.glb")
async def get_preparation_preview(request: Request, asset_id: str, preparation_id: str) -> FileResponse:
    _assert_http_origin(request)
    try: root = resolve_preparation_root(asset_id, preparation_id)
    except PreparationValidationError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc: raise HTTPException(status_code=404, detail="Preparação não encontrada.") from exc
    preview = root / "output" / "prepared.glb"
    if not preview.is_file(): raise HTTPException(status_code=404, detail="Visualização preparada ainda não disponível.")
    return FileResponse(preview, media_type="model/gltf-binary", filename="prepared.glb", headers={"Cache-Control": "no-store"})


@app.get("/api/assets/{asset_id}/preparations/{preparation_id}/prepared.blend")
async def get_prepared_blend(request: Request, asset_id: str, preparation_id: str) -> FileResponse:
    _assert_http_origin(request)
    try: root = resolve_preparation_root(asset_id, preparation_id)
    except PreparationValidationError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc: raise HTTPException(status_code=404, detail="Preparação não encontrada.") from exc
    blend = root / "output" / "prepared.blend"
    if not blend.is_file(): raise HTTPException(status_code=404, detail="Arquivo preparado ainda não disponível.")
    return FileResponse(blend, media_type="application/octet-stream", filename="prepared.blend", headers={"Cache-Control": "no-store"})


@app.websocket("/ws/tasks/{task_id}")
async def task_socket(websocket: WebSocket, task_id: str) -> None:
    origin = websocket.headers.get("origin")
    if origin not in DEFAULT_FRONTEND_ORIGINS:
        await websocket.close(code=1008, reason="Origem não permitida"); return
    if not await store.exists(task_id):
        await websocket.close(code=1008, reason="Tarefa não encontrada"); return
    await websocket.accept(); history = await store.connect(task_id, websocket)
    try:
        for event in history: await websocket.send_json(event)
        while True: await websocket.receive_text()
    except WebSocketDisconnect: pass
    finally: await store.disconnect(task_id, websocket)
