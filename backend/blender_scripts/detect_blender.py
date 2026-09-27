"""Script interno executado somente pelo backend dentro do Blender."""

import json
import platform

import bpy

payload = {
    "version": bpy.app.version_string,
    "version_tuple": list(bpy.app.version),
    "background": bool(bpy.app.background),
    "binary_path": bpy.app.binary_path,
    "python_version": platform.python_version(),
}

print("BODIEZ_RESULT:" + json.dumps(payload, ensure_ascii=False))
