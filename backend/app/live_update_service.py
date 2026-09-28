from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from .blender_service import probe_blender_version, validate_blender_path
from .body_service import BodyError, caps_for, normalize, root_for, run, sources

Publish = Callable[[dict], Awaitable[None]]
CLIENT_TOKEN_RE = __import__('re').compile(r'^[0-9a-f]{32}$')
MAX_GENERATION = 2_000_000_000


class LiveUpdateError(ValueError):
    pass


@dataclass(frozen=True)
class LiveUpdate:
    asset_id: str
    preparation_id: str
    customization_id: str
    client_token: str
    generation: int
    root: Path
    baseline: Path
    request: Path
    blend: Path
    preview: Path
    report: Path
    stale_on_arrival: bool


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def _read_dict(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except Exception as exc:
        raise LiveUpdateError(f'Estado interno inválido: {path.name}') from exc
    return value if isinstance(value, dict) else {}


def _validate_client_token(token: str) -> str:
    token = str(token).lower()
    if not CLIENT_TOKEN_RE.fullmatch(token):
        raise LiveUpdateError('Identificador do cliente inválido.')
    return token


def _validate_generation(generation: int) -> int:
    if isinstance(generation, bool):
        raise LiveUpdateError('Geração de atualização inválida.')
    try:
        value = int(generation)
    except Exception as exc:
        raise LiveUpdateError('Geração de atualização inválida.') from exc
    if value < 1 or value > MAX_GENERATION:
        raise LiveUpdateError('Geração de atualização fora do intervalo permitido.')
    return value


def _client_root(asset_id: str, preparation_id: str, customization_id: str, client_token: str) -> Path:
    return root_for(asset_id, preparation_id, customization_id) / 'live' / _validate_client_token(client_token)


def latest_generation(asset_id: str, preparation_id: str, customization_id: str, client_token: str) -> int:
    state = _read_dict(_client_root(asset_id, preparation_id, customization_id, client_token) / 'state.json')
    try:
        return int(state.get('latest_generation', 0))
    except Exception:
        return 0


def is_latest(update: LiveUpdate) -> bool:
    return latest_generation(
        update.asset_id,
        update.preparation_id,
        update.customization_id,
        update.client_token,
    ) == update.generation


def create_live_update(
    asset_id: str,
    preparation_id: str,
    customization_id: str,
    client_token: str,
    generation: int,
    values: dict,
    bindings: dict,
) -> LiveUpdate:
    token = _validate_client_token(client_token)
    gen = _validate_generation(generation)
    body_root = root_for(asset_id, preparation_id, customization_id)
    baseline = body_root / 'baseline.blend'
    if not baseline.is_file():
        raise LiveUpdateError('Baseline corporal não encontrada. Prepare os controles da Etapa 4 novamente.')

    caps = caps_for(asset_id, preparation_id, customization_id)
    try:
        clean_values, clean_bindings = normalize(caps, values, bindings)
    except BodyError:
        raise
    source_index = sources(caps)
    resolved = {
        control: list(source_index[source_id].get('targets', []))
        for control, source_id in clean_bindings.items()
        if source_id in source_index
    }

    client_root = body_root / 'live' / token
    client_root.mkdir(parents=True, exist_ok=True)
    state_path = client_root / 'state.json'
    current = latest_generation(asset_id, preparation_id, customization_id, token)
    stale_on_arrival = gen <= current

    generation_root = client_root / f'{gen:010d}'
    request_path = generation_root / 'request.json'
    if not stale_on_arrival:
        if generation_root.exists():
            shutil.rmtree(generation_root, ignore_errors=True)
        generation_root.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            request_path,
            {
                'format_version': 1,
                'generation': gen,
                'values': clean_values,
                'bindings': clean_bindings,
                'resolved': resolved,
                'purpose': 'stage6_live_preview',
            },
        )
        _atomic_write(
            state_path,
            {
                'format_version': 1,
                'latest_generation': gen,
            },
        )

    return LiveUpdate(
        asset_id=asset_id,
        preparation_id=preparation_id,
        customization_id=customization_id,
        client_token=token,
        generation=gen,
        root=generation_root,
        baseline=baseline,
        request=request_path,
        blend=generation_root / 'preview.blend',
        preview=generation_root / 'preview.glb',
        report=generation_root / 'result.json',
        stale_on_arrival=stale_on_arrival,
    )


