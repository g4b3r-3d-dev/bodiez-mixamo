"""Render two body GLBs with identical framing. Run inside Blender, not Python."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def import_snapshot(path, frame=None):
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in bpy.data.objects if o not in previous]
    arm = next(o for o in imported if o.type == 'ARMATURE')
    def head(name):
        bone = next(b for b in arm.pose.bones if b.name.split(':')[-1].split('.')[0] == name)
        return arm.matrix_world @ bone.head
    if frame is None:
        up = (head('Head') - head('Hips')).normalized()
        lateral = head('LeftArm') - head('RightArm')
        lateral = (lateral - up * lateral.dot(up)).normalized()
        front = lateral.cross(up).normalized()
        frame = (lateral, front, up)
    graph = bpy.context.evaluated_depsgraph_get()
    snapshots = []
    for obj in imported:
        if obj.type != 'MESH' or not any(m.type == 'ARMATURE' for m in obj.modifiers):
            continue
        ev = obj.evaluated_get(graph)
        mesh = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=graph)
        for vertex in mesh.vertices:
            p = ev.matrix_world @ vertex.co
            vertex.co = (p.dot(frame[0]), -p.dot(frame[1]), p.dot(frame[2]))
        copy = bpy.data.objects.new('Snapshot_' + obj.name, mesh)
        bpy.context.collection.objects.link(copy)
        snapshots.append(copy)
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    return snapshots, frame


def bounds(objects):
    points = [v.co for o in objects for v in o.data.vertices]
    return Vector(tuple(min(p[i] for p in points) for i in range(3))), Vector(tuple(max(p[i] for p in points) for i in range(3)))


def text_label(text, x, z, size):
    curve = bpy.data.curves.new('Label', 'FONT')
    curve.body = text; curve.align_x = 'CENTER'; curve.size = size
    obj = bpy.data.objects.new('Label', curve); bpy.context.collection.objects.link(obj)
    obj.location = (x, -.3, z); obj.rotation_euler = (math.pi / 2, 0, 0)
    mat = bpy.data.materials.get('Label') or bpy.data.materials.new('Label')
    mat.diffuse_color = (.85, .9, 1, 1); curve.materials.append(mat)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='DEPOIS')
    parser.add_argument('--clay', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    before, frame = import_snapshot(args.before)
    after, _ = import_snapshot(args.after, frame)
    lo, hi = bounds(before); center = (lo + hi) * .5; height = hi.z - lo.z
    alo, ahi = bounds(after)
    width = max(hi.x-lo.x, ahi.x-alo.x)
    separation = width * 1.15
    for objects, shift in ((before, -separation/2), (after, separation/2)):
        for o in objects:
            o.location = Vector((shift, 0, 0)) - center
    if args.clay:
        mat = bpy.data.materials.new('Neutral comparison material'); mat.diffuse_color = (.42,.54,.64,1)
        mat.use_nodes = True
        node = mat.node_tree.nodes.get('Principled BSDF')
        node.inputs['Base Color'].default_value = (.42,.54,.64,1); node.inputs['Roughness'].default_value = .8
        for obj in before+after:
            obj.data.materials.clear(); obj.data.materials.append(mat)
            for polygon in obj.data.polygons: polygon.material_index=0
    text_label('ANTES', -separation/2, height*.64, height*.042)
    text_label(args.label, separation/2, height*.64, height*.042)
    text_label('Mesma camera, luz e escala | GLB real da Etapa 4', 0, -height*.67, height*.024)
    scene = bpy.context.scene
    bpy.ops.object.camera_add(location=(0,-height*4,height*.06))
    camera = bpy.context.object; camera.rotation_euler=(math.pi/2,0,0); camera.data.type='ORTHO'; camera.data.ortho_scale=max(width*2.5,height*2.45); scene.camera=camera
    for loc, energy, size in (((-height,-height*2,height*2),350,2),((height,-height,height),180,1.5)):
        bpy.ops.object.light_add(type='AREA',location=loc); light=bpy.context.object
        light.data.energy=energy; light.data.shape='DISK'; light.data.size=height*size
        light.rotation_euler=(-light.location).to_track_quat('-Z','Y').to_euler()
    scene.world.color=(.18,.18,.18)
    scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=48; scene.cycles.use_denoising=False
    scene.render.resolution_x=1600; scene.render.resolution_y=1000; scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'; scene.render.film_transparent=False
    args.output.parent.mkdir(parents=True,exist_ok=True); scene.render.filepath=str(args.output.resolve())
    bpy.ops.render.render(write_still=True)
    print('COMPARISON_RENDERED',str(args.output),flush=True)

if __name__=='__main__': main()
