from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector

RESULT_PREFIX = "BODIEZ_RESULT:"


def read_json(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise RuntimeError("Pedido de exportação inválido.")
    return value


def scene_features() -> dict:
    meshes=[o for o in bpy.context.scene.objects if o.type=="MESH"]; armatures=[o for o in bpy.context.scene.objects if o.type=="ARMATURE"]
    shape_keys=drivers=constraints=nla_tracks=0; modifiers={}; complex_materials=[]; missing_images=[]; external_images=[]
    for obj in bpy.context.scene.objects:
        constraints+=len(obj.constraints); ad=getattr(obj,"animation_data",None)
        if ad: drivers+=len(ad.drivers); nla_tracks+=len(ad.nla_tracks)
        for modifier in getattr(obj,"modifiers",[]): modifiers[modifier.type]=modifiers.get(modifier.type,0)+1
        if obj.type=="MESH" and obj.data.shape_keys:
            keys=obj.data.shape_keys; shape_keys+=max(0,len(keys.key_blocks)-1); kad=keys.animation_data
            if kad: drivers+=len(kad.drivers); nla_tracks+=len(kad.nla_tracks)
    for material in bpy.data.materials:
        if not material.use_nodes or not material.node_tree: continue
        node_types={node.type for node in material.node_tree.nodes}; supported={"OUTPUT_MATERIAL","BSDF_PRINCIPLED","TEX_IMAGE","NORMAL_MAP","MAPPING","TEX_COORD","RGB","VALUE"}
        if node_types-supported: complex_materials.append(material.name)
    for image in bpy.data.images:
        if image.source!="FILE" or image.packed_file or not image.filepath: continue
        path=Path(bpy.path.abspath(image.filepath)); external_images.append(image.name)
        if not path.is_file(): missing_images.append(image.name)
    return {"mesh_count":len(meshes),"armature_count":len(armatures),"shape_key_count":shape_keys,"action_count":len(bpy.data.actions),"driver_count":drivers,"constraint_count":constraints,"nla_track_count":nla_tracks,"modifiers":modifiers,"complex_materials":sorted(set(complex_materials)),"external_images":sorted(set(external_images)),"missing_images":sorted(set(missing_images))}


def warnings_for(features: dict, formats: list[str]) -> list[dict]:
    warnings=[]
    def add(scope,code,message): warnings.append({"scope":scope,"code":code,"message":message})
    if features["missing_images"]: add("all","missing_images","Há imagens externas ausentes: "+", ".join(features["missing_images"][:8]))
    if "blend" in formats and features["external_images"]: add("blend","external_files","O Blender tentará empacotar imagens externas no .blend editável; confira o relatório de empacotamento.")
    if any(f in formats for f in ("glb","fbx")) and features["driver_count"]: add("interchange","drivers","Drivers do Blender não são preservados como lógica editável em GLB/FBX; apenas o estado/animação exportável pode sobreviver.")
    if any(f in formats for f in ("glb","fbx")) and features["constraint_count"]: add("interchange","constraints","Constraints não são portáveis como sistema de rig; animações devem estar bakeadas para máxima compatibilidade.")
    nonportable={name:count for name,count in features["modifiers"].items() if name!="ARMATURE"}
    if any(f in formats for f in ("glb","fbx")) and nonportable: add("interchange","modifiers","Modificadores não-armature podem não ser reproduzidos no destino: "+", ".join(sorted(nonportable)))
    if any(f in formats for f in ("glb","fbx")) and features["complex_materials"]: add("interchange","materials","Materiais com nós complexos podem ser simplificados: "+", ".join(features["complex_materials"][:8]))
    if "fbx" in formats and features["shape_key_count"]: add("fbx","shape_keys","FBX pode transportar blend shapes, mas a fidelidade de nomes, ranges e drivers varia entre aplicações.")
    return warnings


def try_pack_resources():
    try: bpy.ops.file.pack_all(); return True,None
    except Exception as exc: return False,str(exc)


def save_editable_blend(path: Path) -> dict:
    path.parent.mkdir(parents=True,exist_ok=True); packed,error=try_pack_resources(); bpy.context.scene["bodiez_export_kind"]="editable_blend"; bpy.context.scene["bodiez_project_format_version"]=1; bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=False); return {"resources_packed":packed,"pack_error":error}


def export_glb(path: Path):
    path.parent.mkdir(parents=True,exist_ok=True); bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",use_selection=False,export_yup=True,export_skins=True,export_morph=True,export_animations=True,export_cameras=False,export_lights=False)


def export_fbx(path: Path):
    path.parent.mkdir(parents=True,exist_ok=True); bpy.ops.export_scene.fbx(filepath=str(path),use_selection=False,object_types={"ARMATURE","MESH","EMPTY"},add_leaf_bones=False,bake_anim=True,bake_anim_use_all_actions=True,bake_anim_use_nla_strips=True,path_mode="COPY",embed_textures=True)


