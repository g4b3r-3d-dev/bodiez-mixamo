import pytest

from app.body_service import BodyError, normalize_markers


def caps():
    return {
        'breast_marker_info': {
            'height': 2.0,
            'radius_min': .05,
            'radius_max': .19,
            'radius_default': .12,
            'paint_radius_min': .012,
            'paint_radius_max': .11,
            'paint_radius_default': .036,
            'bounds_min': [-1, 0, -.4],
            'bounds_max': [1, 2, .4],
            'up': [0, 1, 0],
            'front': [0, 0, 1],
            'left': [1, 0, 0],
            'origin': [0, 1, 0],
            'chest_min': 1.2,
            'chest_max': 1.8,
        }
    }


def payload():
    return {
        'left': [.18, 1.5, .2],
        'right': [-.18, 1.5, .2],
        'radius': .14,
        'paint': {
            'brush_radius': .04,
            'left': [[.12,1.45,.2],[.18,1.5,.22],[.23,1.56,.2],[.16,1.6,.19]],
            'right': [[-.12,1.45,.2],[-.18,1.5,.22],[-.23,1.56,.2],[-.16,1.6,.19]],
        },
    }


def test_painted_mask_is_preserved_and_sanitized():
    out = normalize_markers(caps(), payload(), required=True)
    assert out['paint']['brush_radius'] == .04
    assert len(out['paint']['left']) == 4
    assert out['left'] == [.18, 1.5, .2]


def test_paint_requires_area_on_both_sides():
    data = payload(); data['paint']['left'] = [[.18,1.5,.2],[.181,1.5,.2],[.182,1.5,.2]]
    with pytest.raises(BodyError, match='cobrir uma área'):
        normalize_markers(caps(), data, required=True)


def test_paint_rejects_wrong_side_and_large_brush():
    data = payload(); data['paint']['left'][0] = [-.12,1.45,.2]
    with pytest.raises(BodyError, match='lado incorreto'):
        normalize_markers(caps(), data, required=True)
    data = payload(); data['paint']['brush_radius'] = .5
    with pytest.raises(BodyError, match='pincel'):
        normalize_markers(caps(), data, required=True)


def test_old_marker_payload_stays_compatible():
    data = payload(); data.pop('paint')
    out = normalize_markers(caps(), data, required=True)
    assert 'paint' not in out
