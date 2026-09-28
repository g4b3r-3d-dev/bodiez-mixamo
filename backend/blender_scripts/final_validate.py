from __future__ import annotations

import json
import math
import re
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector

SEMANTIC = {
    "hips": {"hips", "pelvis"}, "head": {"head"},
    "left_shoulder": {"leftshoulder", "shoulderl"}, "right_shoulder": {"rightshoulder", "shoulderr"},
    "left_upper_arm": {"leftarm", "leftupperarm", "upperarml"}, "right_upper_arm": {"rightarm", "rightupperarm", "upperarmr"},
    "left_forearm": {"leftforearm", "leftlowerarm", "lowerarml"}, "right_forearm": {"rightforearm", "rightlowerarm", "lowerarmr"},
    "left_thigh": {"leftupleg", "leftthigh", "thighl"}, "right_thigh": {"rightupleg", "rightthigh", "thighr"},
    "left_shin": {"leftleg", "leftlowerleg", "calfl"}, "right_shin": {"rightleg", "rightlowerleg", "calfr"},
}
JOINTS = {"left_shoulder":"left_upper_arm","right_shoulder":"right_upper_arm","left_elbow":"left_forearm","right_elbow":"right_forearm","left_hip":"left_thigh","right_hip":"right_thigh","left_knee":"left_shin","right_knee":"right_shin"}


def norm(name: str) -> str:
    value = name.split("|")[-1].rsplit(":", 1)[-1]
    value = re.sub(r"[^A-Za-z0-9]", "", value).lower()
    return value[10:] if value.startswith("mixamorig") else value


def read_json(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise RuntimeError("Pedido de validação inválido.")
    return value


def add(items: list[dict], key: str, label: str, status: str, evidence: str, metrics: dict | None = None) -> None:
    item = {"key": key, "label": label, "status": status, "evidence": evidence}
    if metrics: item["metrics"] = metrics
    items.append(item)


def finite_vector(vector) -> bool:
    return all(math.isfinite(float(value)) for value in vector)


def bounds() -> tuple[Vector, Vector] | None:
    points = [obj.matrix_world @ Vector(corner) for obj in bpy.context.scene.objects if obj.type == "MESH" for corner in obj.bound_box]
    if not points: return None
    low = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    high = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    return low, high


def scene_snapshot() -> dict:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    shape_keys = drivers = constraints = 0; missing_images = []
    for obj in bpy.context.scene.objects:
        constraints += len(obj.constraints); ad = getattr(obj, "animation_data", None); drivers += len(ad.drivers) if ad else 0
        if obj.type == "MESH" and obj.data.shape_keys:
            shape_keys += max(0, len(obj.data.shape_keys.key_blocks) - 1); kad = obj.data.shape_keys.animation_data; drivers += len(kad.drivers) if kad else 0
    for image in bpy.data.images:
        if image.source == "FILE" and not image.packed_file and image.filepath and not Path(bpy.path.abspath(image.filepath)).is_file(): missing_images.append(image.name)
    bb = bounds(); size = bb[1] - bb[0] if bb else Vector((0,0,0))
    return {"mesh_count":len(meshes),"armature_count":len(armatures),"shape_key_count":shape_keys,"action_count":len(bpy.data.actions),"driver_count":drivers,"constraint_count":constraints,"missing_images":sorted(set(missing_images)),"bounds":[float(size.x),float(size.y),float(size.z)],"unit_scale":float(bpy.context.scene.unit_settings.scale_length)}


def select_armature():
    arms = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not arms: return None
    def score(arm):
        names = {norm(bone.name) for bone in arm.data.bones}; return sum(bool(names & variants) for variants in SEMANTIC.values())
    return max(arms, key=lambda arm:(score(arm),len(arm.data.bones)))


def semantic_map(arm) -> dict[str,str]:
    lookup = {norm(bone.name):bone.name for bone in arm.data.bones}; result = {}
    for semantic, variants in SEMANTIC.items():
        for variant in variants:
            if variant in lookup: result[semantic] = lookup[variant]; break
    return result


def skinned_meshes(arm) -> list:
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and (obj.parent == arm or any(mod.type == "ARMATURE" and mod.object == arm for mod in obj.modifiers))]