def world_bounds():
    points=[obj.matrix_world@Vector(corner) for obj in bpy.context.scene.objects if obj.type=="MESH" for corner in obj.bound_box]
    if not points: raise RuntimeError("Não há malha visível para renderizar.")
    low=Vector(tuple(min(p[i] for p in points) for i in range(3))); high=Vector(tuple(max(p[i] for p in points) for i in range(3))); return low,high


def point_at(obj,target): obj.rotation_euler=(target-obj.location).to_track_quat("-Z","Y").to_euler()


def render_transparent_png(path: Path,resolution: int):
    scene=bpy.context.scene; low,high=world_bounds(); center=(low+high)*.5; size=high-low; radius=max(size.x,size.y,size.z,.5); old_camera=scene.camera; temp=[]
    bpy.ops.object.camera_add(location=(center.x,center.y-radius*2.8,center.z+radius*.15)); camera=bpy.context.object; camera.name="Bodiez_Export_Camera"; camera.data.lens=55; point_at(camera,center); scene.camera=camera; temp.append(camera)
    for location,energy,size_value in (((center.x-radius*1.5,center.y-radius*1.8,center.z+radius*2),900,radius*1.5),((center.x+radius*1.7,center.y-radius*.8,center.z+radius*.8),500,radius*1.2)):
        bpy.ops.object.light_add(type="AREA",location=location); light=bpy.context.object; light.data.energy=energy; light.data.shape="DISK"; light.data.size=max(size_value,.5); point_at(light,center); temp.append(light)
    scene.render.film_transparent=True; scene.render.image_settings.file_format="PNG"; scene.render.image_settings.color_mode="RGBA"; scene.render.image_settings.color_depth="8"; scene.render.resolution_x=resolution; scene.render.resolution_y=resolution; scene.render.resolution_percentage=100; scene.render.filepath=str(path)
    try: scene.render.engine="BLENDER_EEVEE_NEXT"
    except Exception:
        try: scene.render.engine="BLENDER_EEVEE"
        except Exception: pass
    bpy.ops.render.render(write_still=True); scene.camera=old_camera
    for obj in temp:
        if obj and obj.name in bpy.data.objects: bpy.data.objects.remove(obj,do_unlink=True)


def main():
    args=sys.argv[sys.argv.index("--")+1:]
    if len(args)!=4: raise RuntimeError("Argumentos internos de exportação inválidos.")
    source,request_path,output_root,report_path=args; request=read_json(request_path); formats=[str(v).lower() for v in request.get("formats",[])]; resolution=int(request.get("resolution",1024)); outputs=request.get("outputs") if isinstance(request.get("outputs"),dict) else {}; out=Path(output_root).resolve(); out.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(Path(source).resolve()),load_ui=False); features=scene_features()
    if not features["mesh_count"]: raise RuntimeError("O projeto não contém malha para exportar.")
    report={"format_version":1,"source_mode":"editable_blender_scene","interchange_semantics":"project_controls_are_baked_as_scene_state","features":features,"warnings":warnings_for(features,formats),"outputs":{}}; total=max(1,len(formats)); completed=0
    if "blend" in formats:
        report["outputs"]["blend"]={"kind":"editable",**save_editable_blend(out/str(outputs.get("blend","character-editable.blend")))}; completed+=1; print(f"BODIEZ_PROGRESS:{int(10+75*completed/total)}:Arquivo .blend editável salvo",flush=True)
    if "glb" in formats:
        export_glb(out/str(outputs.get("glb","character.glb"))); report["outputs"]["glb"]={"kind":"interchange","rig":True,"materials":True,"animations":True,"morph_targets":True,"bodiez_controls":False}; completed+=1; print(f"BODIEZ_PROGRESS:{int(10+75*completed/total)}:GLB exportado",flush=True)
    if "fbx" in formats:
        export_fbx(out/str(outputs.get("fbx","character.fbx"))); report["outputs"]["fbx"]={"kind":"interchange","rig":True,"materials":"best_effort","animations":True,"blend_shapes":"best_effort","bodiez_controls":False}; completed+=1; print(f"BODIEZ_PROGRESS:{int(10+75*completed/total)}:FBX exportado",flush=True)
    if "png" in formats:
        render_transparent_png(out/str(outputs.get("png","character.png")),resolution); report["outputs"]["png"]={"kind":"render","transparent_background":True,"resolution":resolution}; completed+=1; print(f"BODIEZ_PROGRESS:{int(10+75*completed/total)}:PNG transparente renderizado",flush=True)
    Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); print(RESULT_PREFIX+json.dumps({"ok":True,"formats":formats}),flush=True)


try: main()
except Exception as exc:
    traceback.print_exc(); print(RESULT_PREFIX+json.dumps({"ok":False,"error":str(exc)}),flush=True); raise
