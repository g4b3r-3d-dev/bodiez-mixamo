"""Check combined deformation against the original surface before exporting.

These are geometric editing safeguards, not a test of anatomical realism.
Existing defects remain part of the baseline. Coplanar contacts are not crossings.
"""
import bpy
import math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import closest_point_on_tri, intersect_line_line, intersect_ray_tri


def touching(a, b, tolerance):
    """Include pre-existing coplanar overlaps/contacts in the baseline defects."""
    a, b = [Vector(p) for p in a], [Vector(p) for p in b]
    for vertices, face in ((a, b), (b, a)):
        if any((p - closest_point_on_tri(p, *face)).length <= tolerance for p in vertices):
            return True
        for start, end in zip(vertices, vertices[1:] + vertices[:1]):
            ray = end - start
            hit = intersect_ray_tri(*face, ray, start, True)
            if hit is not None and ray.length_squared > 1e-20:
                if 0 <= (hit - start).dot(ray) / ray.length_squared <= 1:
                    return True
    for p, q in zip(a, a[1:] + a[:1]):
        for r, s in zip(b, b[1:] + b[:1]):
            nearest = intersect_line_line(p, q, r, s)
            if nearest is None:
                continue
            x, y = nearest
            u, v = q - p, s - r
            if (u.length_squared > 0 and v.length_squared > 0
                    and 0 <= (x - p).dot(u) / u.length_squared <= 1
                    and 0 <= (y - r).dot(v) / v.length_squared <= 1
                    and (x - y).length <= tolerance):
                return True
    return False


def points(mesh):
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data = evaluated.to_mesh()
    try:
        return np.array([tuple(evaluated.matrix_world @ vertex.co) for vertex in data.vertices])
    finally:
        evaluated.to_mesh_clear()


def crossings(points, triangles):
    vertices = [Vector(point) for point in points]
    # Quantized imported surfaces and existing contacts can change triangle pairs
    # under sub-millimetre motion. Only penetration deeper than 0.02% of extent
    # is treated as a new crossing; this is not a watertightness certification.
    tolerance = max(float(np.ptp(points, axis=0).max()) * .0002, 1e-9)
    tree = BVHTree.FromPolygons(vertices, triangles.tolist(), all_triangles=True)
    found = set()
    for i, j in tree.overlap(tree):
        if i >= j or set(triangles[i]) & set(triangles[j]):
            continue
        a, b = points[triangles[i]], points[triangles[j]]
        if np.min(np.linalg.norm(a[:, None] - b[None, :], axis=2)) < tolerance:
            continue
        for edges, face in ((a, b), (b, a)):
            e1, e2 = face[1] - face[0], face[2] - face[0]
            normal = np.cross(e1, e2)
            area = np.linalg.norm(normal)
            if area < 1e-12:
                continue
            normal /= area
            for start, end in zip(edges, np.roll(edges, -1, axis=0)):
                d0, d1 = (start - face[0]) @ normal, (end - face[0]) @ normal
                if d0 * d1 >= 0 or min(abs(d0), abs(d1)) <= tolerance:
                    continue
                ray = end - start
                h = np.cross(ray, e2)
                determinant = e1 @ h
                if abs(determinant) < area * np.linalg.norm(ray) * 1e-8:
                    continue
                offset = start - face[0]
                u = (offset @ h) / determinant
                q = np.cross(offset, e1)
                v = (ray @ q) / determinant
                t = (e2 @ q) / determinant
                # Strict triangle interior; contacts along a seam are excluded.
                if min(u, v, 1 - u - v, t, 1 - t) > 1e-6:
                    found.add((i, j))
    return found


