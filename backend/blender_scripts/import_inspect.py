from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

import bpy

RESULT_PREFIX = "BODIEZ_RESULT:"


def parse_args() -> argparse.Namespace:
    if "--" not in sys.argv:
        raise RuntimeError("Argumentos internos da tarefa não foram fornecidos.")
    args = sys.argv[sys.argv.index("--") + 1 :]
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--source", required=True)
    parser.add_argument("--preview", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args(args)


def log(message: str) -> None:
    print(f"[Bodiez] {message}", flush=True)


def import_model(source: Path) -> None:
    extension = source.suffix.lower()
    log(f"Importando cópia de trabalho: {source.name}")
    if extension == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif extension in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(source))
    else:
        raise RuntimeError(f"Formato não suportado pelo script interno: {extension}")


def vec3(value) -> list[float]:
    return [round(float(value[0]), 6), round(float(value[1]), 6), round(float(value[2]), 6)]


def normalize_bone_name(name: str) -> str:
    leaf = name.replace("\\", "/").split("/")[-1].split("|")[-1]
    if ":" in leaf:
        leaf = leaf.rsplit(":", 1)[1]
    compact = re.sub(r"[^a-zA-Z0-9]", "", leaf)
    lower = compact.lower()
    if lower.startswith("mixamorig") and len(compact) > len("mixamorig"):
        compact = compact[len("mixamorig") :]
    return compact


