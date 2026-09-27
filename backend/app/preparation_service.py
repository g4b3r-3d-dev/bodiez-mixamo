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

from fastapi import UploadFile

from .asset_service import (
    ASSET_ID_RE,
    MAX_MODEL_BYTES,
    MAX_RESOURCE_BYTES,
    MAX_TOTAL_RESOURCE_BYTES,
    RESOURCE_EXTENSIONS,
    AssetValidationError,
    _gltf_external_uris,
    _safe_filename,
    _validate_model_signature,
    _validate_resource_signature,
    _write_upload,
    load_asset_manifest,
    resolve_asset_root,
)
from .blender_service import (
    BlenderValidationError,
    _read_stream,
    probe_blender_version,
    validate_blender_path,
)

EventPublisher = Callable[[dict], Awaitable[None]]
PREPARATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
BASE_EXTENSIONS = {".fbx", ".glb", ".gltf", ".blend"}
MAX_BLEND_BYTES = 1024 * 1024 * 1024


class PreparationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PreparationWorkspace:
    asset_id: str
    preparation_id: str
    mode: str
    root: Path
    source_model: Path
    base_original: Path | None
    base_working: Path | None
    prepared_blend: Path
    preview_glb: Path
    report_json: Path
    manifest_json: Path
    options: dict[str, float]


def _validate_blend_signature(path: Path) -> None:
    with path.open("rb") as handle:
        header = handle.read(12)
    if not header.startswith(b"BLENDER"):
        raise PreparationValidationError("O arquivo .blend não possui um cabeçalho Blender reconhecível.")


def _validate_base_model(path: Path) -> None:
    if path.suffix.lower() == ".blend":
        _validate_blend_signature(path)
    else:
        try:
            _validate_model_signature(path)
        except AssetValidationError as exc:
            raise PreparationValidationError(str(exc)) from exc


def _load_source_model(asset_id: str) -> tuple[Path, dict]:
    try:
        manifest = load_asset_manifest(asset_id)
        root = resolve_asset_root(asset_id)
    except (AssetValidationError, FileNotFoundError) as exc:
        raise PreparationValidationError("O personagem importado não foi encontrado.") from exc

    if manifest.get("status") != "ready":
        raise PreparationValidationError("O personagem precisa concluir a Etapa 2 antes da preparação corporal.")
    original_name = manifest.get("original_name")
    if not isinstance(original_name, str) or not original_name:
        raise PreparationValidationError("O manifesto do personagem não contém o arquivo de trabalho.")
    source_model = root / "working" / original_name
    if not source_model.is_file():
        raise PreparationValidationError("A cópia de trabalho da Etapa 2 não foi encontrada.")
    return source_model, manifest


def _validate_options(options: dict[str, float]) -> dict[str, float]:
    normalized = {
        "scale": float(options.get("scale", 1.0)),
        "offset_x": float(options.get("offset_x", 0.0)),
        "offset_y": float(options.get("offset_y", 0.0)),
        "offset_z": float(options.get("offset_z", 0.0)),
        "rotation_z": float(options.get("rotation_z", 0.0)),
    }
    if not 0.25 <= normalized["scale"] <= 4.0:
        raise PreparationValidationError("A escala assistida deve ficar entre 0,25 e 4,0.")
    for axis in ("offset_x", "offset_y", "offset_z"):
        if not -10.0 <= normalized[axis] <= 10.0:
            raise PreparationValidationError("Os deslocamentos assistidos devem ficar entre -10 e 10 unidades.")
    if not -180.0 <= normalized["rotation_z"] <= 180.0:
        raise PreparationValidationError("A rotação Z deve ficar entre -180 e 180 graus.")
    return normalized


