from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from .blender_service import probe_blender_version, validate_blender_path
from .config import assets_root

Publish = Callable[[dict], Awaitable[None]]
HEX = re.compile(r"^[0-9a-f]{32}$")
PROJECT_NAME_RE = re.compile(r"^[^\x00/\\\\]{1,80}$")
EXPORT_FORMATS = {"blend", "glb", "fbx", "png"}
RENDER_RESOLUTIONS = {512, 1024, 2048}


class ExportError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectWorkspace:
    project_id: str
    root: Path
    source_blend: Path
    manifest: Path


@dataclass(frozen=True)
class ExportJob:
    project_id: str
    export_id: str
    root: Path
    source_blend: Path
    request: Path
    report: Path
    formats: tuple[str, ...]
    resolution: int


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _safe_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _valid_id(value: str, label: str) -> str:
    if not HEX.fullmatch(value):
        raise ExportError(f"{label} inválido.")
    return value


def _project_root(project_id: str) -> Path:
    _valid_id(project_id, "Projeto")
    root = assets_root() / "projects" / project_id
    if not root.is_dir():
        raise FileNotFoundError(project_id)
    return root


def _stage5_root() -> Path:
    return assets_root() / "stage5"


def _body_state_from_source(source: dict) -> dict:
    if source.get("kind") != "customization_revision":
        return {"editable": False, "values": {}, "bindings": {}}
    try:
        a = _valid_id(str(source["asset_id"]), "Asset")
        p = _valid_id(str(source["preparation_id"]), "Preparação")
        c = _valid_id(str(source["customization_id"]), "Personalização")
        r = _valid_id(str(source["revision_id"]), "Revisão")
    except (KeyError, ExportError):
        return {"editable": False, "values": {}, "bindings": {}}
    req = assets_root() / a / "preparations" / p / "customizations" / c / "revisions" / r / "request.json"
    data = _safe_json(req)
    values = data.get("values") if isinstance(data.get("values"), dict) else {}
    bindings = data.get("bindings") if isinstance(data.get("bindings"), dict) else {}
    return {"editable": bool(values or bindings), "values": values, "bindings": bindings}


def _source_from_stage5_metadata(session_root: Path) -> dict:
    source = _safe_json(session_root / "session.json").get("source")
    return source if isinstance(source, dict) else {}


