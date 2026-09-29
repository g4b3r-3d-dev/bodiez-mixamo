"""Render repeatable 360-degree comparisons of real exported body geometry."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_body_comparison import import_snapshot, bounds, text_label


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='+', type=Path, required=True)
    parser.add_argument('--labels', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--angles', nargs='*', type=int, default=list(range(0, 360, 30)))
    parser.add_argument('--elevated', action='store_true')
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--focus-markers', type=Path, help='Crop only render snapshots around the breast markers')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    assert len(args.models) == len(args.labels)
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    variants = []; frame = None
    for path in args.models:
        meshes, frame = import_snapshot(path, frame)
        variants.append(meshes)
    low, high = bounds(variants[0]); height = high.z - low.z; center = (low + high) / 2
    width = high.x - low.x
    if args.focus_markers:
        import bmesh
        markers = json.loads(args.focus_markers.read_text())
        p = (Vector(markers['left']) + Vector(markers['right'])) / 2
        p = Vector((p.x, -p.z, p.y))
        center = Vector((p.dot(frame[0]), -p.dot(frame[1]), p.dot(frame[2])))
        width, height = markers['radius'] * 4.4, markers['radius'] * 3.6
        for group in variants:
            for mesh in group:
                bm = bmesh.new(); bm.from_mesh(mesh.data)
                for axis, extent in ((0, width * .5), (2, height * .5)):
                    for sign in (-1, 1):
                        position = center.copy(); position[axis] += extent * sign
                        normal = Vector(); normal[axis] = sign
                        bmesh.ops.bisect_plane(bm, geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                            plane_co=position, plane_no=normal, clear_outer=True, dist=1e-8)
                bm.to_mesh(mesh.data); bm.free()
    mat = bpy.data.materials.new('Neutral'); mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (.38, .47, .55, 1)
    bsdf.inputs['Roughness'].default_value = .7
    for meshes in variants:
        for mesh in meshes:
            for v in mesh.data.vertices: v.co -= center
            mesh.data.materials.clear(); mesh.data.materials.append(mat)
            for polygon in mesh.data.polygons: polygon.material_index = 0
    spacing = max(height * .85, width * 1.1)
    shifts = [(i - (len(variants) - 1) / 2) * spacing for i in range(len(variants))]
    for label, shift in zip(args.labels, shifts):
        text_label(label, shift, height * .64, height * .035)
    scene = bpy.context.scene
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.08, .08, .08, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .6
    # Repeat identical local lights for every comparison column.
    for shift in shifts:
        for loc, energy in [((-height, -height * 2, height * 1.8), 100), ((height, -height, height * .8), 55)]:
            bpy.ops.object.light_add(type='AREA', location=(loc[0] + shift, loc[1], loc[2]))
            light = bpy.context.object; light.data.energy = energy * height * height
            light.data.size = height * 1.5
            light.rotation_euler = (Vector((shift, 0, 0)) - light.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.object.camera_add(location=(0, -height * 5, 0))
    camera = bpy.context.object; camera.rotation_euler = (math.pi / 2, 0, 0)
    camera.data.type = 'ORTHO'; camera.data.ortho_scale = spacing * len(variants)
    scene.camera = camera
    scene.render.engine = 'CYCLES'; scene.cycles.samples = args.samples; scene.cycles.use_denoising = False
    scene.render.threads_mode = 'FIXED'; scene.render.threads = 6
    scene.render.resolution_x = 600 * len(variants)
    scene.render.resolution_y = int(scene.render.resolution_x * height * 1.4 / camera.data.ortho_scale)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    args.output.mkdir(parents=True, exist_ok=True)
    views = [(yaw, 0) for yaw in args.angles]
    if args.elevated: views += [(yaw, elevation) for elevation in (-20, 20) for yaw in (0, 180)]
    for yaw, elevation in views:
        rotation = Matrix.Rotation(math.radians(elevation), 4, 'X') @ Matrix.Rotation(math.radians(yaw), 4, 'Z')
        for meshes, shift in zip(variants, shifts):
            for mesh in meshes: mesh.matrix_world = Matrix.Translation((shift, 0, 0)) @ rotation
        filename = f'view-{yaw:03d}-{elevation:+03d}.png'
        scene.render.filepath = str((args.output / filename).resolve())
        bpy.ops.render.render(write_still=True)
        print('ORBIT_RENDERED', filename, flush=True)
    (args.output / 'views.json').write_text(json.dumps({'models': [str(p) for p in args.models],
        'labels': args.labels, 'views': views, 'same_scale': True, 'cropped_render_only': bool(args.focus_markers)}, indent=2))


if __name__ == '__main__': main()