SEMANTIC_VARIANTS = {
    "hips": {"hips", "pelvis"}, "spine": {"spine"}, "spine_1": {"spine1", "spine01", "chest"},
    "spine_2": {"spine2", "spine02", "upperchest"}, "neck": {"neck", "neck1", "neck01"}, "head": {"head"},
    "left_shoulder": {"leftshoulder", "lshoulder", "shoulderl"}, "left_upper_arm": {"leftarm", "leftupperarm", "lupperarm", "upperarml"},
    "left_forearm": {"leftforearm", "leftlowerarm", "lforearm", "lowerarml"}, "left_hand": {"lefthand", "lhand", "handl"},
    "right_shoulder": {"rightshoulder", "rshoulder", "shoulderr"}, "right_upper_arm": {"rightarm", "rightupperarm", "rupperarm", "upperarmr"},
    "right_forearm": {"rightforearm", "rightlowerarm", "rforearm", "lowerarmr"}, "right_hand": {"righthand", "rhand", "handr"},
    "left_thigh": {"leftupleg", "leftthigh", "lthigh", "thighl"}, "left_shin": {"leftleg", "leftlowerleg", "lshin", "calfl"},
    "left_foot": {"leftfoot", "lfoot", "footl"}, "right_thigh": {"rightupleg", "rightthigh", "rthigh", "thighr"},
    "right_shin": {"rightleg", "rightlowerleg", "rshin", "calfr"}, "right_foot": {"rightfoot", "rfoot", "footr"},
}
MIXAMO_CANONICAL = {"Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "RightShoulder", "RightArm", "RightForeArm", "RightHand", "LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"}


def analyze_bone_names(names: list[str]) -> dict:
    normalized = {name: normalize_bone_name(name) for name in names}
    lower_lookup: dict[str, list[str]] = {}
    for original, normal in normalized.items(): lower_lookup.setdefault(normal.lower(), []).append(original)
    semantic_matches: dict[str, str] = {}
    for semantic, variants in SEMANTIC_VARIANTS.items():
        for variant in variants:
            matches = lower_lookup.get(variant.lower())
            if matches: semantic_matches[semantic] = matches[0]; break
    canonical_lower = {value.lower() for value in MIXAMO_CANONICAL}
    canonical_matches = [name for name, normal in normalized.items() if normal.lower() in canonical_lower]
    namespace_counts: dict[str, int] = {}
    for name in names:
        leaf = name.replace("\\", "/").split("/")[-1].split("|")[-1]
        if ":" in leaf:
            prefix = leaf.rsplit(":", 1)[0]; namespace_counts[prefix] = namespace_counts.get(prefix, 0) + 1
    namespace = max(namespace_counts, key=namespace_counts.get) if namespace_counts else None
    semantic_core = {"hips", "head", "left_upper_arm", "right_upper_arm", "left_thigh", "right_thigh", "left_shin", "right_shin", "left_foot", "right_foot"}
    core_matches = len(semantic_core.intersection(semantic_matches.keys()))
    canonical_ratio = len(canonical_matches) / len(MIXAMO_CANONICAL)
    return {"namespace_prefix": namespace, "namespace_counts": namespace_counts, "semantic_matches": semantic_matches, "canonical_mixamo_matches": len(canonical_matches), "canonical_mixamo_total": len(MIXAMO_CANONICAL), "canonical_match_ratio": round(canonical_ratio, 3), "likely_mixamo": len(canonical_matches) >= 12 and core_matches >= 8, "note": "A detecção remove namespaces/prefixos e usa nomes normalizados mais a presença de cadeias humanoides. Isto é uma inspeção, não retargeting nem conversão automática de rig."}


def inspect_armature(obj) -> dict:
    bones = [{"name": b.name, "parent": b.parent.name if b.parent else None, "children_count": len(b.children), "deform": bool(b.use_deform), "head_local": vec3(b.head_local), "tail_local": vec3(b.tail_local), "length": round(float(b.length), 6)} for b in obj.data.bones]
    return {"name": obj.name, "bone_count": len(obj.data.bones), "roots": [b.name for b in obj.data.bones if b.parent is None], "bones": bones, "bone_name_analysis": analyze_bone_names([b.name for b in obj.data.bones])}


def find_armature_for_mesh(obj):
    for modifier in obj.modifiers:
        if modifier.type == "ARMATURE" and modifier.object is not None: return modifier.object
    if obj.parent and obj.parent.type == "ARMATURE": return obj.parent
    return None


def inspect_weights(obj, armature) -> dict:
    if armature is None:
        return {"armature": None, "vertex_groups": len(obj.vertex_groups), "bone_vertex_groups": 0, "weighted_vertices": 0, "total_vertices": len(obj.data.vertices), "coverage": 0.0, "average_influences": 0.0, "max_influences": 0}
    bone_names = {bone.name for bone in armature.data.bones}; group_index_to_name = {g.index: g.name for g in obj.vertex_groups}; bone_group_indices = {i for i, n in group_index_to_name.items() if n in bone_names}
    weighted_vertices = total_influences = max_influences = 0
    for vertex in obj.data.vertices:
        influences = sum(1 for item in vertex.groups if item.group in bone_group_indices and item.weight > 0.000001)
        if influences: weighted_vertices += 1; total_influences += influences; max_influences = max(max_influences, influences)
    total_vertices = len(obj.data.vertices)
    return {"armature": armature.name, "vertex_groups": len(obj.vertex_groups), "bone_vertex_groups": len(bone_group_indices), "weighted_vertices": weighted_vertices, "total_vertices": total_vertices, "coverage": round(weighted_vertices / total_vertices, 4) if total_vertices else 0.0, "average_influences": round(total_influences / weighted_vertices, 3) if weighted_vertices else 0.0, "max_influences": max_influences}


def inspect_mesh(obj) -> dict:
    armature = find_armature_for_mesh(obj); shape_keys = []
    if obj.data.shape_keys:
        for index, key in enumerate(obj.data.shape_keys.key_blocks): shape_keys.append({"name": key.name, "value": round(float(key.value), 6), "min": round(float(key.slider_min), 6), "max": round(float(key.slider_max), 6), "basis": index == 0})
    material_names = [slot.material.name for slot in obj.material_slots if slot.material]
    return {"name": obj.name, "vertices": len(obj.data.vertices), "edges": len(obj.data.edges), "polygons": len(obj.data.polygons), "materials": material_names, "shape_keys": shape_keys, "armature": armature.name if armature else None, "weights": inspect_weights(obj, armature)}


def inspect_material(material) -> dict:
    color = list(material.diffuse_color) if hasattr(material, "diffuse_color") else [1, 1, 1, 1]
    return {"name": material.name, "use_nodes": bool(material.use_nodes), "diffuse_color": [round(float(value), 5) for value in color]}


def inspect_animations(armatures: list) -> dict:
    actions = []
    for action in bpy.data.actions:
        try: frame_range = [round(float(action.frame_range[0]), 3), round(float(action.frame_range[1]), 3)]
        except Exception: frame_range = [0.0, 0.0]
        actions.append({"name": action.name, "frame_range": frame_range})
    nla_tracks = []
    for armature in armatures:
        if not armature.animation_data: continue
        for track in armature.animation_data.nla_tracks: nla_tracks.append({"armature": armature.name, "track": track.name, "strips": [strip.name for strip in track.strips]})
    scene = bpy.context.scene
    return {"actions": actions, "nla_tracks": nla_tracks, "scene_frame_start": int(scene.frame_start), "scene_frame_end": int(scene.frame_end), "fps": round(float(scene.render.fps / scene.render.fps_base), 3)}


def build_report(source: Path) -> dict:
    scene_objects = list(bpy.context.scene.objects); mesh_objects = [o for o in scene_objects if o.type == "MESH"]; armature_objects = [o for o in scene_objects if o.type == "ARMATURE"]
    meshes = [inspect_mesh(o) for o in mesh_objects]; armatures = [inspect_armature(o) for o in armature_objects]
    material_names = sorted({name for mesh in meshes for name in mesh["materials"]}); materials = [inspect_material(bpy.data.materials[name]) for name in material_names if name in bpy.data.materials]; animations = inspect_animations(armature_objects)
    return {"source": {"name": source.name, "format": source.suffix.lower().lstrip(".")}, "summary": {"mesh_count": len(meshes), "armature_count": len(armatures), "material_count": len(materials), "shape_key_count": sum(max(0, len(mesh["shape_keys"]) - 1) for mesh in meshes), "action_count": len(animations["actions"]), "total_vertices": sum(mesh["vertices"] for mesh in meshes), "total_polygons": sum(mesh["polygons"] for mesh in meshes), "likely_mixamo": any(arm["bone_name_analysis"]["likely_mixamo"] for arm in armatures)}, "scene": {"object_count": len(scene_objects), "unit_system": bpy.context.scene.unit_settings.system, "scale_length": float(bpy.context.scene.unit_settings.scale_length)}, "meshes": meshes, "armatures": armatures, "materials": materials, "animations": animations, "limitations": ["A presença de ossos com nomenclatura/estrutura compatível com Mixamo é apenas uma detecção heurística.", "Esta etapa não faz retargeting, não converte Rigify/Bodiez para Mixamo e não cria pesos ou morphs ausentes.", "O GLB gerado é uma cópia intermediária de visualização; o arquivo importado original permanece intacto."]}


def main() -> None:
    args = parse_args(); source = Path(args.source).resolve(); preview = Path(args.preview).resolve(); report = Path(args.report).resolve()
    if not source.is_file(): raise RuntimeError("A cópia de trabalho não existe.")
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False); import_model(source)
    report_data = build_report(source); report.parent.mkdir(parents=True, exist_ok=True); report.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Inspeção: {report_data['summary']['mesh_count']} malha(s), {report_data['summary']['armature_count']} armature(s), {report_data['summary']['shape_key_count']} shape key(s).")
    preview.parent.mkdir(parents=True, exist_ok=True); log("Gerando GLB intermediário para o visualizador web..."); bpy.ops.export_scene.gltf(filepath=str(preview), export_format="GLB")
    if not preview.is_file(): raise RuntimeError("O exportador glTF não gerou o arquivo de visualização.")
    print(RESULT_PREFIX + json.dumps({"ok": True, "preview_bytes": preview.stat().st_size}), flush=True)


if __name__ == "__main__":
    try: main()
    except Exception: traceback.print_exc(); raise