def list_export_sources() -> list[dict]:
    rows: list[dict] = []
    root = assets_root()
    if root.exists():
        for asset_dir in root.iterdir():
            if not asset_dir.is_dir() or not HEX.fullmatch(asset_dir.name):
                continue
            preparations = asset_dir / "preparations"
            if not preparations.is_dir():
                continue
            for prep_dir in preparations.iterdir():
                if not prep_dir.is_dir() or not HEX.fullmatch(prep_dir.name):
                    continue
                report = _safe_json(prep_dir / "preparation.json")
                prepared = prep_dir / "output" / "prepared.blend"
                if report.get("ready_for_body_customization") and prepared.is_file():
                    rows.append({"kind":"preparation","asset_id":asset_dir.name,"preparation_id":prep_dir.name,"label":f"Base preparada · {asset_dir.name[:8]}","updated_at":int(prepared.stat().st_mtime),"has_animation":False,"has_pose":False,"body_editable":False})
                customizations = prep_dir / "customizations"
                if not customizations.is_dir():
                    continue
                for custom_dir in customizations.iterdir():
                    if not custom_dir.is_dir() or not HEX.fullmatch(custom_dir.name):
                        continue
                    revisions = custom_dir / "revisions"
                    if not revisions.is_dir():
                        continue
                    for rev_dir in revisions.iterdir():
                        if not rev_dir.is_dir() or not HEX.fullmatch(rev_dir.name):
                            continue
                        blend = rev_dir / "customized.blend"
                        if not blend.is_file():
                            continue
                        state = _safe_json(rev_dir / "request.json")
                        rows.append({"kind":"customization_revision","asset_id":asset_dir.name,"preparation_id":prep_dir.name,"customization_id":custom_dir.name,"revision_id":rev_dir.name,"label":f"Corpo personalizado · {asset_dir.name[:8]} · {rev_dir.name[:6]}","updated_at":int(blend.stat().st_mtime),"has_animation":False,"has_pose":False,"body_editable":bool(state.get("values") or state.get("bindings"))})
    stage5 = _stage5_root()
    if stage5.is_dir():
        for session_dir in stage5.iterdir():
            if not session_dir.is_dir() or not HEX.fullmatch(session_dir.name):
                continue
            lineage = _source_from_stage5_metadata(session_dir)
            pose_root = session_dir / "pose_revisions"
            if pose_root.is_dir():
                for rev_dir in pose_root.iterdir():
                    if not rev_dir.is_dir() or not HEX.fullmatch(rev_dir.name):
                        continue
                    blend = rev_dir / "posed.blend"
                    if blend.is_file():
                        rows.append({"kind":"pose_revision","session_id":session_dir.name,"revision_id":rev_dir.name,"label":f"Pose · sessão {session_dir.name[:6]} · {rev_dir.name[:6]}","updated_at":int(blend.stat().st_mtime),"has_animation":False,"has_pose":True,"body_editable":bool(_body_state_from_source(lineage).get("editable")),"lineage":lineage})
            anim_root = session_dir / "animations"
            if anim_root.is_dir():
                for anim_dir in anim_root.iterdir():
                    if not anim_dir.is_dir() or not HEX.fullmatch(anim_dir.name):
                        continue
                    blend = anim_dir / "retargeted.blend"
                    report = _safe_json(anim_dir / "report.json")
                    if blend.is_file() and report.get("status") == "ready":
                        rows.append({"kind":"animation_result","session_id":session_dir.name,"animation_id":anim_dir.name,"label":f"Animação retargeteada · {session_dir.name[:6]} · {anim_dir.name[:6]}","updated_at":int(blend.stat().st_mtime),"has_animation":True,"has_pose":False,"body_editable":bool(_body_state_from_source(lineage).get("editable")),"lineage":lineage})
    rows.sort(key=lambda item: item["updated_at"], reverse=True)
    return rows[:200]


def resolve_export_source(spec: dict) -> tuple[Path, dict, dict]:
    kind = str(spec.get("kind", ""))
    if kind in {"preparation", "customization_revision"}:
        a = _valid_id(str(spec.get("asset_id", "")), "Asset")
        p = _valid_id(str(spec.get("preparation_id", "")), "Preparação")
        prep = assets_root() / a / "preparations" / p
        if kind == "preparation":
            path = prep / "output" / "prepared.blend"
            report = _safe_json(prep / "preparation.json")
            if not report.get("ready_for_body_customization") or not path.is_file():
                raise ExportError("A preparação selecionada não está aprovada para exportação.")
            descriptor = {"kind": kind, "asset_id": a, "preparation_id": p}
            return path, descriptor, {"body":{"editable":False,"values":{},"bindings":{}},"poses":{},"animation":{}}
        c = _valid_id(str(spec.get("customization_id", "")), "Personalização")
        r = _valid_id(str(spec.get("revision_id", "")), "Revisão")
        rev = prep / "customizations" / c / "revisions" / r
        path = rev / "customized.blend"
        if not path.is_file():
            raise ExportError("A revisão corporal selecionada não existe.")
        descriptor = {"kind":kind,"asset_id":a,"preparation_id":p,"customization_id":c,"revision_id":r}
        return path, descriptor, {"body":_body_state_from_source(descriptor),"poses":{},"animation":{}}
    if kind in {"pose_revision", "animation_result"}:
        sid = _valid_id(str(spec.get("session_id", "")), "Sessão")
        session = _stage5_root() / sid
        if not session.is_dir():
            raise ExportError("Sessão da Etapa 5 não encontrada.")
        lineage = _source_from_stage5_metadata(session)
        body = _body_state_from_source(lineage)
        pose_library = _safe_json(session / "poses.json").get("poses", {})
        if kind == "pose_revision":
            rid = _valid_id(str(spec.get("revision_id", "")), "Revisão de pose")
            rev = session / "pose_revisions" / rid
            path = rev / "posed.blend"
            if not path.is_file():
                raise ExportError("Revisão de pose não encontrada.")
            descriptor = {"kind":kind,"session_id":sid,"revision_id":rid,"lineage":lineage}
            return path, descriptor, {"body":body,"poses":{"library":pose_library,"active":_safe_json(rev / "pose.json")},"animation":{}}
        aid = _valid_id(str(spec.get("animation_id", "")), "Animação")
        anim = session / "animations" / aid
        path = anim / "retargeted.blend"
        report = _safe_json(anim / "report.json")
        if not path.is_file() or report.get("status") != "ready":
            raise ExportError("A animação selecionada não está pronta para exportação.")
        descriptor = {"kind":kind,"session_id":sid,"animation_id":aid,"lineage":lineage}
        return path, descriptor, {"body":body,"poses":{"library":pose_library},"animation":{"manifest":_safe_json(anim / "manifest.json"),"report":report}}
    raise ExportError("Tipo de fonte de exportação inválido.")