class ShapeGuard:
    def __init__(self, meshes, arm=None, semantic=None):
        self.arm = arm
        self.semantic = semantic or {}
        self.pose_guards = {}
        self.baseline = []
        for mesh in meshes:
            mesh.data.calc_loop_triangles()
            triangles = np.array([t.vertices[:] for t in mesh.data.loop_triangles], dtype=int).reshape(-1, 3)
            if not len(triangles):
                continue
            before = points(mesh)
            if not np.isfinite(before).all() or len(before) != len(mesh.data.vertices):
                raise RuntimeError('A malha base não permite validar a deformação corporal.')
            edges = np.array([e.vertices[:] for e in mesh.data.edges], dtype=int).reshape(-1, 2)
            self.baseline.append((mesh, before, triangles, edges, None))
        if not self.baseline:
            raise RuntimeError('Nenhuma superfície triangular disponível para validar o corpo.')
        if arm is not None:
            for name, rotations in [('hip_flexion', {'left_thigh': (35, 0, 0), 'left_shin': (-55, 0, 0)}),
                                    ('arms_down', {'left_upper_arm': (0, 0, 60), 'right_upper_arm': (0, 0, -60)})]:
                saved = self.pose(rotations)
                try:
                    self.pose_guards[name] = (rotations, ShapeGuard(meshes))
                finally:
                    self.restore_pose(saved)

    def pose(self, rotations):
        saved = []
        for name, rotation in rotations.items():
            if name not in self.semantic:
                continue
            bone = self.arm.pose.bones[self.semantic[name]]
            saved.append((bone, bone.rotation_mode, bone.matrix_basis.copy()))
            bone.rotation_mode = 'XYZ'
            bone.rotation_euler = tuple(math.radians(v) for v in rotation)
        bpy.context.view_layer.update()
        return saved

    def restore_pose(self, saved):
        for bone, mode, matrix in saved:
            bone.rotation_mode = mode
            bone.matrix_basis = matrix
        bpy.context.view_layer.update()

    def check(self, height=1, check_crossings=True):
        results = {}
        accepted = True
        for index, (mesh, before, triangles, edges, original_crossings) in enumerate(self.baseline):
            # Uniform height changes preserve shape. Compare in original-size coordinates.
            after = points(mesh) / height
            if after.shape != before.shape or not np.isfinite(after).all():
                return False, {mesh.name: {'finite': False}}
            p, q = before[triangles], after[triangles]
            bn = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
            an = np.cross(q[:, 1] - q[:, 0], q[:, 2] - q[:, 0])
            ba, aa = np.linalg.norm(bn, axis=1), np.linalg.norm(an, axis=1)
            valid = ba > 1e-12
            cosine = np.sum(bn[valid] * an[valid], axis=1) / np.maximum(ba[valid] * aa[valid], 1e-30)
            old_lengths = np.linalg.norm(before[edges[:, 0]] - before[edges[:, 1]], axis=1)
            new_lengths = np.linalg.norm(after[edges[:, 0]] - after[edges[:, 1]], axis=1)
            useful = old_lengths > 1e-8
            ratios = new_lengths[useful] / old_lengths[useful]
            extent = max(float(np.ptp(before, axis=0).max()), 1e-8)
            displacement = float(np.linalg.norm(after - before, axis=1).max()) / extent
            result = {'finite': True, 'new_degenerate_triangles': int(((aa < 1e-12) & valid).sum()),
                      'edge_ratio_min': float(ratios.min()) if len(ratios) else 1.,
                      'edge_ratio_max': float(ratios.max()) if len(ratios) else 1.,
                      'max_normal_rotation': float(np.degrees(np.arccos(np.clip(cosine, -1, 1))).max()) if len(cosine) else 0.,
                      'relative_displacement': displacement}
            ok = (result['new_degenerate_triangles'] == 0 and result['edge_ratio_min'] >= .5
                  and result['edge_ratio_max'] <= 1.5 and result['max_normal_rotation'] <= 60
                  and displacement <= .06)
            if ok and check_crossings:
                # Avoid numerical intersection churn when restoring or changing only height.
                if np.max(np.abs(after - before)) < 1e-6 * extent:
                    result['new_crossings'] = 0
                else:
                    if original_crossings is None:
                        original_crossings = crossings(before, triangles)
                        self.baseline[index] = (mesh, before, triangles, edges, original_crossings)
                    candidates = crossings(after, triangles) - original_crossings
                    contacts = {(i, j) for i, j in candidates
                                if touching(before[triangles[i]], before[triangles[j]], extent * .0002)}
                    result['baseline_contacts'] = len(contacts)
                    result['new_crossings'] = len(candidates - contacts)
                    ok = result['new_crossings'] == 0
            results[mesh.name] = result
            accepted &= ok
        if accepted:
            for name, (rotations, guard) in self.pose_guards.items():
                saved = self.pose(rotations)
                try:
                    ok, measurements = guard.check(height, check_crossings=False)
                    results.update({name + '/' + mesh: value for mesh, value in measurements.items()})
                    accepted &= ok
                finally:
                    self.restore_pose(saved)
        return accepted, results


def apply_guarded(values, apply_values, guard):
    """Back off all interacting changes together; always export a checked candidate."""
    attempts = []
    for strength in [1., .75, .5, .25, .125, .0625, .03125, .015625, 0.]:
        candidate = {}
        for key, value in values.items():
            default = 1. if key in {'height', 'head_size', 'shoulder_width', 'hip_width', 'arm_length', 'leg_length'} else 0.
            candidate[key] = value if key == 'height' else default + (value - default) * strength
        apply_values(candidate)
        bpy.context.view_layer.update()
        ok, measurements = guard.check(candidate.get('height', 1.))
        attempts.append({'strength': strength, 'accepted': bool(ok), 'meshes': measurements})
        if ok:
            # Shoulder/joint limits should not unnecessarily erase the requested
            # waist/hip and breast shape. Recover these together only if the whole
            # candidate still passes every pose and surface check.
            recovery = strength
            accepted_attempt = attempts[-1]
            for boost in [1., .75, .5, .25]:
                if boost <= strength or not any(values.get(k, 0) for k in ('feminine_curves', 'breast_size')):
                    break
                recovered = {**candidate, **{k: values[k] * boost for k in ('feminine_curves', 'breast_size') if k in values}}
                apply_values(recovered)
                bpy.context.view_layer.update()
                safe, measurements = guard.check(recovered.get('height', 1.))
                attempts.append({'strength': strength, 'curve_breast_strength': boost,
                                 'accepted': bool(safe), 'meshes': measurements})
                if safe:
                    candidate, recovery = recovered, boost
                    break
            if not attempts[-1]['accepted']:
                apply_values(candidate)
                bpy.context.view_layer.update()
                attempts.append(accepted_attempt)
            return candidate, {'enabled': True, 'strength': strength, 'attempts': attempts,
                               'curve_breast_strength': recovery,
                               'limits': {'edge_ratio': [.5, 1.5], 'max_normal_rotation': 60,
                                          'relative_displacement': .06, 'crossing_tolerance': .0002},
                               'scope': 'Geometry in reference pose, hip flexion and lowered arms. Crossings within each mesh in reference pose only; excludes existing crossings and contacts.'}
    raise RuntimeError('Não foi possível preservar a integridade da malha. A base precisa de revisão.')