def weighted_indices(mesh, bone_name: str, limit: int = 40) -> list[int]:
    group = mesh.vertex_groups.get(bone_name)
    if not group: return []
    result = []
    for vertex in mesh.data.vertices:
        if any(link.group == group.index and link.weight > .05 for link in vertex.groups):
            result.append(vertex.index)
            if len(result) >= limit: break
    return result


def evaluated_positions(mesh, indices: list[int]) -> list[Vector]:
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()); temp = evaluated.to_mesh()
    try: return [evaluated.matrix_world @ temp.vertices[index].co for index in indices if index < len(temp.vertices)]
    finally: evaluated.to_mesh_clear()


def deformation_checks() -> tuple[list[dict],dict]:
    checks = []; arm = select_armature()
    if not arm: add(checks,"armature","Esqueleto para deformação","fail","Nenhum armature foi encontrado na cena reaberta."); return checks,{"tested_joints":0,"responsive_joints":0}
    mapping = semantic_map(arm); meshes = skinned_meshes(arm)
    if not meshes: add(checks,"skinning","Malha vinculada ao rig","fail","Nenhuma malha skinnada foi encontrada para o armature principal."); return checks,{"tested_joints":0,"responsive_joints":0}
    tested = responsive = 0
    for label, semantic in JOINTS.items():
        bone_name = mapping.get(semantic)
        if not bone_name: add(checks,f"joint_{label}",label.replace("_"," ").title(),"warn","Osso semântico não identificado; articulação não foi testada."); continue
        pair = next(((mesh, weighted_indices(mesh,bone_name)) for mesh in meshes if weighted_indices(mesh,bone_name)), None)
        if not pair: add(checks,f"joint_{label}",label.replace("_"," ").title(),"warn",f"O osso {bone_name} não possui amostra de vértices com peso suficiente."); continue
        mesh,indices = pair; pose_bone = arm.pose.bones.get(bone_name)
        if not pose_bone: continue
        tested += 1; before = evaluated_positions(mesh,indices); old_matrix = pose_bone.matrix_basis.copy(); pose_bone.rotation_mode = "QUATERNION"
        axis = Vector((1,0,0)); delta = axis.rotation_difference(Vector((math.cos(math.radians(12)),math.sin(math.radians(12)),0))); pose_bone.rotation_quaternion = delta @ pose_bone.rotation_quaternion
        bpy.context.view_layer.update(); after = evaluated_positions(mesh,indices); movement = max((after[i]-before[i]).length for i in range(min(len(before),len(after)))) if before and after else 0.; finite = all(finite_vector(position) for position in after)
        pose_bone.matrix_basis = old_matrix; bpy.context.view_layer.update()
        if finite and movement > 1e-6: responsive += 1; add(checks,f"joint_{label}",label.replace("_"," ").title(),"pass",f"Deformação respondeu a uma rotação diagnóstica de 12° em {bone_name}.",{"max_vertex_movement":movement,"sampled_vertices":len(indices)})
        else: add(checks,f"joint_{label}",label.replace("_"," ").title(),"fail",f"A deformação não respondeu de forma finita/confiável em {bone_name}.",{"max_vertex_movement":movement,"finite":finite})
    if tested == 0: add(checks,"joint_coverage","Cobertura dos testes articulares","fail","Nenhuma das articulações principais pôde ser testada.")
    elif responsive < tested: add(checks,"joint_coverage","Cobertura dos testes articulares","warn",f"{responsive}/{tested} articulações testadas responderam corretamente.")
    else: add(checks,"joint_coverage","Cobertura dos testes articulares","pass",f"Todas as {tested} articulações testadas responderam corretamente.")
    return checks,{"tested_joints":tested,"responsive_joints":responsive,"semantic_bones":mapping}


