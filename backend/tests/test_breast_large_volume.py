import math

import pytest

from app.body_profile import BREAST_SIZE_MAX, NATURAL_LIMITS
from app.body_service import BodyError, current_capabilities, normalize


def capabilities(source_type='markers', slider_max=1.0):
    source = {
        'source_id': 'markers:breast_size' if source_type == 'markers' else 'existing:breast',
        'type': source_type,
        'control_hint': 'breast_size' if source_type != 'existing' else None,
        'driven': False,
        'slider_min': -.5 if source_type != 'existing' else 0.,
        'slider_max': slider_max,
        'targets': [],
    }
    return current_capabilities({
        'controls': {'breast_size': {'enabled': source_type != 'markers'}},
        'morph_sources': [source],
        'default_bindings': {},
        'breast_marker_info': {
            'height': 2., 'radius_min': .05, 'radius_max': .19, 'radius_default': .12,
            'bounds_min': [-1., 0., -.4], 'bounds_max': [1., 2., .4],
            'up': [0., 1., 0.], 'front': [0., 0., 1.], 'left': [1., 0., 0.],
            'origin': [0., 1., 0.], 'chest_min': 1.2, 'chest_max': 1.8,
        },
    })


def markers():
    return {'left': [.15, 1.5, .2], 'right': [-.15, 1.5, .2], 'radius': .12}


def test_assisted_breast_source_is_upgraded_and_accepts_large_values():
    caps = capabilities('markers', 1.)
    source = caps['morph_sources'][0]
    assert source['slider_max'] == BREAST_SIZE_MAX
    assert NATURAL_LIMITS['breast_size'][1] == BREAST_SIZE_MAX
    values, bindings = normalize(
        caps, {'breast_size': 25.}, {'breast_size': 'markers:breast_size'}, markers())
    assert values['breast_size'] == 25.
    assert bindings['breast_size'] == 'markers:breast_size'


def test_technical_ceiling_only_rejects_pathological_values():
    caps = capabilities('markers', 1.)
    with pytest.raises(BodyError, match='limite técnico'):
        normalize(caps, {'breast_size': BREAST_SIZE_MAX + 1},
                  {'breast_size': 'markers:breast_size'}, markers())
    with pytest.raises(BodyError, match='Valor inválido'):
        normalize(caps, {'breast_size': math.inf},
                  {'breast_size': 'markers:breast_size'}, markers())


def test_existing_shape_key_keeps_its_own_range():
    caps = capabilities('existing', .75)
    with pytest.raises(BodyError, match='intervalo da fonte'):
        normalize(caps, {'breast_size': 2.}, {'breast_size': 'existing:breast'})