def resolve_live_preview(
    asset_id: str,
    preparation_id: str,
    customization_id: str,
    client_token: str,
    generation: int,
) -> Path:
    token = _validate_client_token(client_token)
    gen = _validate_generation(generation)
    root = _client_root(asset_id, preparation_id, customization_id, token) / f'{gen:010d}'
    if not root.is_dir():
        raise FileNotFoundError(gen)
    return root / 'preview.glb'


def _cleanup_old_generations(update: LiveUpdate, keep: int = 3) -> None:
    parent = update.root.parent
    dirs = sorted(
        [p for p in parent.iterdir() if p.is_dir() and p.name.isdigit()],
        key=lambda p: p.name,
        reverse=True,
    )
    for old in dirs[keep:]:
        shutil.rmtree(old, ignore_errors=True)


async def process_live_update(
    blender_path: str,
    script_path: Path,
    update: LiveUpdate,
    publish: Publish,
    timeout_seconds: float = 240.0,
) -> None:
    try:
        if update.stale_on_arrival or not is_latest(update):
            await publish(
                {
                    'type': 'success',
                    'message': 'Atualização ultrapassada ignorada.',
                    'result': {'generation': update.generation, 'stale': True},
                }
            )
            return

        executable = validate_blender_path(blender_path)
        await probe_blender_version(executable)
        if not script_path.is_file():
            raise RuntimeError('Script interno de personalização não encontrado.')

        await publish(
            {
                'type': 'progress',
                'value': 20,
                'message': 'Sincronizando alterações estruturais no Blender...',
                'generation': update.generation,
            }
        )
        await run(
            executable,
            [
                '--background',
                '--factory-startup',
                '--disable-autoexec',
                '--python-exit-code',
                '1',
                '--python',
                str(script_path),
                '--',
                'apply',
                str(update.baseline),
                str(update.request),
                str(update.blend),
                str(update.preview),
                str(update.report),
            ],
            publish,
            timeout_seconds,
        )

        if not is_latest(update):
            await publish(
                {
                    'type': 'success',
                    'message': 'Resultado antigo descartado; há alterações mais novas.',
                    'result': {'generation': update.generation, 'stale': True},
                }
            )
            _cleanup_old_generations(update)
            return

        if not update.preview.is_file():
            raise RuntimeError('O Blender terminou sem gerar a prévia estrutural.')
        report = _read_dict(update.report)
        _cleanup_old_generations(update)
        await publish(
            {
                'type': 'progress',
                'value': 100,
                'message': 'Estrutura sincronizada.',
                'generation': update.generation,
            }
        )
        await publish(
            {
                'type': 'success',
                'message': 'Prévia do Blender atualizada.',
                'result': {
                    'generation': update.generation,
                    'stale': False,
                    'preview_url': (
                        f'/api/stage6/assets/{update.asset_id}/preparations/{update.preparation_id}'
                        f'/customizations/{update.customization_id}/live/{update.client_token}/{update.generation}/preview.glb'
                    ),
                    'application': report,
                },
            }
        )
    except Exception as exc:
        if not is_latest(update):
            await publish(
                {
                    'type': 'success',
                    'message': 'Erro de uma atualização antiga ignorado.',
                    'result': {'generation': update.generation, 'stale': True},
                }
            )
            return
        await publish(
            {
                'type': 'error',
                'message': f'Falha ao atualizar a prévia estrutural: {exc}',
                'code': 'STAGE6_LIVE_UPDATE_ERROR',
                'generation': update.generation,
            }
        )
