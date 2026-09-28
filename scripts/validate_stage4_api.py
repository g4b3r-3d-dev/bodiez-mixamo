"""Exercise the running app's Stage 4 and save GLBs for reproducible photo checks.

Run with backend/.venv/bin/python scripts/validate_stage4_api.py
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import websockets


async def wait_task(task_id):
    async with websockets.connect('ws://127.0.0.1:8000/ws/tasks/'+task_id, origin='http://127.0.0.1:5173') as socket:
        await socket.send('ready')
        async with asyncio.timeout(260):
            async for message in socket:
                event=json.loads(message)
                if event['type']=='error':raise RuntimeError(event['message'])
                if event['type']=='success':return event['result']
        raise RuntimeError('Task ended without a result')


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',default='riged-decimate.fbx')
    parser.add_argument('--asset-id')
    parser.add_argument('--all-controls',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('.local-data/stage4-visual/api'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=60) as client:
        response=await client.get('/api/stage4/ready-preparations');response.raise_for_status()
        items=response.json()['items']
        source=next(x for x in items if (x['asset_id']==args.asset_id if args.asset_id else x.get('name')==args.name))
        path=f"/api/assets/{source['asset_id']}/preparations/{source['preparation_id']}/customizations"
        response=await client.post(path);response.raise_for_status();created=response.json()
        prepared=await wait_task(created['task_id']);caps=prepared['capabilities']
        async def download(url,name):
            response=await client.get(url);response.raise_for_status()
            assert response.content[:4]==b'glTF'
            (args.output/name).write_bytes(response.content)
            return hashlib.sha256(response.content).hexdigest()
        await download(prepared['preview_url'],'before.glb')
        reports={'source':source,'customization_id':created['customization_id'],'variants':{}}
        variants={name:caps['builtin_presets'][name] for name in ['encorpado','musculoso','regular']}
        variants['estrutura']={k:(spec['max'] if spec['kind']=='structural' else spec['default']) for k,spec in caps['control_specs'].items()}
        if args.all_controls:
            defaults={k:s['default'] for k,s in caps['control_specs'].items()}
            for key,spec in caps['control_specs'].items():
                if caps['controls'][key]['enabled']:variants['control-'+key]={**defaults,key:spec['max']}
        for name,values in variants.items():
            response=await client.post(path+'/'+created['customization_id']+'/apply',json={'values':values,'bindings':caps['default_bindings']});response.raise_for_status()
            applied=await wait_task(response.json()['task_id'])
            digest=await download(applied['preview_url'],name+'.glb')
            measurement=await asyncio.create_subprocess_exec('node',str(Path(__file__).resolve().parents[1]/'frontend/scripts/measure-body.mjs'),str(args.output/'before.glb'),str(args.output/(name+'.glb')),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            stdout,stderr=await measurement.communicate()
            if measurement.returncode:raise RuntimeError(stderr.decode())
            geometry=json.loads(stdout)
            if name=='regular':assert geometry['max_displacement']<1e-5,geometry
            else:assert geometry['changed_vertices']>0 and geometry['max_displacement']>1e-5,geometry
            reports['variants'][name]={'values':values,'sha256':digest,'geometry':geometry,'result':applied}
            print('API_VALIDATED',name,flush=True)
        (args.output/'report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())
