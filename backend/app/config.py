from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Final

APP_NAME: Final = "bodiez-local"
DEFAULT_FRONTEND_ORIGINS: Final[set[str]] = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
}


def settings_path() -> Path:
    override = os.environ.get("BODIEZ_SETTINGS_PATH")
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME / "settings.json"


def data_root() -> Path:
    override = os.environ.get("BODIEZ_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


def assets_root() -> Path:
    return data_root() / "assets"


def discover_blender() -> str | None:
    from_path = shutil.which("blender")
    if from_path:
        return str(Path(from_path).resolve())

    candidates = [
        Path("/usr/bin/blender"),
        Path("/usr/local/bin/blender"),
        Path("/opt/blender/blender"),
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    return None


def load_settings() -> dict[str, str | None]:
    path = settings_path()
    if not path.exists():
        return {"blender_path": discover_blender()}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"blender_path": discover_blender()}

    blender_path = data.get("blender_path")
    if isinstance(blender_path, str) and blender_path.strip():
        return {"blender_path": blender_path}
    return {"blender_path": discover_blender()}


def save_settings(blender_path: str) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"blender_path": blender_path}, indent=2), encoding="utf-8")
    tmp.replace(path)
