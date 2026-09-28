import json

import pytest

from app import live_update_service as s


@pytest.fixture()
def configured(tmp_path, monkeypatch):
    (tmp_path / 'baseline.blend').write_bytes(b'blend')
    monkeypatch.setattr(s, 'root_for', lambda a, p, c: tmp_path)
    monkeypatch.setattr(
        s,
        'caps_for',
        lambda a, p, c: {
            'morph_sources': [
                {
                    'source_id': 'auto:arm_volume',
                    'targets': [{'mesh': 'Body', 'key': 'Bodiez_Auto_arm_volume'}],
                }
            ]
        },
    )
    monkeypatch.setattr(
        s,
        'normalize',
        lambda caps, values, bindings: (
            {'height': float(values.get('height', 1.0)), 'arm_volume': float(values.get('arm_volume', 0.0))},
            dict(bindings),
        ),
    )
    monkeypatch.setattr(
        s,
        'sources',
        lambda caps: {
            'auto:arm_volume': {
                'source_id': 'auto:arm_volume',
                'targets': [{'mesh': 'Body', 'key': 'Bodiez_Auto_arm_volume'}],
            }
        },
    )
    return tmp_path


def test_live_update_writes_resolved_request(configured):
    update = s.create_live_update(
        'a' * 32,
        'b' * 32,
        'c' * 32,
        'd' * 32,
        1,
        {'height': 1.04, 'arm_volume': 0.2},
        {'arm_volume': 'auto:arm_volume'},
    )
    request = json.loads(update.request.read_text())
    assert request['generation'] == 1
    assert request['values']['height'] == 1.04
    assert request['resolved']['arm_volume'][0]['key'] == 'Bodiez_Auto_arm_volume'
    assert s.is_latest(update) is True


def test_older_generation_is_marked_stale_without_touching_existing_work(configured):
    first = s.create_live_update('a' * 32, 'b' * 32, 'c' * 32, 'd' * 32, 4, {}, {})
    marker = first.root / 'running.marker'
    marker.write_text('keep')
    duplicate = s.create_live_update('a' * 32, 'b' * 32, 'c' * 32, 'd' * 32, 4, {}, {})
    older = s.create_live_update('a' * 32, 'b' * 32, 'c' * 32, 'd' * 32, 3, {}, {})
    assert first.stale_on_arrival is False
    assert duplicate.stale_on_arrival is True
    assert older.stale_on_arrival is True
    assert marker.read_text() == 'keep'
    assert s.latest_generation('a' * 32, 'b' * 32, 'c' * 32, 'd' * 32) == 4


def test_invalid_client_token_is_rejected(configured):
    with pytest.raises(s.LiveUpdateError):
        s.create_live_update('a' * 32, 'b' * 32, 'c' * 32, '../bad', 1, {}, {})


@pytest.mark.asyncio
async def test_stale_update_does_not_launch_blender(configured, monkeypatch):
    s.create_live_update('a' * 32, 'b' * 32, 'c' * 32, 'd' * 32, 8, {}, {})
    stale = s.create_live_update('a' * 32, 'b' * 32, 'c' * 32, 'd' * 32, 7, {}, {})
    called = False

    async def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError('Blender não deveria ser iniciado para geração antiga.')

    monkeypatch.setattr(s, 'run', forbidden)
    events = []

    async def publish(event):
        events.append(event)

    await s.process_live_update('/not/used', configured / 'not-used.py', stale, publish)
    assert called is False
    assert events[-1]['type'] == 'success'
    assert events[-1]['result']['stale'] is True
