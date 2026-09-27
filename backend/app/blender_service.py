from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Awaitable, Callable

RESULT_PREFIX = "BODIEZ_RESULT:"
ALLOWED_EXECUTABLE_NAMES = {"blender", "blender.exe"}
BLENDER_VERSION_RE = re.compile(r"^Blender\s+([0-9]+(?:\.[0-9]+){1,2})", re.MULTILINE)

EventPublisher = Callable[[dict], Awaitable[None]]


class BlenderValidationError(ValueError):
    pass


def validate_blender_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        raise BlenderValidationError("Use um caminho absoluto para o executável do Blender.")

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise BlenderValidationError("O executável informado não existe.") from exc

    if resolved.name.lower() not in ALLOWED_EXECUTABLE_NAMES:
        raise BlenderValidationError(
            "Por segurança, o arquivo precisa se chamar 'blender' ou 'blender.exe'."
        )
    if not resolved.is_file():
        raise BlenderValidationError("O caminho informado não aponta para um arquivo.")
    if os.name != "nt" and not os.access(resolved, os.X_OK):
        raise BlenderValidationError("O arquivo do Blender não tem permissão de execução.")
    return resolved


async def _read_stream(
    stream: asyncio.StreamReader | None,
    stream_name: str,
    publish: EventPublisher,
    result_holder: dict,
) -> None:
    if stream is None:
        return
    while True:
        line = await stream.readline()
        if not line:
            return
        text = line.decode("utf-8", errors="replace").rstrip()
        if not text:
            continue
        if text.startswith(RESULT_PREFIX):
            payload = text[len(RESULT_PREFIX) :]
            try:
                result_holder.update(json.loads(payload))
            except json.JSONDecodeError:
                await publish(
                    {
                        "type": "log",
                        "level": "warning",
                        "stream": stream_name,
                        "message": "O Blender retornou um resultado interno inválido.",
                    }
                )
            continue
        await publish(
            {
                "type": "log",
                "level": "info" if stream_name == "stdout" else "warning",
                "stream": stream_name,
                "message": text,
            }
        )


async def probe_blender_version(executable: Path, timeout_seconds: float = 10.0) -> str:
    process = await asyncio.create_subprocess_exec(
        str(executable),
        "--version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise BlenderValidationError("O Blender não respondeu ao teste de versão a tempo.")

    combined = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
    match = BLENDER_VERSION_RE.search(combined)
    if process.returncode != 0 or not match:
        raise BlenderValidationError(
            "O arquivo foi executado, mas não se identificou como Blender pelo comando --version."
        )
    return match.group(1)


async def run_blender_connection_test(
    raw_path: str,
    script_path: Path,
    publish: EventPublisher,
    timeout_seconds: float = 30.0,
) -> None:
    try:
        await publish({"type": "progress", "value": 5, "message": "Validando caminho do Blender..."})
        executable = validate_blender_path(raw_path)

        await publish({"type": "progress", "value": 15, "message": "Confirmando executável..."})
        probe_version = await probe_blender_version(executable)
        await publish(
            {
                "type": "log",
                "level": "info",
                "stream": "backend",
                "message": f"Executável identificado como Blender {probe_version}.",
            }
        )

        if not script_path.is_file():
            raise RuntimeError("Script interno de diagnóstico não foi encontrado.")

        await publish({"type": "progress", "value": 30, "message": "Iniciando Blender em segundo plano..."})
        process = await asyncio.create_subprocess_exec(
            str(executable),
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--python",
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        result: dict = {}
        stdout_task = asyncio.create_task(_read_stream(process.stdout, "stdout", publish, result))
        stderr_task = asyncio.create_task(_read_stream(process.stderr, "stderr", publish, result))

        await publish({"type": "progress", "value": 55, "message": "Executando tarefa bpy real..."})
        try:
            return_code = await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise RuntimeError("O teste do Blender excedeu o limite de tempo.")

        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

        if return_code != 0:
            raise RuntimeError(f"O Blender encerrou com código {return_code}.")
        if not result.get("version"):
            raise RuntimeError("O Blender terminou sem retornar o resultado esperado do bpy.")

        await publish({"type": "progress", "value": 100, "message": "Conexão validada."})
        await publish(
            {
                "type": "success",
                "message": "Blender conectado e bpy executado com sucesso.",
                "result": result,
            }
        )
    except BlenderValidationError as exc:
        await publish({"type": "error", "message": str(exc), "code": "BLENDER_VALIDATION_ERROR"})
    except Exception as exc:
        await publish(
            {
                "type": "error",
                "message": f"Falha ao testar o Blender: {exc}",
                "code": "BLENDER_TEST_ERROR",
            }
        )