def _clean_project_name(name: str | None) -> str:
    value = (name or "Projeto Bodiez").strip()
    if not PROJECT_NAME_RE.fullmatch(value):
        raise ExportError("Nome de projeto inválido.")
    return value


def create_project(spec: dict, name: str | None = None) -> ProjectWorkspace:
    source_path, descriptor, state = resolve_export_source(spec)
    project_id = uuid.uuid4().hex
    root = assets_root() / "projects" / project_id
    source_blend = root / "source.blend"
    manifest = root / "project.bodiez.json"
    root.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copy2(source_path, source_blend)
        project = {"format":"bodiez-project","format_version":1,"minimum_stage":7,"project_id":project_id,"name":_clean_project_name(name),"created_at":int(time.time()),"source":{**descriptor,"file_ref":"source.blend"},"body":state.get("body",{}),"poses":state.get("poses",{}),"animation":state.get("animation",{}),"files":{"source_blend":"source.blend"},"editability":{"authoritative_format":"blend","body_parameters_recorded":bool((state.get("body") or {}).get("editable")),"pose_data_recorded":bool(state.get("poses")),"animation_data_recorded":bool(state.get("animation")),"interchange_exports_retain_bodiez_control_semantics":False},"export_policy":{"editable":["blend"],"interchange":["glb","fbx"],"render":["png"]}}
        _atomic_json(manifest, project)
        return ProjectWorkspace(project_id, root, source_blend, manifest)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def list_projects() -> list[dict]:
    root = assets_root() / "projects"
    rows: list[dict] = []
    if not root.is_dir():
        return rows
    for project_dir in root.iterdir():
        if not project_dir.is_dir() or not HEX.fullmatch(project_dir.name):
            continue
        manifest = _safe_json(project_dir / "project.bodiez.json")
        if manifest.get("format") != "bodiez-project":
            continue
        rows.append({"project_id":project_dir.name,"name":manifest.get("name","Projeto Bodiez"),"created_at":int(manifest.get("created_at",0) or 0),"source":manifest.get("source",{}),"editability":manifest.get("editability",{})})
    rows.sort(key=lambda item: item["created_at"], reverse=True)
    return rows[:100]


def project_for(project_id: str) -> ProjectWorkspace:
    root = _project_root(project_id)
    source = root / "source.blend"
    manifest = root / "project.bodiez.json"
    if not source.is_file() or not manifest.is_file():
        raise FileNotFoundError(project_id)
    return ProjectWorkspace(project_id, root, source, manifest)


def load_project(project_id: str) -> dict:
    data = _safe_json(project_for(project_id).manifest)
    if data.get("format") != "bodiez-project" or data.get("format_version") != 1:
        raise ExportError("Formato de projeto Bodiez não suportado.")
    return data


