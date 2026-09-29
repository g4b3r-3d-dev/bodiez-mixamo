"""Independent mesh measurements for accepted body combinations in three poses."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_body_curves import metrics, points
from body_customize import armature, matches, meshes


def snapshot(path, rotations):
    bpy.ops.wm.open_mainfile(filepath=str(path.resolve()), load_ui=False)
    arm = armature(); semantic = matches(arm)
    for name, rotation in rotations.items():
        if name in semantic:
            bone = arm.pose.bones[semantic[name]]
            bone.rotation_mode = 'XYZ'
            bone.rotation_euler = tuple(math.radians(v) for v in rotation)
    bpy.context.view_layer.update()
    root = bpy.data.objects.get('Bodiez_CustomizationRoot')
    height = root.scale.x if root else 1.
    result = {}
    for mesh in meshes(arm):
        mesh.data.calc_loop_triangles()
        result[mesh.name] = (points(mesh) / height,
                             np.array([t.vertices[:] for t in mesh.data.loop_triangles]),
                             np.array([e.vertices[:] for e in mesh.data.edges]))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--variants', nargs='+', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    report = {}
    for pose, rotations in [('rest', {}), ('hip_flexion', {'left_thigh': (35, 0, 0), 'left_shin': (-55, 0, 0)}),
                            ('arms_down', {'left_upper_arm': (0, 0, 60), 'right_upper_arm': (0, 0, -60)})]:
        baseline = snapshot(args.baseline, rotations)
        report[pose] = {}
        for path in args.variants:
            current = snapshot(path, rotations)
            runs = {}
            for name, (before, triangles, edges) in baseline.items():
                after = current[name][0]
                assert np.array_equal(triangles, current[name][1])
                runs[name] = metrics(before, after, triangles, edges)
            report[pose][path.stem] = runs
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    for pose in report.values():
        for variant in pose.values():
            for run in variant.values():
                assert run['finite'] and run['new_degenerate_triangles'] == 0
                assert run['normal_rotations_over_90'] == 0
    print('NATURAL_POSE_AUDIT_OK', flush=True)


if __name__ == '__main__':
    main()
