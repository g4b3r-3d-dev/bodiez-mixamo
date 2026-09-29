"""A localized waist/hip/glute shape key, measured in the rig's body frame."""
from mathutils import Vector

CONTROL = 'feminine_curves'
KEY = 'Bodiez_Auto_' + CONTROL
VERSION = 2
REQUIRED = ('hips', 'head', 'left_upper_arm', 'right_upper_arm',
            'left_thigh', 'right_thigh')
REGION = ('hips', 'spine', 'spine1', 'spine2', 'left_thigh', 'right_thigh')


def falloff(distance):
    """Compact smooth support, with no deformation outside the region."""
    return max(0., 1. - distance * distance) ** 2 if abs(distance) < 1 else 0.


def curve_morphs(arm, meshes, matches):
    if not all(name in matches for name in REQUIRED):
        return []

    def head(name):
        return arm.matrix_world @ arm.data.bones[matches[name]].head_local

    origin = head('hips')
    axis = head('head') - origin
    span = axis.length
    if span < 1e-6:
        return []
    up = axis.normalized()
    lateral = head('left_upper_arm') - head('right_upper_arm')
    lateral -= up * lateral.dot(up)
    if lateral.length < 1e-6:
        return []
    lateral.normalize()
    front = lateral.cross(up).normalized()
    targets = []
    for mesh in meshes:
        groups = {g.index for name in REGION if name in matches
                  if (g := mesh.vertex_groups.get(matches[name])) is not None}
        if not groups:
            continue
        basis = mesh.data.shape_keys.reference_key.data if mesh.data.shape_keys else mesh.data.vertices
        inverse = mesh.matrix_world.inverted().to_3x3()
        deltas = []
        for vertex, base in zip(mesh.data.vertices, basis):
            weight = min(1., sum(w.weight for w in vertex.groups if w.group in groups))
            offset = mesh.matrix_world @ base.co - origin
            x, depth, z = offset.dot(lateral), offset.dot(front), offset.dot(up) / span
            waist = falloff((z - .27) / .30)
            hip = falloff((z + .10) / .48)
            # Body weights protect hands/arms even when resting beside the hips.
            # Rear-only expansion leaves the abdomen out of the glute adjustment.
            rear = max(0., -depth)
            # Moderate the maximum and extend the lower transition into the
            # upper thighs: a short, strong bulge looked detached in profile.
            delta = (lateral * x * (.14 * hip - .12 * waist)
                     + front * (-depth * .06 * waist - rear * .20 * hip)) * weight
            deltas.append(inverse @ delta)
        if not any(d.length > 1e-8 for d in deltas):
            continue
        if not mesh.data.shape_keys:
            mesh.shape_key_add(name='Basis', from_mix=False)
        key = mesh.data.shape_keys.key_blocks.get(KEY) or mesh.shape_key_add(name=KEY, from_mix=False)
        key.value = 0; key.slider_min = 0; key.slider_max = 1
        for base, target, delta in zip(mesh.data.shape_keys.reference_key.data, key.data, deltas):
            target.co = base.co + delta
        mesh['bodiez_version_' + KEY] = VERSION
        targets.append({'mesh': mesh.name, 'key': key.name})
    return targets
