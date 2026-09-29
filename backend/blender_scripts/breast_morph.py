"""Localized, reversible breast shape keys in the unchanged mesh topology."""
import math
import re

import bpy

from mathutils import Vector
from mathutils.bvhtree import BVHTree


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
    """Inflate around a center inside the torso instead of extruding forward.

    ``x/y/z`` are measured from the surface marker. The virtual inflation
    center sits behind the marker, so enlargement behaves like scaling a soft
    volume around that center: flanks widen, the upper/lower poles round out,
    and the apex advances only as one component of the same radial motion.
    """
    distance2 = (x / radius) ** 2 + (y / radius) ** 2 + (z / (radius * .95)) ** 2
    if distance2 >= 1.:
        return Vector(), 0.

    # Keep most of the central breast moving as one rounded volume, then use a
    # C1 edge taper. A strong radial taper from the apex created a pinched ring.
    normalized = math.sqrt(max(0., distance2))
    if normalized <= .58:
        envelope = 1.
    else:
        envelope = 1. - _smoothstep01((normalized - .58) / .42)

    # Vertices near/behind the chest attachment must stay anchored. The old
    # forward-projection field started at this same plane, but its displacement
    # direction was front-heavy. Here the plane only controls influence.
    attachment = _smoothstep01((z / radius + .55) / .45)
    influence = envelope * attachment
    if influence <= 1e-8:
        return Vector(), 0.

    # The virtual center is 0.38 radii inside the chest and just 0.03 radii
    # above the marker. That tiny vertical offset gives the lower pole a little
    # more fullness without turning the operation back into a directional push.
    radial = (lateral * x + up * (y - radius * .03)
              + front * max(0., z + radius * .38))
    delta = radial * (.40 * influence)
    return delta, influence


def marker_morphs(meshes, markers, info):
    """Same world-space inflation field for body and clothing."""
    centers = [from_gltf(markers[s]) for s in ('left', 'right')]
    radius = markers['radius']
    front, up, lateral = (from_gltf(info[k]) for k in ('front', 'up', 'left'))
    # Require points on the baseline surface; a valid HTTP request alone is not
    # enough to approve a detached marker or silently export an unchanged body.
    trees = []; surfaces = {}
    for mesh in meshes:
        points, polygons = world_geometry(mesh)
        if len(points) != len(mesh.data.vertices):
            raise RuntimeError('Marcadores requerem uma base sem modificadores que alterem a topologia.')
        surfaces[mesh.name] = points
        if polygons:
            trees.append(BVHTree.FromPolygons(points, polygons))
    for point in centers:
        distances = [hit[3] for tree in trees if (hit := tree.find_nearest(point))[0] is not None]
        if not distances or min(distances) > info['height'] * .008:
            raise RuntimeError('Marcador fora da superfície. Marque novamente na base original.')
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
                candidates.append((influence, delta))
                if delta.length > 1e-8:
                    affected[index] += 1
            if not candidates:
                deltas.append(Vector())
                continue
            # Markers may overlap near the sternum. Each delta already contains
            # its own falloff, so average only for overlap; do not multiply that
            # falloff a second time or the breast edge collapses toward the apex.
            total = sum(weight for weight, _ in candidates)
            deltas.append(sum((delta * weight for weight, delta in candidates), Vector()) /
                          max(total, 1e-8))
        target = make_key(mesh, deltas)
        if target:
            targets.append(target)
    if not all(affected) or not targets:
        raise RuntimeError('Os dois marcadores precisam alcançar vértices. Aumente a área de influência.')
    return targets, affected
