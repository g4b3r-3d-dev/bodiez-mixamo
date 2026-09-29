"""Exercise natural body safeguards through HTTP, Blender and exported GLB geometry."""
import argparse
import asyncio
import json
from pathlib import Path

import httpx
from validate_stage4_api import wait_task
from validate_breast_api import node, ROOT


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--markers', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    out = args.output; out.mkdir(parents=True, exist_ok=True)
    prepared = json.loads(args.prepared.read_text())
    markers = json.loads(args.markers.read_text())
    endpoint = prepared['path'] + '/' + prepared['created']['customization_id']
    async with httpx.AsyncClient(base_url=args.base_url, timeout=90) as client:
        response = await client.get(endpoint); response.raise_for_status()
        caps = response.json()['capabilities']
        assert caps['natural_shape']['enabled']
        specs = caps['control_specs']
        defaults = {k: s['default'] for k, s in specs.items()}
        bindings = {**caps['default_bindings'], 'breast_size': 'markers:breast_size'}
        response = await client.get(prepared['result']['preview_url']); response.raise_for_status()
        (out/'before.glb').write_bytes(response.content)
        variants = {
            'maximos': {k: s['max'] for k, s in specs.items()},
            'minimos': {k: s['min'] for k, s in specs.items()},
            'curvas-com-seios': {**defaults, 'feminine_curves': 1, 'breast_size': 1},
            'cintura-marcada': {**defaults, 'feminine_curves': 1, 'torso_volume': -.2, 'hip_width': 1.06, 'leg_volume': .28, 'breast_size': 1},
            'contrastes': {**defaults, 'head_size': 1.06, 'shoulder_width': .94, 'hip_width': 1.06, 'arm_length': .96, 'leg_length': 1.04, 'arm_volume': -.22, 'leg_volume': .28, 'torso_volume': .25, 'breast_size': -.5, 'feminine_curves': 1},
            **caps['builtin_presets'],
            'preset-antigo': {**defaults, 'head_size': 1.15, 'shoulder_width': 1.12, 'hip_width': 1.12, 'arm_length': 1.08, 'leg_length': 1.08, 'arm_volume': .5, 'leg_volume': .5, 'torso_volume': .45, 'feminine_curves': 1, 'breast_size': 1},
            'restaurado': defaults,
        }
        report = {'model': prepared['source'], 'variants': {}}
        for name, values in variants.items():
            payload = {'values': values, 'bindings': bindings, 'breast_markers': markers}
            response = await client.post(endpoint+'/apply', json=payload); response.raise_for_status()
            result = await wait_task(response.json()['task_id'], args.base_url)
            application = result['application']; guard = application['natural_shape']
            assert result['values'] == application['values']
            assert guard['attempts'][-1]['accepted']
            for key, value in result['values'].items():
                assert specs[key]['min'] <= value <= specs[key]['max']
            for key, change in guard['adjustments'].items():
                assert change['requested'] == values[key] and change['applied'] == result['values'][key]
            for extension, url in [('glb', result['preview_url']), ('blend', result['blend_url'])]:
                response = await client.get(url); response.raise_for_status()
                (out/f'{name}.{extension}').write_bytes(response.content)
            geometry = await node(ROOT/'frontend/scripts/measure-body.mjs', out/'before.glb', out/f'{name}.glb')
            if name in ('regular', 'restaurado'):
                assert geometry['max_displacement'] < 1e-5
            else:
                assert geometry['changed_vertices'] > 0, (name, guard)
            report['variants'][name] = {'requested': values, 'applied': result['values'], 'guard': guard, 'geometry': geometry}
            (out/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
            print('NATURAL_BODY_VALIDATED', name, guard['strength'], flush=True)
        # Reapply an accepted result: the UI and saved presets must not drift.
        values = report['variants']['maximos']['applied']
        payload = {'values': values, 'bindings': bindings, 'breast_markers': markers}
        response = await client.put(endpoint+'/presets', json={**payload, 'name': 'Proporções naturais'}); response.raise_for_status()
        assert response.json()['values'] == values
        response = await client.get(endpoint+'/presets'); response.raise_for_status()
        assert response.json()['custom']['Proporções naturais']['values'] == values
        response = await client.post(endpoint+'/apply', json=payload); response.raise_for_status()
        result = await wait_task(response.json()['task_id'], args.base_url)
        assert result['values'] == values
        report['effective_values_roundtrip'] = True
        (out/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
