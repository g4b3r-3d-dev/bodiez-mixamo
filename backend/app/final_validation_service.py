from __future__ import annotations

import asyncio
import json
import math
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from .blender_service import probe_blender_version, validate_blender_path
from .config import assets_root
from .export_service import ExportError, load_project, project_for

Publish = Callable[[dict], Awaitable[None]]
HEX = re.compile(r"^[0-9a-f]{32}$")


class FinalValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationRun:
    project_id: str
    validation_id: str
    export_id: str | None
    root: Path
    project_root: Path
    source_blend: Path
    request: Path
    blender_report: Path
    final_report: Path


def _safe_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _valid_id(value: str, label: str) -> str:
    if not HEX.fullmatch(value):
        raise FinalValidationError(f"{label} inválido.")
    return value


def _validation_root(project_id: str, validation_id: str) -> Path:
    _valid_id(project_id, "Projeto")
    _valid_id(validation_id, "Validação")
    root = assets_root() / "projects" / project_id / "validations" / validation_id
    if not root.is_dir():
        raise FileNotFoundError(validation_id)
    return root


def _export_root(project_id: str, export_id: str) -> Path:
    _valid_id(project_id, "Projeto")
    _valid_id(export_id, "Exportação")
    root = assets_root() / "projects" / project_id / "exports" / export_id
    if not root.is_dir():
        raise FileNotFoundError(export_id)
    return root


def list_validation_targets() -> list[dict]:
    projects_root = assets_root() / "projects"
    rows: list[dict] = []
    if not projects_root.is_dir():
        return rows
    for project_dir in projects_root.iterdir():
        if not project_dir.is_dir() or not HEX.fullmatch(project_dir.name):
            continue
        manifest = _safe_json(project_dir / "project.bodiez.json")
        source = project_dir / "source.blend"
        if manifest.get("format") != "bodiez-project" or not source.is_file():
            continue
        exports: list[dict] = []
        exports_root = project_dir / "exports"
        if exports_root.is_dir():
            for export_dir in exports_root.iterdir():
                if not export_dir.is_dir() or not HEX.fullmatch(export_dir.name):
                    continue
                report = _safe_json(export_dir / "report.json")
                files = {
                    "blend": (export_dir / "character-editable.blend").is_file(),
                    "glb": (export_dir / "character.glb").is_file(),
                    "fbx": (export_dir / "character.fbx").is_file(),
                    "png": (export_dir / "character.png").is_file(),
                }
                request = _safe_json(export_dir / "request.json")
                exports.append({
                    "export_id": export_dir.name,
                    "created_at": int(export_dir.stat().st_mtime),
                    "requested_formats": request.get("formats", []),
                    "files": files,
                    "has_report": bool(report),
                })
            exports.sort(key=lambda item: item["created_at"], reverse=True)
        rows.append({
            "project_id": project_dir.name,
            "name": manifest.get("name", "Projeto Bodiez"),
            "created_at": int(manifest.get("created_at", 0) or 0),
            "source": manifest.get("source", {}),
            "editability": manifest.get("editability", {}),
            "exports": exports,
        })
    rows.sort(key=lambda item: item["created_at"], reverse=True)
    return rows[:100]


def _project_checks(project_id: str) -> list[dict]:
    workspace = project_for(project_id)
    manifest = load_project(project_id)
    checks: list[dict] = []

    def add(key: str, label: str, status: str, evidence: str) -> None:
        checks.append({"key": key, "label": label, "status": status, "evidence": evidence})

    add("project_manifest", "Manifesto do projeto", "pass", "project.bodiez.json foi reaberto com format_version 1.")
    add("source_blend", "Cena autoritativa", "pass" if workspace.source_blend.is_file() else "fail", "source.blend existe dentro do diretório do projeto.")
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    file_ref = source.get("file_ref")
    add("relative_reference", "Referência de arquivo portátil", "pass" if file_ref == "source.blend" else "fail", f"file_ref={file_ref!r}; o esperado é 'source.blend'.")
    editability = manifest.get("editability") if isinstance(manifest.get("editability"), dict) else {}
    body = manifest.get("body") if isinstance(manifest.get("body"), dict) else {}
    body_recorded = bool(editability.get("body_parameters_recorded"))
    body_payload = bool(body.get("values") or body.get("bindings"))
    add("body_contract", "Parâmetros corporais", "pass" if body_recorded == body_payload else "warn", "Manifesto e flag de editabilidade corporal são coerentes." if body_recorded == body_payload else "A flag de parâmetros corporais não coincide com o payload salvo.")
    poses = manifest.get("poses") if isinstance(manifest.get("poses"), dict) else {}
    pose_recorded = bool(editability.get("pose_data_recorded"))
    add("pose_contract", "Dados de pose", "pass" if pose_recorded == bool(poses) else "warn", "Estado de pose é coerente com a flag do projeto." if pose_recorded == bool(poses) else "A flag de pose não coincide com os dados salvos.")
    animation = manifest.get("animation") if isinstance(manifest.get("animation"), dict) else {}
    animation_recorded = bool(editability.get("animation_data_recorded"))
    add("animation_contract", "Dados de animação", "pass" if animation_recorded == bool(animation) else "warn", "Estado de animação é coerente com a flag do projeto." if animation_recorded == bool(animation) else "A flag de animação não coincide com os dados salvos.")
    add("interchange_semantics", "Semântica de controles no intercâmbio", "pass" if editability.get("interchange_exports_retain_bodiez_control_semantics") is False else "warn", "GLB/FBX são tratados como intercâmbio, não como substitutos do projeto editável.")
    return checks