def create_export_job(project_id: str, formats: list[str], resolution: int) -> ExportJob:
    project = project_for(project_id)
    clean = tuple(dict.fromkeys(str(fmt).lower() for fmt in formats))
    if not clean or any(fmt not in EXPORT_FORMATS for fmt in clean):
        raise ExportError("Escolha pelo menos um formato válido: blend, glb, fbx ou png.")
    if resolution not in RENDER_RESOLUTIONS:
        raise ExportError("Resolução PNG inválida. Use 512, 1024 ou 2048.")
    export_id = uuid.uuid4().hex
    root = project.root / "exports" / export_id
    root.mkdir(parents=True, exist_ok=False)
    request = root / "request.json"
    report = root / "report.json"
    _atomic_json(request,{"format_version":1,"project_id":project_id,"export_id":export_id,"formats":list(clean),"resolution":resolution,"outputs":{"blend":"character-editable.blend","glb":"character.glb","fbx":"character.fbx","png":"character.png"}})
    return ExportJob(project_id, export_id, root, project.source_blend, request, report, clean, resolution)


async def _export_stream(stream: asyncio.StreamReader | None, stream_name: str, publish: Publish) -> None:
    if stream is None:
        return
    while True:
        raw = await stream.readline()
        if not raw:
            return
        text = raw.decode("utf-8", errors="replace").rstrip()
        if not text:
            continue
        if text.startswith("BODIEZ_PROGRESS:"):
            parts = text.split(":", 2)
            if len(parts) == 3:
                try:
                    value = max(0, min(100, int(parts[1])))
                except ValueError:
                    value = 0
                await publish({"type":"progress","value":value,"message":parts[2]})
            continue
        if text.startswith("BODIEZ_RESULT:"):
            continue
        await publish({"type":"log","level":"info" if stream_name == "stdout" else "warning","stream":stream_name,"message":text})


async def _run(executable: Path, args: list[str], publish: Publish, timeout: float = 600.0) -> None:
    process = await asyncio.create_subprocess_exec(str(executable),*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    stdout = asyncio.create_task(_export_stream(process.stdout, "stdout", publish))
    stderr = asyncio.create_task(_export_stream(process.stderr, "stderr", publish))
    try:
        code = await asyncio.wait_for(process.wait(), timeout)
    except TimeoutError:
        process.kill(); await process.wait(); await asyncio.gather(stdout, stderr, return_exceptions=True)
        raise RuntimeError("O Blender excedeu o limite de tempo da exportação.")
    await asyncio.gather(stdout, stderr, return_exceptions=True)
    if code:
        raise RuntimeError(f"O Blender encerrou a exportação com código {code}.")


async def process_export(blender: str, script: Path, job: ExportJob, publish: Publish) -> None:
    try:
        executable = validate_blender_path(blender)
        version = await probe_blender_version(executable)
        await publish({"type":"progress","value":5,"message":f"Preparando exportação no Blender {version}..."})
        if not script.is_file():
            raise RuntimeError("Script interno de exportação não encontrado.")
        await _run(executable,["--background","--factory-startup","--disable-autoexec","--python-exit-code","1","--python",str(script),"--",str(job.source_blend),str(job.request),str(job.root),str(job.report)],publish)
        report = _safe_json(job.report)
        files: dict[str, str] = {}
        mapping = {"blend":"character-editable.blend","glb":"character.glb","fbx":"character.fbx","png":"character.png"}
        for fmt, filename in mapping.items():
            if fmt in job.formats and (job.root / filename).is_file():
                files[fmt] = f"/api/stage7/projects/{job.project_id}/exports/{job.export_id}/files/{fmt}"
        await publish({"type":"success","message":"Exportação concluída.","result":{"project_id":job.project_id,"export_id":job.export_id,"files":files,"report":report}})
    except Exception as exc:
        report = _safe_json(job.report) if job.report.is_file() else None
        await publish({"type":"error","message":str(exc),"code":"STAGE7_EXPORT_ERROR","result":{"report":report} if report else None})


def export_file(project_id: str, export_id: str, fmt: str) -> Path:
    project = project_for(project_id)
    _valid_id(export_id, "Exportação")
    fmt = fmt.lower()
    mapping = {"blend":"character-editable.blend","glb":"character.glb","fbx":"character.fbx","png":"character.png","report":"report.json"}
    if fmt not in mapping:
        raise ExportError("Formato de download inválido.")
    root = project.root / "exports" / export_id
    if not root.is_dir():
        raise FileNotFoundError(export_id)
    path = root / mapping[fmt]
    if not path.is_file():
        raise FileNotFoundError(path.name)
    return path
