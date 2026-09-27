from pathlib import Path

import pytest

from app.blender_service import BlenderValidationError, validate_blender_path


def test_rejects_relative_path() -> None:
    with pytest.raises(BlenderValidationError, match="caminho absoluto"):
        validate_blender_path("blender")


def test_rejects_nonexistent_path(tmp_path: Path) -> None:
    path = tmp_path / "blender"
    with pytest.raises(BlenderValidationError, match="não existe"):
        validate_blender_path(str(path))


def test_rejects_wrong_executable_name(tmp_path: Path) -> None:
    path = tmp_path / "bash"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    with pytest.raises(BlenderValidationError, match="precisa se chamar"):
        validate_blender_path(str(path))


def test_full_connection_flow_with_fake_blender(tmp_path: Path) -> None:
    import asyncio

    from app.blender_service import run_blender_connection_test

    fake_blender = tmp_path / "blender"
    fake_blender.write_text(
        """#!/usr/bin/env python3
import json
import sys
if '--version' in sys.argv:
    print('Blender 4.5.3')
    raise SystemExit(0)
print('Blender 4.5.3 fake startup')
print('BODIEZ_RESULT:' + json.dumps({
    'version': '4.5.3',
    'version_tuple': [4, 5, 3],
    'background': True,
    'binary_path': sys.argv[0],
    'python_version': '3.11.0',
}))
""",
        encoding="utf-8",
    )
    fake_blender.chmod(0o755)
    internal_script = tmp_path / "diagnostic.py"
    internal_script.write_text("# fixed internal script placeholder\n", encoding="utf-8")

    events: list[dict] = []

    async def publish(event: dict) -> None:
        events.append(event)

    asyncio.run(
        run_blender_connection_test(
            str(fake_blender),
            internal_script,
            publish,
            timeout_seconds=5,
        )
    )

    assert events[-1]["type"] == "success"
    assert events[-1]["result"]["version"] == "4.5.3"
    assert any(event.get("type") == "progress" and event.get("value") == 100 for event in events)