async def create_preparation_workspace(
    asset_id: str,
    mode: str,
    base: UploadFile | None = None,
    resources: list[UploadFile] | None = None,
    options: dict[str, float] | None = None,
) -> PreparationWorkspace:
    if not ASSET_ID_RE.fullmatch(asset_id):
        raise PreparationValidationError("Identificador de asset inválido.")
    if mode not in {"existing_bound", "adapt_base"}:
        raise PreparationValidationError("Modo de preparação inválido.")
    if mode == "existing_bound" and base is not None:
        raise PreparationValidationError("O modo de malha já vinculada não recebe uma base adicional.")
    if mode == "adapt_base" and base is None:
        raise PreparationValidationError("Selecione a base corporal que será adaptada ao esqueleto Mixamo.")

    source_model, _ = _load_source_model(asset_id)
    normalized_options = _validate_options(options or {})
    asset_root = resolve_asset_root(asset_id)
    preparation_id = uuid.uuid4().hex
    root = asset_root / "preparations" / preparation_id
    prepared_blend = root / "output" / "prepared.blend"
    preview_glb = root / "output" / "prepared.glb"
    report_json = root / "preparation.json"
    manifest_json = root / "manifest.json"
    base_original: Path | None = None
    base_working: Path | None = None
    resource_uploads = resources or []

    try:
        root.mkdir(parents=True, exist_ok=False)
        if mode == "adapt_base" and base is not None:
            base_name = _safe_filename(base.filename)
            extension = Path(base_name).suffix.lower()
            if extension not in BASE_EXTENSIONS:
                raise PreparationValidationError("A base corporal deve ser FBX, GLB, GLTF ou BLEND.")
            base_original = root / "input" / "original" / base_name
            limit = MAX_BLEND_BYTES if extension == ".blend" else MAX_MODEL_BYTES
            await _write_upload(base, base_original, limit)
            _validate_base_model(base_original)

            seen: set[str] = set()
            total_resource_bytes = 0
            for resource in resource_uploads:
                name = _safe_filename(resource.filename)
                resource_ext = Path(name).suffix.lower()
                if extension == ".blend":
                    raise PreparationValidationError("Arquivos .blend devem ser enviados sem dependências externas adicionais.")
                if resource_ext not in RESOURCE_EXTENSIONS:
                    raise PreparationValidationError(
                        f"Dependência '{name}' não é permitida. Use BIN, PNG, JPG, WEBP ou KTX2."
                    )
                if name in seen or name == base_name:
                    raise PreparationValidationError(f"Arquivo duplicado no envio: '{name}'.")
                seen.add(name)
                destination = root / "input" / "original" / name
                size = await _write_upload(resource, destination, MAX_RESOURCE_BYTES)
                _validate_resource_signature(destination)
                total_resource_bytes += size
                if total_resource_bytes > MAX_TOTAL_RESOURCE_BYTES:
                    raise PreparationValidationError("As dependências externas excedem o limite total de 1 GB.")

            if extension == ".gltf":
                try:
                    required = _gltf_external_uris(base_original)
                except AssetValidationError as exc:
                    raise PreparationValidationError(str(exc)) from exc
                missing = [name for name in required if name not in seen]
                if missing:
                    raise PreparationValidationError(
                        "O GLTF da base referencia arquivos externos não selecionados: " + ", ".join(missing)
                    )

            working_dir = root / "input" / "working"
            working_dir.mkdir(parents=True, exist_ok=True)
            base_working = working_dir / base_name
            shutil.copy2(base_original, base_working)
            for name in seen:
                shutil.copy2(root / "input" / "original" / name, working_dir / name)

        manifest = {
            "format_version": 1,
            "asset_id": asset_id,
            "preparation_id": preparation_id,
            "mode": mode,
            "created_at": int(time.time()),
            "status": "queued",
            "source_model": source_model.name,
            "base_original_name": base_original.name if base_original else None,
            "options": normalized_options,
            "notes": {
                "weight_transfer_is_not_retargeting": True,
                "source_original_preserved": True,
                "base_original_preserved": bool(base_original),
            },
        }
        manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return PreparationWorkspace(
            asset_id=asset_id,
            preparation_id=preparation_id,
            mode=mode,
            root=root,
            source_model=source_model,
            base_original=base_original,
            base_working=base_working,
            prepared_blend=prepared_blend,
            preview_glb=preview_glb,
            report_json=report_json,
            manifest_json=manifest_json,
            options=normalized_options,
        )
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    finally:
        if base is not None:
            await base.close()
        for resource in resource_uploads:
            await resource.close()


def _update_manifest(workspace: PreparationWorkspace, **updates: object) -> None:
    try:
        data = json.loads(workspace.manifest_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"asset_id": workspace.asset_id, "preparation_id": workspace.preparation_id}
    data.update(updates)
    tmp = workspace.manifest_json.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(workspace.manifest_json)