def validate_source(source: Path):
    bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False); scene=[]; resources=[]; snap=scene_snapshot(); add(scene,"reopen_blend","Reabrir source.blend","pass","A cena autoritativa foi aberta pelo Blender sem erro.")
    add(scene,"mesh_presence","Malhas da cena","pass" if snap["mesh_count"]>0 else "fail",f"{snap['mesh_count']} malha(s) encontradas.",{"mesh_count":snap["mesh_count"]})
    dimensions=snap["bounds"]; finite=all(math.isfinite(v) and v>=0 for v in dimensions); add(scene,"finite_bounds","Escala e limites finitos","pass" if finite and max(dimensions,default=0)>0 else "fail",f"Extensão mundial XYZ = {dimensions}.",{"bounds":dimensions,"unit_scale":snap["unit_scale"]})
    if finite and max(dimensions,default=0)>0:
        ratio=dimensions[2]/max(dimensions[0],dimensions[1],1e-12); add(scene,"orientation","Orientação vertical","pass" if ratio>=.55 else "warn",f"Razão altura Z / maior extensão horizontal = {ratio:.3f}. A validação assume personagem com eixo vertical Z no Blender.",{"z_horizontal_ratio":ratio})
    missing=snap["missing_images"]; add(resources,"images","Recursos de imagem","pass" if not missing else "warn","Nenhuma imagem externa ausente." if not missing else "Imagens externas ausentes: "+", ".join(missing[:10]),{"missing_count":len(missing)})
    add(resources,"native_features","Recursos nativos da cena","pass",f"Shape keys={snap['shape_key_count']}, actions={snap['action_count']}, drivers={snap['driver_count']}, constraints={snap['constraint_count']}.",{k:snap[k] for k in ("shape_key_count","action_count","driver_count","constraint_count")})
    return scene,resources,snap


def imported_snapshot(path: Path, fmt: str) -> dict:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if fmt=="glb": bpy.ops.import_scene.gltf(filepath=str(path))
    elif fmt=="fbx": bpy.ops.import_scene.fbx(filepath=str(path),use_anim=True)
    else: raise RuntimeError("Formato de comparação desconhecido.")
    return scene_snapshot()


def compare_export(source: dict, exported: dict, fmt: str) -> list[dict]:
    checks=[]; add(checks,f"{fmt}_mesh",f"{fmt.upper()} contém malha","pass" if exported["mesh_count"]>0 else "fail",f"{exported['mesh_count']} malha(s) após reimportar {fmt.upper()}.")
    if source["armature_count"]: add(checks,f"{fmt}_rig",f"Rig no {fmt.upper()}","pass" if exported["armature_count"]>0 else "fail",f"Armatures fonte={source['armature_count']} / reimportado={exported['armature_count']}.")
    if source["action_count"]: add(checks,f"{fmt}_animations",f"Animações no {fmt.upper()}","pass" if exported["action_count"]>0 else "warn",f"Actions fonte={source['action_count']} / reimportado={exported['action_count']}.")
    if source["shape_key_count"]: add(checks,f"{fmt}_morphs",f"Morphs no {fmt.upper()}","pass" if exported["shape_key_count"]>0 else "warn",f"Shape keys fonte={source['shape_key_count']} / reimportado={exported['shape_key_count']}.")
    sb,eb=source["bounds"],exported["bounds"]
    if max(sb,default=0)>0 and max(eb,default=0)>0:
        ratio=eb[2]/sb[2] if sb[2]>1e-12 else 0; add(checks,f"{fmt}_scale",f"Escala do {fmt.upper()}","pass" if .8<=ratio<=1.25 else "warn",f"Razão de altura reimportada/fonte = {ratio:.4f}.",{"height_ratio":ratio,"source_height":sb[2],"export_height":eb[2]})
    return checks


