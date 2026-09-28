from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .stage6_main import app, _assert_http_origin
from .blender_service import validate_blender_path
from .config import load_settings
from .export_service import ExportError,create_export_job,create_project,export_file,list_export_sources,list_projects,load_project,process_export,project_for
from .task_store import store

SCRIPT = Path(__file__).resolve().parents[1] / "blender_scripts" / "export_project.py"
app.version = "0.7.0"


class SourceSpec(BaseModel):
    kind: str
    asset_id: str | None = None
    preparation_id: str | None = None
    customization_id: str | None = None
    revision_id: str | None = None
    session_id: str | None = None
    animation_id: str | None = None


class CreateProjectRequest(BaseModel):
    name: str = Field(default="Projeto Bodiez", min_length=1, max_length=80)
    source: SourceSpec


class ExportRequest(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["blend", "glb"])
    resolution: int = Field(default=1024)


def reg(method: str, path: str, fn, **kwargs) -> None:
    if not any(getattr(route,"path",None)==path and method in (getattr(route,"methods",None) or set()) for route in app.routes):
        app.add_api_route(path, fn, methods=[method], **kwargs)


def _api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, "Projeto ou exportação não encontrado.")
    return HTTPException(422, str(exc))


def _blender_path() -> str:
    path = load_settings().get("blender_path")
    if not path:
        raise HTTPException(409, "Configure o Blender antes de exportar.")
    try:
        validate_blender_path(path)
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc
    return path


async def export_sources(request: Request):
    _assert_http_origin(request); return {"items": list_export_sources()}


async def projects(request: Request):
    _assert_http_origin(request); return {"items": list_projects()}


async def create_project_route(request: Request, body: CreateProjectRequest):
    _assert_http_origin(request)
    try:
        workspace = create_project(body.source.model_dump(exclude_none=True), body.name)
        manifest = load_project(workspace.project_id)
    except Exception as exc:
        raise _api_error(exc) from exc
    return {"project_id": workspace.project_id, "project": manifest}


async def project_info(request: Request, project_id: str):
    _assert_http_origin(request)
    try: return load_project(project_id)
    except Exception as exc: raise _api_error(exc) from exc


async def project_manifest_file(request: Request, project_id: str):
    _assert_http_origin(request)
    try: project = project_for(project_id)
    except Exception as exc: raise _api_error(exc) from exc
    return FileResponse(project.manifest,media_type="application/json",filename=f"{project_id}.bodiez.json",headers={"Cache-Control":"no-store"})


async def project_source_blend(request: Request, project_id: str):
    _assert_http_origin(request)
    try: project = project_for(project_id)
    except Exception as exc: raise _api_error(exc) from exc
    return FileResponse(project.source_blend,media_type="application/octet-stream",filename="source.blend",headers={"Cache-Control":"no-store"})


async def start_export(request: Request, project_id: str, body: ExportRequest):
    _assert_http_origin(request); blender = _blender_path()
    try: job = create_export_job(project_id, body.formats, body.resolution)
    except Exception as exc: raise _api_error(exc) from exc
    task_id = uuid.uuid4().hex; await store.create(task_id)
    async def publish(event: dict) -> None: await store.publish(task_id, event)
    asyncio.create_task(process_export(blender, SCRIPT, job, publish))
    return {"task_id":task_id,"project_id":project_id,"export_id":job.export_id}


async def download_export(request: Request, project_id: str, export_id: str, fmt: str):
    _assert_http_origin(request)
    try: path = export_file(project_id, export_id, fmt)
    except (ExportError, FileNotFoundError) as exc: raise _api_error(exc) from exc
    media={"blend":"application/octet-stream","glb":"model/gltf-binary","fbx":"application/octet-stream","png":"image/png","report":"application/json"}.get(fmt.lower(),"application/octet-stream")
    return FileResponse(path,media_type=media,filename=path.name,headers={"Cache-Control":"no-store"})


reg("GET","/api/stage7/sources",export_sources)
reg("GET","/api/stage7/projects",projects)
reg("POST","/api/stage7/projects",create_project_route,status_code=201)
reg("GET","/api/stage7/projects/{project_id}",project_info)
reg("GET","/api/stage7/projects/{project_id}/project.bodiez.json",project_manifest_file)
reg("GET","/api/stage7/projects/{project_id}/source.blend",project_source_blend)
reg("POST","/api/stage7/projects/{project_id}/exports",start_export,status_code=202)
reg("GET","/api/stage7/projects/{project_id}/exports/{export_id}/files/{fmt}",download_export)