def _resolve_export_files(project_id: str, export_id: str | None) -> tuple[str | None, dict[str, str], dict]:
    if not export_id:
        return None, {}, {}
    root = _export_root(project_id, export_id)
    paths = {
        "blend": root / "character-editable.blend",
        "glb": root / "character.glb",
        "fbx": root / "character.fbx",
        "png": root / "character.png",
    }
    files = {key: str(path) for key, path in paths.items() if path.is_file()}
    return export_id, files, _safe_json(root / "report.json")


def create_validation_run(project_id: str, export_id: str | None = None) -> ValidationRun:
    project = project_for(_valid_id(project_id, "Projeto"))
    if export_id is not None:
        _valid_id(export_id, "Exportação")
    chosen_export, export_files, export_report = _resolve_export_files(project_id, export_id)
    project_checks = _project_checks(project_id)
    if chosen_export:
        export_request = _safe_json(project.root / "exports" / chosen_export / "request.json")
        same_project = str(export_request.get("project_id", project_id)) == project_id
        requested = [str(value).lower() for value in export_request.get("formats", [])] if isinstance(export_request.get("formats"), list) else []
        missing_outputs = [fmt for fmt in requested if fmt in {"blend", "glb", "fbx", "png"} and fmt not in export_files]
        project_checks.append({"key": "export_lineage", "label": "Linhagem da exportação", "status": "pass" if same_project else "fail", "evidence": "A exportação selecionada pertence ao projeto reaberto." if same_project else "O request da exportação referencia outro projeto."})
        project_checks.append({"key": "export_completeness", "label": "Arquivos solicitados na Etapa 7", "status": "pass" if not missing_outputs else "warn", "evidence": "Todos os formatos solicitados que podem ser validados estão presentes." if not missing_outputs else "Saídas solicitadas ausentes: " + ", ".join(missing_outputs)})
    validation_id = uuid.uuid4().hex
    root = project.root / "validations" / validation_id
    root.mkdir(parents=True, exist_ok=False)
    request = root / "request.json"
    blender_report = root / "blender-report.json"
    final_report = root / "final-report.json"
    _write_json(request, {
        "format_version": 1,
        "project_id": project_id,
        "validation_id": validation_id,
        "export_id": chosen_export,
        "source_blend": str(project.source_blend),
        "export_files": export_files,
        "stage7_report": export_report,
        "project_checks": project_checks,
    })
    return ValidationRun(project_id, validation_id, chosen_export, root, project.root, project.source_blend, request, blender_report, final_report)


def _normalize_check(raw: dict, group: str) -> dict:
    status = str(raw.get("status", "warn")).lower()
    if status not in {"pass", "warn", "fail"}:
        status = "warn"
    return {
        "group": group,
        "key": str(raw.get("key", "unknown")),
        "label": str(raw.get("label", raw.get("key", "Verificação"))),
        "status": status,
        "evidence": str(raw.get("evidence", "")),
        "metrics": raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {},
    }