async def run_blender_preparation(
    raw_blender_path: str,
    script_path: Path,
    workspace: PreparationWorkspace,
    publish: EventPublisher,
    timeout_seconds: float = 240.0,
) -> None:
    try:
        _update_manifest(workspace, status="processing")
        await publish({"type": "progress", "value": 5, "message": "Validando preparação e Blender..."})
        executable = validate_blender_path(raw_blender_path)
        version = await probe_blender_version(executable)
        if not script_path.is_file():
            raise RuntimeError("Script interno de preparação corporal não foi encontrado.")

        args = [
            str(executable),
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--python-exit-code",
            "1",
            "--python",
            str(script_path),
            "--",
            "--mode",
            workspace.mode,
            "--source",
            str(workspace.source_model),
            "--preview",
            str(workspace.preview_glb),
            "--blend",
            str(workspace.prepared_blend),
            "--report",
            str(workspace.report_json),
            "--scale",
            str(workspace.options["scale"]),
            "--offset-x",
            str(workspace.options["offset_x"]),
            "--offset-y",
            str(workspace.options["offset_y"]),
            "--offset-z",
            str(workspace.options["offset_z"]),
            "--rotation-z",
            str(workspace.options["rotation_z"]),
        ]
        if workspace.base_working is not None:
            args.extend(["--base", str(workspace.base_working)])

        await publish({"type": "progress", "value": 18, "message": "Abrindo cópias de trabalho no Blender..."})
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        result_marker: dict = {}
        stdout_task = asyncio.create_task(_read_stream(process.stdout, "stdout", publish, result_marker))
        stderr_task = asyncio.create_task(_read_stream(process.stderr, "stderr", publish, result_marker))
        await publish({"type": "progress", "value": 42, "message": "Revisando rig, pose de referência e pesos..."})

        try:
            return_code = await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise RuntimeError("A preparação corporal excedeu o limite de tempo.")

        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        if return_code != 0:
            raise RuntimeError(f"O Blender encerrou a preparação com código {return_code}.")
        if not workspace.report_json.is_file():
            raise RuntimeError("O Blender terminou sem gerar o relatório de preparação.")
        if not workspace.prepared_blend.is_file():
            raise RuntimeError("O Blender terminou sem salvar o arquivo .blend preparado.")
        if not workspace.preview_glb.is_file() or workspace.preview_glb.stat().st_size < 20:
            raise RuntimeError("O Blender terminou sem gerar a visualização GLB preparada.")

        try:
            report = json.loads(workspace.report_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("O relatório de preparação gerado pelo Blender é inválido.") from exc

        _update_manifest(
            workspace,
            status="ready" if report.get("ready_for_body_customization") else "review_required",
            blender_version=version,
            ready_for_body_customization=bool(report.get("ready_for_body_customization")),
            blockers=report.get("blockers", []),
            warnings=report.get("warnings", []),
        )
        await publish({"type": "progress", "value": 100, "message": "Preparação corporal concluída."})
        await publish(
            {
                "type": "success",
                "message": (
                    "Base preparada e validações articulares aprovadas."
                    if report.get("ready_for_body_customization")
                    else "Preparação gerada para revisão assistida; há pontos que precisam de intervenção."
                ),
                "result": {
                    "asset_id": workspace.asset_id,
                    "preparation_id": workspace.preparation_id,
                    "mode": workspace.mode,
                    "preview_url": (
                        f"/api/assets/{workspace.asset_id}/preparations/{workspace.preparation_id}/preview.glb"
                    ),
                    "blend_url": (
                        f"/api/assets/{workspace.asset_id}/preparations/{workspace.preparation_id}/prepared.blend"
                    ),
                    "preparation": report,
                },
            }
        )
    except (PreparationValidationError, BlenderValidationError) as exc:
        _update_manifest(workspace, status="error", error=str(exc))
        await publish({"type": "error", "message": str(exc), "code": "PREPARATION_VALIDATION_ERROR"})
    except Exception as exc:
        message = f"Falha ao preparar a base corporal: {exc}"
        _update_manifest(workspace, status="error", error=message)
        await publish({"type": "error", "message": message, "code": "PREPARATION_ERROR"})


def resolve_preparation_root(asset_id: str, preparation_id: str) -> Path:
    if not ASSET_ID_RE.fullmatch(asset_id) or not PREPARATION_ID_RE.fullmatch(preparation_id):
        raise PreparationValidationError("Identificador de preparação inválido.")
    root = resolve_asset_root(asset_id) / "preparations" / preparation_id
    if not root.is_dir():
        raise FileNotFoundError(preparation_id)
    return root


def load_preparation_report(asset_id: str, preparation_id: str) -> dict | None:
    path = resolve_preparation_root(asset_id, preparation_id) / "preparation.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
