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
from urllib.parse import unquote, urlparse

from fastapi import UploadFile

from .blender_service import (
    BlenderValidationError,
    _read_stream,
    probe_blender_version,
    validate_blender_path,
)
from .config import assets_root

EventPublisher = Callable[[dict], Awaitable[None]]

MODEL_EXTENSIONS = {".fbx", ".glb", ".gltf"}
RESOURCE_EXTENSIONS = {".bin", ".png", ".jpg", ".jpeg", ".webp", ".ktx2"}
MAX_MODEL_BYTES = 512 * 1024 * 1024
MAX_RESOURCE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_RESOURCE_BYTES = 1024 * 1024 * 1024
ASSET_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class AssetValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AssetWorkspace:
    asset_id: str
    root: Path
    original_model: Path
    working_model: Path
    preview_glb: Path
    report_json: Path
    manifest_json: Path
    resource_names: tuple[str, ...]


def _safe_filename(raw_name: str | None) -> str:
    if not raw_name:
        raise AssetValidationError("O arquivo enviado não possui nome.")
    if "/" in raw_name or "\\" in raw_name or raw_name != Path(raw_name).name or raw_name in {".", ".."}:
        raise AssetValidationError("Nome de arquivo inválido.")
    if "\x00" in raw_name or len(raw_name) > 255:
        raise AssetValidationError("Nome de arquivo inválido.")
    return raw_name


async def _write_upload(upload: UploadFile, destination: Path, limit: int) -> int:
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                handle.close()
                destination.unlink(missing_ok=True)
                raise AssetValidationError(
                    f"O arquivo '{destination.name}' excede o limite de {limit // (1024 * 1024)} MB."
                )
            handle.write(chunk)
    if total == 0:
        destination.unlink(missing_ok=True)
        raise AssetValidationError(f"O arquivo '{destination.name}' está vazio.")
    return total


def _validate_model_signature(path: Path) -> None:
    extension = path.suffix.lower()
    if extension not in MODEL_EXTENSIONS:
        raise AssetValidationError("Formato não permitido. Use FBX, GLB ou GLTF.")

    with path.open("rb") as handle:
        prefix = handle.read(4096)
    if extension == ".glb":
        if len(prefix) < 12 or prefix[:4] != b"glTF":
            raise AssetValidationError("O arquivo .glb não possui um cabeçalho GLB válido.")
        version = int.from_bytes(prefix[4:8], "little")
        declared_length = int.from_bytes(prefix[8:12], "little")
        if version != 2 or declared_length != path.stat().st_size:
            raise AssetValidationError("O arquivo .glb não possui estrutura GLB 2 válida.")
        return

    if extension == ".fbx":
        is_binary = prefix.startswith(b"Kaydara FBX Binary")
        is_ascii = b"FBXHeaderExtension" in prefix or prefix.lstrip().startswith(b"; FBX")
        if not (is_binary or is_ascii):
            raise AssetValidationError("O arquivo .fbx não possui um cabeçalho FBX reconhecível.")
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssetValidationError("O arquivo .gltf não contém JSON GLTF válido.") from exc
    asset = data.get("asset")
    if not isinstance(asset, dict) or not str(asset.get("version", "")).startswith("2"):
        raise AssetValidationError("Somente GLTF 2.x é suportado nesta etapa.")



def _validate_resource_signature(path: Path) -> None:
    extension = path.suffix.lower()
    if extension == ".bin":
        return
    with path.open("rb") as handle:
        prefix = handle.read(16)
    valid = {
        ".png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": prefix.startswith(b"\xff\xd8\xff"),
        ".jpeg": prefix.startswith(b"\xff\xd8\xff"),
        ".webp": len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP",
        ".ktx2": prefix.startswith(b"\xabKTX 20\xbb\r\n\x1a\n"),
    }.get(extension, False)
    if not valid:
        raise AssetValidationError(f"A dependência '{path.name}' não corresponde ao formato declarado.")

