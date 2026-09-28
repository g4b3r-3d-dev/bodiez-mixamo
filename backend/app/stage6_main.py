from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .stage5_main import app, _assert_http_origin
from .blender_service import validate_blender_path
from .config import load_settings
from .live_update_service import (
    LiveUpdateError,
    create_live_update,
    process_live_update,
    resolve_live_preview,
)
from .task_store import store

SCRIPT = Path(__file__).resolve().parents[1] / 'blender_scripts' / 'body_customize.py'
app.version = '0.6.0'


class LiveUpdateRequest(BaseModel):
    client_token: str = Field(min_length=32, max_length=32)
    generation: int = Field(ge=1, le=2_000_000_000)
    values: dict[str, float] = Field(default_factory=dict)
    bindings: dict[str, str] = Field(default_factory=dict)


def reg(method: str, path: str, fn, **kwargs) -> None:
    if not any(
        getattr(route, 'path', None) == path and method in (getattr(route, 'methods', None) or set())
        for route in app.routes
    ):
        app.add_api_route(path, fn, methods=[method], **kwargs)


def _api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, 'Prévia da Etapa 6 não encontrada.')
    return HTTPException(422, str(exc))


def _blender_path() -> str:
    path = load_settings().get('blender_path')
    if not path:
        raise HTTPException(409, 'Configure o Blender antes de sincronizar alterações estruturais.')
    try:
        validate_blender_path(path)
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc
    return path


async def live_update(
    request: Request,
    asset_id: str,
    preparation_id: str,
    customization_id: str,
    body: LiveUpdateRequest,
):
    _assert_http_origin(request)
    blender = _blender_path()
    try:
        update = create_live_update(
            asset_id,
            preparation_id,
            customization_id,
            body.client_token,
            body.generation,
            body.values,
            body.bindings,
        )
    except Exception as exc:
        raise _api_error(exc) from exc

    task_id = uuid.uuid4().hex
    await store.create(task_id)

    async def publish(event: dict) -> None:
        await store.publish(task_id, event)

    asyncio.create_task(process_live_update(blender, SCRIPT, update, publish))
    return {
        'task_id': task_id,
        'generation': update.generation,
        'stale_on_arrival': update.stale_on_arrival,
    }


async def live_preview(
    request: Request,
    asset_id: str,
    preparation_id: str,
    customization_id: str,
    client_token: str,
    generation: int,
):
    _assert_http_origin(request)
    try:
        preview = resolve_live_preview(
            asset_id,
            preparation_id,
            customization_id,
            client_token,
            generation,
        )
    except (LiveUpdateError, ValueError, FileNotFoundError) as exc:
        raise _api_error(exc) from exc
    if not preview.is_file():
        raise HTTPException(404, 'Prévia estrutural ainda não disponível.')
    return FileResponse(
        preview,
        media_type='model/gltf-binary',
        filename='stage6-live-preview.glb',
        headers={'Cache-Control': 'no-store'},
    )


reg(
    'POST',
    '/api/stage6/assets/{asset_id}/preparations/{preparation_id}/customizations/{customization_id}/live',
    live_update,
    status_code=202,
)
reg(
    'GET',
    '/api/stage6/assets/{asset_id}/preparations/{preparation_id}/customizations/{customization_id}/live/{client_token}/{generation}/preview.glb',
    live_preview,
)