def build_final_report(run: ValidationRun, blender_data: dict) -> dict:
    request = _safe_json(run.request)
    checks: list[dict] = []
    for raw in request.get("project_checks", []):
        if isinstance(raw, dict):
            checks.append(_normalize_check(raw, "project"))
    for group in ("scene", "deformation", "exports", "resources"):
        values = blender_data.get(group, [])
        if isinstance(values, list):
            for raw in values:
                if isinstance(raw, dict):
                    checks.append(_normalize_check(raw, group))
    failures = [item for item in checks if item["status"] == "fail"]
    warnings = [item for item in checks if item["status"] == "warn"]
    verdict = "blocked" if failures else ("pass_with_warnings" if warnings else "pass")
    limitations = blender_data.get("limitations") if isinstance(blender_data.get("limitations"), list) else []
    stage7_report = request.get("stage7_report") if isinstance(request.get("stage7_report"), dict) else {}
    for warning in stage7_report.get("warnings", []) if isinstance(stage7_report.get("warnings"), list) else []:
        if isinstance(warning, dict) and warning.get("message"):
            limitations.append(str(warning["message"]))
    limitations = list(dict.fromkeys(str(item) for item in limitations if item))
    report = {
        "format_version": 1,
        "project_id": run.project_id,
        "validation_id": run.validation_id,
        "export_id": run.export_id,
        "created_at": int(time.time()),
        "verdict": verdict,
        "summary": {
            "passed": sum(item["status"] == "pass" for item in checks),
            "warnings": len(warnings),
            "failures": len(failures),
            "total": len(checks),
        },
        "checks": checks,
        "metrics": blender_data.get("metrics", {}),
        "limitations": limitations,
        "flow": {
            "import": "verified_by_project_lineage",
            "customize": "verified_when_body_state_is_recorded",
            "pose": "verified_when_pose_state_is_recorded",
            "animate": "verified_when_animation_state_is_recorded",
            "save": "project_manifest_and_source_blend_reopened",
            "reopen": "source_blend_opened_by_blender",
            "export": "selected_stage7_export_compared_when_available",
        },
    }
    _write_json(run.final_report, report)
    return report


async def _stream(stream: asyncio.StreamReader | None, stream_name: str, publish: Publish) -> None:
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
                await publish({"type": "progress", "value": value, "message": parts[2]})
            continue
        if text.startswith("BODIEZ_RESULT:"):
            continue
        await publish({"type": "log", "level": "info" if stream_name == "stdout" else "warning", "stream": stream_name, "message": text})


async def process_validation(raw_blender_path: str, script: Path, run: ValidationRun, publish: Publish, timeout: float = 600.0) -> None:
    try:
        executable = validate_blender_path(raw_blender_path)
        version = await probe_blender_version(executable)
        await publish({"type": "progress", "value": 5, "message": f"Reabrindo projeto no Blender {version}..."})
        if not script.is_file():
            raise RuntimeError("Script interno de validação final não encontrado.")
        process = await asyncio.create_subprocess_exec(
            str(executable), "--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1", "--python", str(script), "--", str(run.request), str(run.blender_report),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout = asyncio.create_task(_stream(process.stdout, "stdout", publish))
        stderr = asyncio.create_task(_stream(process.stderr, "stderr", publish))
        try:
            code = await asyncio.wait_for(process.wait(), timeout)
        except TimeoutError:
            process.kill(); await process.wait(); await asyncio.gather(stdout, stderr, return_exceptions=True)
            raise RuntimeError("A validação final excedeu o limite de tempo.")
        await asyncio.gather(stdout, stderr, return_exceptions=True)
        if code != 0:
            raise RuntimeError(f"O Blender encerrou a validação com código {code}.")
        blender_data = _safe_json(run.blender_report)
        if not blender_data:
            raise RuntimeError("O Blender não produziu o relatório esperado.")
        report = build_final_report(run, blender_data)
        message = {"pass": "Validação final aprovada.", "pass_with_warnings": "Validação final aprovada com avisos.", "blocked": "Validação final encontrou bloqueadores."}[report["verdict"]]
        await publish({"type": "success", "message": message, "result": report})
    except Exception as exc:
        await publish({"type": "error", "message": str(exc), "code": "FINAL_VALIDATION_ERROR"})


def validation_report(project_id: str, validation_id: str) -> dict:
    root = _validation_root(project_id, validation_id)
    report = _safe_json(root / "final-report.json")
    if not report:
        raise FileNotFoundError(validation_id)
    return report


def validation_report_path(project_id: str, validation_id: str) -> Path:
    root = _validation_root(project_id, validation_id)
    path = root / "final-report.json"
    if not path.is_file():
        raise FileNotFoundError(validation_id)
    return path


def validation_preview(project_id: str, export_id: str | None) -> Path | None:
    if not export_id:
        return None
    root = _export_root(project_id, export_id)
    path = root / "character.glb"
    return path if path.is_file() else None
