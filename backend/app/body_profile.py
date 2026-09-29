"""Editing bounds relative to the supplied body, not population norms.

Most controls stay conservative. Breast volume is intentionally different: users may
request very large stylized proportions. BREAST_SIZE_MAX is only a technical guard
against pathological floating-point values, not an anatomical recommendation.
"""

BREAST_SIZE_MAX = 100.0

NATURAL_LIMITS = {
    'height': (.90, 1.10),
    'head_size': (.94, 1.06),
    'shoulder_width': (.94, 1.06),
    'hip_width': (.94, 1.06),
    'arm_length': (.96, 1.04),
    'leg_length': (.96, 1.04),
    'arm_volume': (-.22, .28),
    'leg_volume': (-.22, .28),
    'torso_volume': (-.20, .25),
    'feminine_curves': (0., 1.),
    'breast_size': (-.5, BREAST_SIZE_MAX),
}


def natural_values(values):
    return {key: max(NATURAL_LIMITS[key][0], min(NATURAL_LIMITS[key][1], value))
            for key, value in values.items()}