def _gltf_external_uris(path: Path) -> list[str]:
    if path.suffix.lower() != ".gltf":
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    uris: list[str] = []
    for collection_name in ("buffers", "images"):
        collection = data.get(collection_name, [])
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            uri = item.get("uri")
            if not isinstance(uri, str) or uri.startswith("data:"):
                continue
            parsed = urlparse(uri)
            if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
                raise AssetValidationError("GLTF com recursos remotos/URLs, query ou fragmento não é permitido.")
            decoded = unquote(parsed.path)
            candidate = Path(decoded)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise AssetValidationError("GLTF com caminhos absolutos ou '../' não é permitido.")
            if len(candidate.parts) != 1:
                raise AssetValidationError(
                    "Nesta etapa, dependências externas de GLTF devem ficar na mesma pasta do .gltf, sem subpastas."
                )
            uris.append(candidate.name)
    return sorted(set(uris))


async def create_asset_workspace(model: UploadFile, resources: list[UploadFile]) -> AssetWorkspace:
    model_name = _safe_filename(model.filename)
    model_ext = Path(model_name).suffix.lower()
    if model_ext not in MODEL_EXTENSIONS:
        raise AssetValidationError("Formato não permitido. Use FBX, GLB ou GLTF.")

    asset_id = uuid.uuid4().hex
    root = assets_root() / asset_id
    original_dir = root / "original"
    working_dir = root / "working"
    preview_dir = root / "preview"
    original_model = original_dir / model_name
    working_model = working_dir / model_name
    preview_glb = preview_dir / "model.glb"
    report_json = root / "inspection.json"
    manifest_json = root / "manifest.json"

    try:
        await _write_upload(model, original_model, MAX_MODEL_BYTES)
        _validate_model_signature(original_model)

        seen: set[str] = set()
        total_resource_bytes = 0
        resource_names: list[str] = []
        for resource in resources:
            name = _safe_filename(resource.filename)
            extension = Path(name).suffix.lower()
            if extension not in RESOURCE_EXTENSIONS:
                raise AssetValidationError(
                    f"Dependência '{name}' não é permitida. Use BIN, PNG, JPG, WEBP ou KTX2."
                )
            if name in seen or name == model_name:
                raise AssetValidationError(f"Arquivo duplicado no envio: '{name}'.")
            seen.add(name)
            resource_destination = original_dir / name
            size = await _write_upload(resource, resource_destination, MAX_RESOURCE_BYTES)
            _validate_resource_signature(resource_destination)
            total_resource_bytes += size
            if total_resource_bytes > MAX_TOTAL_RESOURCE_BYTES:
                raise AssetValidationError("As dependências externas excedem o limite total de 1 GB.")
            resource_names.append(name)

        required_resources = _gltf_external_uris(original_model)
        missing = [name for name in required_resources if name not in seen]
        if missing:
            raise AssetValidationError(
                "O GLTF referencia arquivos externos que não foram selecionados: " + ", ".join(missing)
            )

        working_dir.mkdir(parents=True, exist_ok=True)
        preview_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original_model, working_model)
        for name in resource_names:
            shutil.copy2(original_dir / name, working_dir / name)

        manifest = {
            "format_version": 1,
            "asset_id": asset_id,
            "created_at": int(time.time()),
            "status": "queued",
            "original_name": model_name,
            "format": model_ext.lstrip("."),
            "resources": resource_names,
            "original_preserved": True,
        }
        manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return AssetWorkspace(
            asset_id=asset_id,
            root=root,
            original_model=original_model,
            working_model=working_model,
            preview_glb=preview_glb,
            report_json=report_json,
            manifest_json=manifest_json,
            resource_names=tuple(resource_names),
        )
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    finally:
        await model.close()
        for resource in resources:
            await resource.close()


def _update_manifest(workspace: AssetWorkspace, **updates: object) -> None:
    try:
        data = json.loads(workspace.manifest_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"asset_id": workspace.asset_id}
    data.update(updates)
    tmp = workspace.manifest_json.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(workspace.manifest_json)


