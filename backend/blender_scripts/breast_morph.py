"""Localized, reversible breast shape keys in the unchanged mesh topology."""
import math
import re

import bpy

from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


MARKER_SOURCE = 'markers:breast_size'
KEY = 'Bodiez_Auto_breast_size'


def gltf(v):
    return [v.x, v.z, -v.y]


def from_gltf(v):
    return Vector((v[0], -v[2], v[1]))


def world_geometry(mesh):
    # Markers refer to the visible baseline, including existing active shape keys.
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data = evaluated.to_mesh()
    try:
        return ([evaluated.matrix_world @ v.co for v in data.vertices],
                [list(p.vertices) for p in data.polygons])
    finally:
        evaluated.to_mesh_clear()


def breast_bones(arm, meshes):
    """Only explicit paired names with actual skin weights, never generic Chest."""
    aliases = {
        'left': {'breastl', 'lbreast', 'leftbreast', 'bustl', 'bustleft', 'leftbust'},
        'right': {'breastr', 'rbreast', 'rightbreast', 'bustr', 'bustright', 'rightbust'},
    }
    found = {}
    for bone in arm.data.bones:
        name = re.sub('[^a-z0-9]', '', bone.name.split(':')[-1].lower())
        name = re.sub(r'^(def|org|mixamorig)', '', name)
        for side, names in aliases.items():
            if name not in names:
                continue
            if any((g := m.vertex_groups.get(bone.name)) is not None and
                   any(any(w.group == g.index and w.weight > .01 for w in v.groups)
                       for v in m.data.vertices) for m in meshes):
                found[side] = bone.name
    return found if len(found) == 2 else {}


def marker_info(arm, meshes, matches):
    def bone_position(name):
        return arm.matrix_world @ arm.data.bones[matches[name]].head_local
    up = Vector((0, 0, 1)); lateral = Vector((1, 0, 0))
    if all(n in matches for n in ('head', 'hips', 'left_upper_arm', 'right_upper_arm')):
        up = (bone_position('head') - bone_position('hips')).normalized()
        lateral = bone_position('left_upper_arm') - bone_position('right_upper_arm')
        lateral = (lateral - up * lateral.dot(up)).normalized()
    front = lateral.cross(up).normalized()
    points = [p for m in meshes for p in world_geometry(m)[0]]
    height = max(p.dot(up) for p in points) - min(p.dot(up) for p in points)
    if height < 1e-6:
        raise RuntimeError('Malha sem dimensão suficiente para marcar o corpo.')
    center = sum(points, Vector()) / len(points)
    origin = bone_position('hips') if 'hips' in matches else center
    low = min(p.dot(up) for p in points) + height * .5
    high = min(p.dot(up) for p in points) + height * .86
    if 'head' in matches and 'hips' in matches:
        span = (bone_position('head') - origin).dot(up)
        low, high = origin.dot(up) + span * .25, origin.dot(up) + span * .94
    gp = [gltf(p) for p in points]
    return {'coordinate_space': 'baseline_gltf_world', 'height': height,
            'radius_min': height * .025, 'radius_max': height * .095,
            'radius_default': height * .075,
            'paint_radius_min': height * .006, 'paint_radius_max': height * .055,
            'paint_radius_default': height * .018,
            'bounds_min': [min(p[i] for p in gp) for i in range(3)],
            'bounds_max': [max(p[i] for p in gp) for i in range(3)],
            'up': gltf(up), 'front': gltf(front), 'left': gltf(lateral),
            'origin': gltf(origin), 'chest_min': low, 'chest_max': high}


def make_key(mesh, displacements):
    if not any(d.length > 1e-8 for d in displacements):
        return None
    if not mesh.data.shape_keys:
        mesh.shape_key_add(name='Basis', from_mix=False)
    key = mesh.data.shape_keys.key_blocks.get(KEY) or mesh.shape_key_add(name=KEY, from_mix=False)
    key.value = 0; key.slider_min = -.5; key.slider_max = 1
    inverse = mesh.matrix_world.inverted().to_3x3()
    for base, target, delta in zip(mesh.data.shape_keys.reference_key.data, key.data, displacements):
        target.co = base.co + inverse @ delta
    return {'mesh': mesh.name, 'key': key.name}