def inspect_png(path: Path) -> dict:
    image=bpy.data.images.load(str(path),check_existing=False)
    try: return {"width":int(image.size[0]),"height":int(image.size[1]),"channels":int(image.channels),"has_alpha":int(image.channels)>=4}
    finally: bpy.data.images.remove(image)


def main() -> None:
    args=sys.argv[sys.argv.index("--")+1:]
    if len(args)!=2: raise RuntimeError("Argumentos internos de validação inválidos.")
    request=read_json(args[0]); report_path=Path(args[1]); source=Path(str(request.get("source_blend",""))).resolve()
    if not source.is_file(): raise RuntimeError("source.blend do projeto não existe.")
    print("BODIEZ_PROGRESS:12:Reabrindo a cena autoritativa",flush=True); scene,resources,source_snap=validate_source(source)
    print("BODIEZ_PROGRESS:35:Testando deformação nas articulações principais",flush=True); deformation,deformation_metrics=deformation_checks(); exports=[]; files=request.get("export_files") if isinstance(request.get("export_files"),dict) else {}
    if files.get("glb"): print("BODIEZ_PROGRESS:58:Reimportando GLB para comparar rig, escala e recursos",flush=True); exports.extend(compare_export(source_snap,imported_snapshot(Path(files["glb"]),"glb"),"glb"))
    else: add(exports,"glb_missing","Comparação GLB","warn","Nenhum GLB foi selecionado nesta validação.")
    if files.get("fbx"): print("BODIEZ_PROGRESS:72:Reimportando FBX para comparação",flush=True); exports.extend(compare_export(source_snap,imported_snapshot(Path(files["fbx"]),"fbx"),"fbx"))
    else: add(exports,"fbx_missing","Comparação FBX","warn","Nenhum FBX foi selecionado nesta validação.")
    if files.get("png"):
        print("BODIEZ_PROGRESS:84:Validando render PNG transparente",flush=True); png=inspect_png(Path(files["png"])); add(exports,"png_dimensions","Dimensões do PNG","pass" if png["width"]>0 and png["height"]>0 else "fail",f"PNG = {png['width']}×{png['height']} px.",png); add(exports,"png_alpha","Canal alpha do PNG","pass" if png["has_alpha"] else "fail","A imagem possui canal alpha." if png["has_alpha"] else "O PNG não possui canal alpha.",png)
    else: add(exports,"png_missing","Render PNG","warn","Nenhum PNG foi selecionado nesta validação.")
    add(exports,"editable_blend","BLEND exportado","pass" if files.get("blend") else "warn","A exportação editável .blend existe no conjunto selecionado." if files.get("blend") else "O conjunto selecionado não contém character-editable.blend; source.blend continua sendo a cena autoritativa do projeto.")
    limitations=["A orientação vertical é verificada assumindo eixo Z no Blender; personagens deliberadamente deitados podem gerar aviso.","O teste de deformação usa pequenas rotações diagnósticas e pesos existentes; não substitui inspeção artística de interpenetrações e volume.","Reimportar GLB/FBX verifica estrutura, escala e presença de recursos, mas não prova fidelidade visual em todos os softwares de destino.","Drivers, constraints e modificadores proprietários do Blender não possuem equivalência editável garantida em GLB/FBX.","A validação não presume APIs, nomes de shape keys ou drivers proprietários do Bodiez; ela mede apenas recursos realmente presentes."]
    data={"format_version":1,"scene":scene,"deformation":deformation,"exports":exports,"resources":resources,"metrics":{"source":source_snap,"deformation":deformation_metrics},"limitations":limitations}; report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); print("BODIEZ_PROGRESS:100:Validação Blender concluída",flush=True); print("BODIEZ_RESULT:"+json.dumps({"ok":True}),flush=True)

try: main()
except Exception as exc:
    traceback.print_exc(); print("BODIEZ_RESULT:"+json.dumps({"ok":False,"error":str(exc)}),flush=True); raise