async def run_blender_import(
    raw_blender_path: str,
    script_path: Path,
    workspace: AssetWorkspace,
    publish: EventPublisher,
    timeout_seconds: float = 180.0,
) -> None:
    try:
        _update_manifest(workspace, status="processing")
        await publish({"type": "progress", "value": 5, "message": "Validando Blender e arquivo..."})
        executable = validate_blender_path(raw_blender_path)
        version = await probe_blender_version(executable)
        await publish(
            {
                "type": "log",
                "level": "info",
                "stream": "backend",
                "message": f"Processamento iniciado com Blender {version}.",
            }
        )

        if not script_path.is_file():
            raise RuntimeError("Script interno de importação não foi encontrado.")

        await publish({"type": "progress", "value": 18, "message": "Abrindo cópia de trabalho no Blender..."})
        process = await asyncio.create_subprocess_exec(
            str(executable),
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--python-exit-code",
            "1",
            "--python",
            str(script_path),
            "--",
            "--source",
            str(workspace.working_model),
            "--preview",
            str(workspace.preview_glb),
            "--report",
            str(workspace.report_json),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        result_marker: dict = {}
        stdout_task = asyncio.create_task(_read_stream(process.stdout, "stdout", publish, result_marker))
        stderr_task = asyncio.create_task(_read_stream(process.stderr, "stderr", publish, result_marker))
        await publish({"type": "progress", "value": 35, "message": "Inspecionando malhas, rig e animações..."})

        try:
            return_code = await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise RuntimeError("A importação excedeu o limite de tempo.")

        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        if return_code != 0:
            raise RuntimeError(f"O Blender encerrou a importação com código {return_code}.")
        if not workspace.report_json.is_file():
            raise RuntimeError("O Blender terminou sem gerar o relatório de inspeção.")
        if not workspace.preview_glb.is_file() or workspace.preview_glb.stat().st_size < 20:
            raise RuntimeError("O Blender terminou sem gerar o GLB intermediário de visualização.")

        try:
            inspection = json.loads(workspace.report_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("O relatório de inspeção gerado pelo Blender é inválido.") from exc

        summary = inspection.get("summary", {})
        _update_manifest(
            workspace,
            status="ready",
            blender_version=version,
            summary=summary,
            preview_size=workspace.preview_glb.stat().st_size,
        )

        await publish({"type": "progress", "value": 100, "message": "Personagem importado e inspecionado."})
        await publish(
            {
                "type": "success",
                "message": "Importação concluída. O original foi preservado e a visualização usa uma cópia GLB.",
                "result": {
                    "asset_id": workspace.asset_id,
                    "original_name": workspace.original_model.name,
                    "preview_url": f"/api/assets/{workspace.asset_id}/preview.glb",
                    "inspection": inspection,
                },
            }
        )
    except (AssetValidationError, BlenderValidationError) as exc:
        _update_manifest(workspace, status="error", error=str(exc))
        await publish({"type": "error", "message": str(exc), "code": "ASSET_VALIDATION_ERROR"})
    except Exception as exc:
        message = f"Falha ao importar o personagem: {exc}"
        _update_manifest(workspace, status="error", error=message)
        await publish({"type": "error", "message": message, "code": "ASSET_IMPORT_ERROR"})


def resolve_asset_root(asset_id: str) -> Path:
    if not ASSET_ID_RE.fullmatch(asset_id):
        raise AssetValidationError("Identificador de asset inválido.")
    root = assets_root() / asset_id
    if not root.is_dir():
        raise FileNotFoundError(asset_id)
    return root


def load_asset_manifest(asset_id: str) -> dict:
    root = resolve_asset_root(asset_id)
    path = root / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(asset_id)
    return json.loads(path.read_text(encoding="utf-8"))


def load_asset_inspection(asset_id: str) -> dict | None:
    root = resolve_asset_root(asset_id)
    path = root / "inspection.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
