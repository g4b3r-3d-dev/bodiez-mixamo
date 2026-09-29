"""Validate curves on a prepared female model through the running local API."""
import asyncio
import argparse
import hashlib
import json
from pathlib import Path

import httpx

from validate_stage4_api import wait_task


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, help='Import and prepare this local model first')
    parser.add_argument('--asset-id')
    parser.add_argument('--output', type=Path, default=Path('.local-data/stage4-curves'))
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', timeout=60) as client:
        digest = None
        if args.model:
            digest = hashlib.sha256(args.model.read_bytes()).hexdigest()
            with args.model.open('rb') as model:
                response = await client.post('/api/assets/import', files={'model': (args.model.name, model, 'model/gltf-binary')})
            response.raise_for_status()
            imported = await wait_task(response.json()['task_id'])
            (output / 'inspection.json').write_text(json.dumps(imported, ensure_ascii=False, indent=2))
            args.asset_id = imported['asset_id']
            response = await client.post(f'/api/assets/{args.asset_id}/prepare/existing')
            response.raise_for_status()
            preparation = await wait_task(response.json()['task_id'])
            (output / 'preparation.json').write_text(json.dumps(preparation, ensure_ascii=False, indent=2))
            print('MODEL_PREPARED', args.asset_id, flush=True)
        response = await client.get('/api/stage4/ready-preparations')
        response.raise_for_status()
        source = next(x for x in response.json()['items'] if (x['asset_id'] == args.asset_id if args.asset_id else x.get('name') == 'femele-decimate-retextured-rename-parts.glb'))
        path = f"/api/assets/{source['asset_id']}/preparations/{source['preparation_id']}/customizations"
        response = await client.post(path)
        response.raise_for_status()
        prepared = await wait_task(response.json()['task_id'])
        caps = prepared['capabilities']
        (output / 'capabilities.json').write_text(json.dumps(caps, ensure_ascii=False, indent=2))
        assert caps['controls']['feminine_curves']['enabled']
        path += '/' + prepared['customization_id']

        async def download(url, name):
            response = await client.get(url)
            response.raise_for_status()
            (output / name).write_bytes(response.content)

        await download(prepared['preview_url'], 'before.glb')
        report = {'source': source, 'original_sha256': digest, 'customization_id': prepared['customization_id'], 'variants': {}}
        for name, intensity in [('suaves', .35), ('marcadas', .65), ('maximas', 1.), ('restaurado', 0.)]:
            response = await client.post(path + '/apply', json={'values': {'feminine_curves': intensity}})
            response.raise_for_status()
            applied = await wait_task(response.json()['task_id'])
            await download(applied['preview_url'], name + '.glb')
            await download(applied['blend_url'], name + '.blend')
            process = await asyncio.create_subprocess_exec(
                'node', 'frontend/scripts/measure-body.mjs', str(output / 'before.glb'),
                str(output / (name + '.glb')), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await process.communicate()
            assert process.returncode == 0, stderr.decode()
            geometry = json.loads(stdout)
            if intensity == 0:
                assert geometry['max_displacement'] < 1e-5
            else:
                assert geometry['changed_vertices'] > 0
            report['variants'][name] = {'geometry': geometry, 'result': applied}
            print('CURVES_VALIDATED', name, geometry['max_displacement'], flush=True)
        small = report['variants']['suaves']['geometry']['max_displacement']
        large = report['variants']['maximas']['geometry']['max_displacement']
        assert abs(small / large - .35) < .001, 'Intensity must be progressive'
        response = await client.put(path + '/presets', json={'name': 'Curvas marcadas', 'values': {'feminine_curves': .65}})
        response.raise_for_status()
        response = await client.get(path + '/presets')
        response.raise_for_status()
        assert response.json()['custom']['Curvas marcadas']['values']['feminine_curves'] == .65
        if args.model:
            assert hashlib.sha256(args.model.read_bytes()).hexdigest() == digest, 'Original model was modified'
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
