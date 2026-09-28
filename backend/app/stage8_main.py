from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .stage7_main import app, _assert_http_origin
from .blender_service import validate_blender_path
from .config import load_settings
from .final_validation_service import create_validation_run,list_validation_targets,process_validation,validation_report,validation_report_path
from .task_store import store

SCRIPT = Path(__file__).resolve().parents[1] / "blender_scripts" / "final_validate.py"
app.version = "0.8.0"


class ValidationRequest(BaseModel):
    export_id: str | None = None


def reg(method: str, path: str, fn, **kwargs) -> None:
    if not any(getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or set()) for route in app.routes):
        app.add_api_route(path, fn, methods=[method], **kwargs)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, "Projeto, exportação ou validação não encontrada.")
    return HTTPException(422, str(exc))


def _blender_path() -> str:
    path = load_settings().get("blender_path")
    if not path:
        raise HTTPException(409, "Configure o Blender antes de executar a validação final.")
    try:
        validate_blender_path(path)
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc
    return path


async def targets(request: Request):
    _assert_http_origin(request)
    return {"items": list_validation_targets()}


async def start_validation(request: Request, project_id: str, body: ValidationRequest):
    _assert_http_origin(request)
    blender = _blender_path()
    try:
        run = create_validation_run(project_id, body.export_id)
    except Exception as exc:
        raise _error(exc) from exc
    task_id = uuid.uuid4().hex
    await store.create(task_id)
    async def publish(event: dict) -> None:
        await store.publish(task_id, event)
    asyncio.create_task(process_validation(blender, SCRIPT, run, publish))
    return {"task_id": task_id, "project_id": project_id, "validation_id": run.validation_id, "export_id": run.export_id}


async def report(request: Request, project_id: str, validation_id: str):
    _assert_http_origin(request)
    try:
        return validation_report(project_id, validation_id)
    except Exception as exc:
        raise _error(exc) from exc


async def report_file(request: Request, project_id: str, validation_id: str):
    _assert_http_origin(request)
    try:
        path = validation_report_path(project_id, validation_id)
    except Exception as exc:
        raise _error(exc) from exc
    return FileResponse(path, media_type="application/json", filename="bodiez-final-validation.json", headers={"Cache-Control": "no-store"})


reg("GET", "/api/stage8/targets", targets)
reg("POST", "/api/stage8/projects/{project_id}/validations", start_validation, status_code=202)
reg("GET", "/api/stage8/projects/{project_id}/validations/{validation_id}", report)
reg("GET", "/api/stage8/projects/{project_id}/validations/{validation_id}/report.json", report_file)
