"""Validate breast marker workflow through HTTP, WebSocket, Blender and Three.js.

Requires a prepared female fixture. See docs/stage4-breast/README.md.
"""
import argparse
import asyncio
import json
from pathlib import Path

import httpx

from validate_stage4_api import wait_task

ROOT=Path(__file__).resolve().parents[1]

async def node(*args):
 proc=await asyncio.create_subprocess_exec('node',*[str(a) for a in args],stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
 out,err=await proc.communicate()
 if proc.returncode:raise RuntimeError(err.decode())
 return json.loads(out)

async def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--base-url',default='http://127.0.0.1:8000')
 parser.add_argument('--asset-id',required=True)
 parser.add_argument('--output',type=Path,default=Path('.local-data/stage4-breast'))
 parser.add_argument('--reuse-prepared',action='store_true')
 parser.add_argument('--full-range',action='store_true',help='Include intermediate values, maximum and curves combination')
 args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
 async with httpx.AsyncClient(base_url=args.base_url,timeout=90) as client:
  async def request(method,path,**kwargs):
   r=await client.request(method,path,**kwargs);r.raise_for_status();return r.json()
  if args.reuse_prepared:
   prepared=json.loads((out/'prepared.json').read_text())
  else:
   items=(await request('GET','/api/stage4/ready-preparations'))['items']
   source=next(i for i in items if i['asset_id']==args.asset_id)
   path=f"/api/assets/{source['asset_id']}/preparations/{source['preparation_id']}/customizations"
   created=await request('POST',path)
   result=await wait_task(created['task_id'],args.base_url)
   prepared={'source':source,'path':path,'created':created,'result':result}
   (out/'prepared.json').write_text(json.dumps(prepared,indent=2))
  result=prepared['result'];caps=result['capabilities']
  assert caps['controls']['breast_size']['requires_markers'], 'Fixture must have no breast bones'
  r=await client.get(result['preview_url']);r.raise_for_status();(out/'before.glb').write_bytes(r.content)
  markers=await node(ROOT/'frontend/scripts/pick-breast-markers.mjs',out/'before.glb',out/'prepared.json')
  (out/'markers.json').write_text(json.dumps(markers,indent=2))
  endpoint=prepared['path']+'/'+prepared['created']['customization_id']
  bindings={**caps['default_bindings'],'breast_size':'markers:breast_size'}
  defaults={k:s['default'] for k,s in caps['control_specs'].items()}
  payload={'values':{**defaults,'breast_size':.75},'bindings':bindings,'breast_markers':markers}
  # HTTP validation must reject missing, misplaced and swapped markers.
  invalids=[{**payload,'breast_markers':None},
            {**payload,'breast_markers':{**markers,'left':markers['right']}},
            {**payload,'breast_markers':{**markers,'radius':100}}]
  for invalid in invalids:
   r=await client.post(endpoint+'/apply',json=invalid);assert r.status_code==422,r.text
  saved=await request('PUT',endpoint+'/presets',json={**payload,'name':'Seios por marcadores'})
  assert saved['breast_markers']==markers
  presets=await request('GET',endpoint+'/presets')
  assert presets['custom']['Seios por marcadores']['breast_markers']==markers
  reports={'markers':markers,'source':prepared['source'],'variants':{},'invalid_requests_rejected':len(invalids),'preset_roundtrip':True}
  variants={'aumentar':{'breast_size':.75},'reduzir':{'breast_size':-.5},'restaurar':{'breast_size':0},'combinado':{'breast_size':.75,'height':1.05,'torso_volume':.15}}
  if args.full_range:
   variants.update({'reducao-suave':{'breast_size':-.25},'aumento-suave':{'breast_size':.35},'aumento-moderado':{'breast_size':.65},'maximo':{'breast_size':1},'curvas':{'breast_size':.65,'feminine_curves':.65}})
  for name,values in variants.items():
   task=await request('POST',endpoint+'/apply',json={**payload,'values':{**defaults,**values}})
   applied=await wait_task(task['task_id'],args.base_url)
   r=await client.get(applied['preview_url']);r.raise_for_status();(out/(name+'.glb')).write_bytes(r.content)
   r=await client.get(applied['blend_url']);r.raise_for_status();(out/(name+'.blend')).write_bytes(r.content)
   geometry=await node(ROOT/'frontend/scripts/measure-body.mjs',out/'before.glb',out/(name+'.glb'))
   if name=='restaurar':assert geometry['max_displacement']<1e-5,geometry
   else:assert geometry['changed_vertices']>0 and geometry['max_displacement']>1e-4,geometry
   assert all(applied['application']['breast_markers']['affected_vertices_per_side'])
   locality=await node(ROOT/'frontend/scripts/measure-breast.mjs',out/'before.glb',out/(name+'.glb'),out/'prepared.json',out/'markers.json',values['breast_size']) if name not in ('combinado','curvas') else None
   reports['variants'][name]={'values':values,'applied_values':applied['values'],'geometry':geometry,'locality':locality,'application':applied['application']}
   print('BREAST_API_VALIDATED',name,geometry['changed_vertices'],geometry['max_displacement'],flush=True)
  (out/'report.json').write_text(json.dumps(reports,indent=2,ensure_ascii=False))
  if args.full_range:
   order=['restaurar','aumento-suave','aumento-moderado','aumentar','maximo']
   effective=[reports['variants'][name]['applied_values']['breast_size'] for name in order]
   displacement=[reports['variants'][name]['geometry']['max_displacement'] for name in order]
   assert all(a<=b+1e-7 for a,b in zip(effective,effective[1:])),effective
   assert all(a<=b+1e-6 for a,b in zip(displacement,displacement[1:])),displacement

if __name__=='__main__':asyncio.run(main())