def bone_morphs(arm, meshes, bones):
    targets = []
    for mesh in meshes:
        groups = [(mesh.vertex_groups.get(name), arm.matrix_world @ arm.data.bones[name].head_local)
                  for name in bones.values()]
        deltas = []
        for vertex in mesh.data.vertices:
            weights = {w.group: w.weight for w in vertex.groups}
            point = mesh.matrix_world @ vertex.co
            delta = sum(((point - origin) * (.55 * weights.get(group.index, 0))
                         for group, origin in groups if group is not None), Vector())
            deltas.append(delta)
        target = make_key(mesh, deltas)
        if target:
            targets.append(target)
    return targets


def _smoothstep01(value):
    value = max(0., min(1., value))
    return value * value * (3. - 2. * value)


def _balloon_delta(x, y, z, radius, lateral, up, front):
    """Inflate around a center inside the torso instead of extruding forward."""
    distance2 = (x / radius) ** 2 + (y / radius) ** 2 + (z / (radius * .95)) ** 2
    if distance2 >= 1.:
        return Vector(), 0.
    normalized = math.sqrt(max(0., distance2))
    if normalized <= .58:
        envelope = 1.
    else:
        envelope = 1. - _smoothstep01((normalized - .58) / .42)
    attachment = _smoothstep01((z / radius + .55) / .45)
    influence = envelope * attachment
    if influence <= 1e-8:
        return Vector(), 0.
    radial = (lateral * x + up * (y - radius * .03)
              + front * max(0., z + radius * .38))
    delta = radial * (.40 * influence)
    return delta, influence


def _paint_data(markers):
    paint = markers.get('paint') if isinstance(markers, dict) else None
    if not isinstance(paint, dict):
        return None
    radius = float(paint.get('brush_radius', 0))
    if radius <= 0:
        return None
    samples = {side: [from_gltf(p) for p in paint.get(side, [])]
               for side in ('left', 'right')}
    if not all(samples.values()):
        return None
    trees = {}
    for side, points in samples.items():
        tree = KDTree(len(points))
        for index, point in enumerate(points):
            tree.insert(point, index)
        tree.balance(); trees[side] = tree
    return {'radius': radius, 'samples': samples, 'trees': trees}


def _paint_weight(point, paint, side):
    if not paint:
        return 1.
    hit = paint['trees'][side].find(point)
    if not hit:
        return 0.
    distance = hit[2]
    if distance >= paint['radius']:
        return 0.
    return 1. - _smoothstep01(distance / paint['radius'])


def marker_morphs(meshes, markers, info):
    """World-space balloon field, optionally clipped by painted surface masks."""
    sides = ('left', 'right')
    centers = [from_gltf(markers[s]) for s in sides]
    radius = markers['radius']
    front, up, lateral = (from_gltf(info[k]) for k in ('front', 'up', 'left'))
    paint = _paint_data(markers)
    surface_trees = []; surfaces = {}
    for mesh in meshes:
        points, polygons = world_geometry(mesh)
        if len(points) != len(mesh.data.vertices):
            raise RuntimeError('Marcadores requerem uma base sem modificadores que alterem a topologia.')
        surfaces[mesh.name] = points
        if polygons:
            surface_trees.append(BVHTree.FromPolygons(points, polygons))
    validation_points = list(centers)
    if paint:
        validation_points.extend(p for side in sides for p in paint['samples'][side])
    for point in validation_points:
        distances = [hit[3] for tree in surface_trees if (hit := tree.find_nearest(point))[0] is not None]
        if not distances or min(distances) > info['height'] * .01:
            raise RuntimeError('A pintura contém pontos fora da superfície. Pinte novamente na base original.')
    targets = []; affected = [0, 0]
    for mesh in meshes:
        deltas = []
        for point in surfaces[mesh.name]:
            candidates = []
            for index, center in enumerate(centers):
                offset = point - center
                x, y, z = offset.dot(lateral), offset.dot(up), offset.dot(front)
                delta, influence = _balloon_delta(x, y, z, radius, lateral, up, front)
                if influence <= 0:
                    continue
                mask = _paint_weight(point, paint, sides[index])
                if mask <= 0:
                    continue
                delta *= mask; influence *= mask
                candidates.append((influence, delta))
                if delta.length > 1e-8:
                    affected[index] += 1
            if not candidates:
                deltas.append(Vector())
                continue
            total = sum(weight for weight, _ in candidates)
            deltas.append(sum((delta * weight for weight, delta in candidates), Vector()) /
                          max(total, 1e-8))
        target = make_key(mesh, deltas)
        if target:
            targets.append(target)
    if not all(affected) or not targets:
        message = ('A área pintada não alcançou vértices suficientes. Pinte uma região maior em cada seio.'
                   if paint else 'Os dois marcadores precisam alcançar vértices. Aumente a área de influência.')
        raise RuntimeError(message)
    return targets, affected
