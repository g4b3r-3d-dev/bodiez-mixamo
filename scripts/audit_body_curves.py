"""Measure mesh distortion across curve intensities and representative rig poses."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_ray_tri

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend/blender_scripts'))
from body_customize import armature, matches, meshes, body_reference


def points(mesh):
    ev = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()); data = ev.to_mesh()
    try: return np.array([tuple(ev.matrix_world @ v.co) for v in data.vertices])
    finally: ev.to_mesh_clear()


def metrics(before, after, triangles, edges):
    p, q = before[triangles], after[triangles]
    bn = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    an = np.cross(q[:, 1] - q[:, 0], q[:, 2] - q[:, 0])
    ba, aa = np.linalg.norm(bn, axis=1), np.linalg.norm(an, axis=1)
    valid = ba > 1e-12
    ratio = aa[valid] / ba[valid]
    length_before = np.linalg.norm(before[edges[:, 0]] - before[edges[:, 1]], axis=1)
    length_after = np.linalg.norm(after[edges[:, 0]] - after[edges[:, 1]], axis=1)
    stretch = length_after[length_before > 1e-10] / length_before[length_before > 1e-10]
    angle = np.degrees(np.arccos(np.clip(np.sum(bn[valid] * an[valid], axis=1) / np.maximum(ba[valid] * aa[valid], 1e-30), -1, 1)))
    displacement = np.linalg.norm(after - before, axis=1)
    return {'finite': bool(np.isfinite(after).all()), 'vertices': len(before),
            'changed_vertices': int((displacement > 1e-6).sum()),
            'max_displacement': float(displacement.max()),
            'new_degenerate_triangles': int(((aa < 1e-12) & valid).sum()),
            'normal_rotations_over_90': int((angle > 90).sum()),
            'max_normal_rotation_degrees': float(angle.max()),
            'triangle_area_ratio_range': [float(ratio.min()), float(ratio.max())],
            'edge_length_ratio_range': [float(stretch.min()), float(stretch.max())],
            'edge_length_ratio_p01_p99': np.percentile(stretch, [1, 99]).tolist()}


def intersections(points, triangles):
    """Non-adjacent triangle crossings; excludes contacts and coplanar overlap."""
    vertices = [Vector(p) for p in points]
    tree = BVHTree.FromPolygons(vertices, triangles.tolist(), all_triangles=True, epsilon=0)
    found = set()
    for i, j in tree.overlap(tree):
        if i >= j or set(triangles[i]) & set(triangles[j]): continue
        a, b = [[vertices[k] for k in triangles[index]] for index in (i, j)]
        if any((p - q).length < 1e-7 for p in a for q in b): continue
        for edges, face in ((a, b), (b, a)):
            for start, end in zip(edges, edges[1:] + edges[:1]):
                ray = end - start
                hit = intersect_ray_tri(*face, ray, start, True)
                if hit is not None and ray.length_squared > 1e-20:
                    t = (hit - start).dot(ray) / ray.length_squared
                    if 1e-6 < t < 1 - 1e-6: found.add((i, j))
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--blend', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--control', choices=['feminine_curves','breast_size'], default='feminine_curves')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()), load_ui=False)
    arm = armature(); body_reference(arm); semantic = matches(arm); body = meshes(arm)
    report = {'control': args.control, 'poses': {}, 'profiles': {}}
    key_name = 'Bodiez_Auto_' + args.control
    values = (-.5, -.25, .25, .35, .5, .65, .75, 1., 0.) if args.control == 'breast_size' else (.25, .35, .5, .65, .75, 1., 0.)
    def head(n): return arm.matrix_world @ arm.data.bones[semantic[n]].head_local
    origin = head('hips'); up = (head('head') - origin).normalized(); span = (head('head') - origin).length
    left = head('left_upper_arm') - head('right_upper_arm'); left = (left - up * left.dot(up)).normalized()
    front = left.cross(up).normalized()
    def profile(p):
        coords = (p - np.array(origin)) @ np.array([left, front, up]).T
        result = []
        for z in np.arange(-.4, 1.01, .025):
            selected = coords[(np.abs(coords[:, 2] / span - z) < .018) & (np.abs(coords[:, 0]) < span * .65)]
            if len(selected) > 5:
                result.append({'z': round(float(z), 3), 'width': float(np.ptp(selected[:, 0])), 'depth': float(np.ptp(selected[:, 1]))})
        return result
    # Compare to the *same pose* at zero curves, so joint rotation is not counted as morph damage.
    for pose, rotations in [('rest', {}), ('hip_flexion', {'left_thigh': (35, 0, 0), 'left_shin': (-55, 0, 0)}),
                            ('arms_down', {'left_upper_arm': (0, 0, 60), 'right_upper_arm': (0, 0, -60)})]:
        body_reference(arm)
        for name, rotation in rotations.items():
            if name in semantic:
                bone = arm.pose.bones[semantic[name]]; bone.rotation_mode = 'XYZ'
                bone.rotation_euler = tuple(math.radians(v) for v in rotation)
        results = {}
        for mesh in body:
            key = mesh.data.shape_keys.key_blocks.get(key_name) if mesh.data.shape_keys else None
            if key is None: continue
            mesh.data.calc_loop_triangles()
            triangles = np.array([t.vertices[:] for t in mesh.data.loop_triangles])
            edges = np.array([e.vertices[:] for e in mesh.data.edges])
            key.value = 0; bpy.context.view_layer.update(); baseline = points(mesh)
            original_crossings = intersections(baseline, triangles) if pose == 'rest' else set()
            if pose == 'rest':
                locations = {}
                for i, j in original_crossings:
                    center = baseline[np.concatenate((triangles[i], triangles[j]))].mean(axis=0) - np.array(origin)
                    x, z = abs(float(center @ np.array(left))) / span, float(center @ np.array(up)) / span
                    region = 'head_neck' if z > .8 else 'arms_hands' if x > .65 else 'legs_feet' if z < -.45 else 'torso_pelvis'
                    locations[region] = locations.get(region, 0) + 1
                report['baseline_crossing_regions'] = locations
            runs = {}
            for value in values:
                key.value = value; bpy.context.view_layer.update(); current = points(mesh)
                runs[str(value)] = metrics(baseline, current, triangles, edges)
                if pose == 'rest' and value in (-.5, -.25, .35, .65, 1., 0.):
                    crossing = intersections(current, triangles)
                    runs[str(value)]['non_adjacent_triangle_crossings'] = len(crossing)
                    runs[str(value)]['new_crossings'] = len(crossing - original_crossings)
                    runs[str(value)]['baseline_crossings'] = len(original_crossings)
                if pose == 'rest': report['profiles'][str(value)] = profile(current)
            results[mesh.name] = runs
        report['poses'][pose] = results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    assert any(report['poses'].values()), 'No matching morph found to audit'
    for pose in report['poses'].values():
        for runs in pose.values():
            for value, run in runs.items():
                assert run['finite'] and run['new_degenerate_triangles'] == 0, run
                assert run['normal_rotations_over_90'] == 0, run
                assert run.get('new_crossings', 0) == 0, run
                if float(value) == 0: assert run['max_displacement'] < 1e-7, run
    print('CURVE_AUDIT', str(args.output), flush=True)


if __name__ == '__main__': main()
