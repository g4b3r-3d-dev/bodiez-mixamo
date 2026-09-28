from __future__ import annotations
import asyncio,json,uuid
from pathlib import Path
from fastapi import HTTPException,Request
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from .main import app,_assert_http_origin
from .config import load_settings,assets_root
from .blender_service import validate_blender_path
from .task_store import store
from .body_service import BodyError,create_workspace,prepare_controls,create_revision,apply_controls,caps_for,root_for,revision_root,list_presets,save_preset

SCRIPT=Path(__file__).resolve().parents[1]/'blender_scripts'/'body_customize.py'
class ApplyBody(BaseModel):values:dict[str,float]=Field(default_factory=dict);bindings:dict[str,str]=Field(default_factory=dict)
class SavePreset(BaseModel):name:str=Field(min_length=1,max_length=64);values:dict[str,float]=Field(default_factory=dict);bindings:dict[str,str]=Field(default_factory=dict)
def reg(method,path,fn,**kw):
 if not any(getattr(r,'path',None)==path and method in (getattr(r,'methods',None) or set()) for r in app.routes):app.add_api_route(path,fn,methods=[method],**kw)
def body_error(e):
 if isinstance(e,FileNotFoundError):return HTTPException(404,'Recurso corporal não encontrado.')
 return HTTPException(422,str(e))
def preparation_name(report_path:Path):
 asset=report_path.parent.parents[1]
 try:
  manifest=json.loads((asset/'manifest.json').read_text())
  return manifest.get('original_name') or asset.name
 except (OSError,ValueError,AttributeError):return asset.name
async def ready(request:Request):
 _assert_http_origin(request);rows=[]
 for f in assets_root().glob('*/preparations/*/preparation.json'):
  try:r=json.loads(f.read_text())
  except Exception:continue
  blend=f.parent/'output'/'prepared.blend'
  if isinstance(r,dict) and r.get('ready_for_body_customization') and blend.is_file():rows.append({'asset_id':f.parent.parents[1].name,'preparation_id':f.parent.name,'mode':r.get('mode'),'name':preparation_name(f),'updated_at':int(max(f.stat().st_mtime,blend.stat().st_mtime))})
 rows.sort(key=lambda x:x['updated_at'],reverse=True);return {'items':rows[:50]}
async def create(request:Request,asset_id:str,preparation_id:str):
 _assert_http_origin(request);blender=load_settings().get('blender_path')
 if not blender:raise HTTPException(409,'Configure o Blender primeiro.')
 try:validate_blender_path(blender);w=await create_workspace(asset_id,preparation_id)
 except Exception as e:raise body_error(e) from e
 tid=uuid.uuid4().hex;await store.create(tid)
 async def pub(x):await store.publish(tid,x)
 asyncio.create_task(prepare_controls(blender,SCRIPT,w,pub));return {'asset_id':asset_id,'preparation_id':preparation_id,'customization_id':w.body_id,'task_id':tid}
async def info(request:Request,asset_id:str,preparation_id:str,customization_id:str):
 _assert_http_origin(request)
 try:return {'asset_id':asset_id,'preparation_id':preparation_id,'customization_id':customization_id,'capabilities':caps_for(asset_id,preparation_id,customization_id)}
 except Exception as e:raise body_error(e) from e
async def apply(request:Request,asset_id:str,preparation_id:str,customization_id:str,body:ApplyBody):
 _assert_http_origin(request);blender=load_settings().get('blender_path')
 if not blender:raise HTTPException(409,'Configure o Blender primeiro.')
 try:validate_blender_path(blender);r=create_revision(asset_id,preparation_id,customization_id,body.values,body.bindings)
 except Exception as e:raise body_error(e) from e
 tid=uuid.uuid4().hex;await store.create(tid)
 async def pub(x):await store.publish(tid,x)
 asyncio.create_task(apply_controls(blender,SCRIPT,r,pub));return {'asset_id':asset_id,'preparation_id':preparation_id,'customization_id':customization_id,'revision_id':r.revision_id,'task_id':tid}
def send(path,name):
 if not path.is_file():raise HTTPException(404,'Arquivo ainda não disponível.')
 return FileResponse(path,media_type='model/gltf-binary' if path.suffix=='.glb' else 'application/octet-stream',filename=name,headers={'Cache-Control':'no-store'})
async def baseline_preview(request:Request,asset_id:str,preparation_id:str,customization_id:str):
 _assert_http_origin(request)
 try:return send(root_for(asset_id,preparation_id,customization_id)/'baseline.glb','customizable.glb')
 except Exception as e:raise body_error(e) from e
async def rev_preview(request:Request,asset_id:str,preparation_id:str,customization_id:str,revision_id:str):
 _assert_http_origin(request)
 try:return send(revision_root(asset_id,preparation_id,customization_id,revision_id)/'customized.glb','customized.glb')
 except Exception as e:raise body_error(e) from e
async def rev_blend(request:Request,asset_id:str,preparation_id:str,customization_id:str,revision_id:str):
 _assert_http_origin(request)
 try:return send(revision_root(asset_id,preparation_id,customization_id,revision_id)/'customized.blend','customized.blend')
 except Exception as e:raise body_error(e) from e
async def presets(request:Request,asset_id:str,preparation_id:str,customization_id:str):
 _assert_http_origin(request)
 try:return list_presets(asset_id,preparation_id,customization_id)
 except Exception as e:raise body_error(e) from e
async def put_preset(request:Request,asset_id:str,preparation_id:str,customization_id:str,body:SavePreset):
 _assert_http_origin(request)
 try:return save_preset(asset_id,preparation_id,customization_id,body.name,body.values,body.bindings)
 except Exception as e:raise body_error(e) from e
reg('GET','/api/stage4/ready-preparations',ready);reg('POST','/api/assets/{asset_id}/preparations/{preparation_id}/customizations',create,status_code=202);reg('GET','/api/assets/{asset_id}/preparations/{preparation_id}/customizations/{customization_id}',info);reg('POST','/api/assets/{asset_id}/preparations/{preparation_id}/customizations/{customization_id}/apply',apply,status_code=202);reg('GET','/api/assets/{asset_id}/preparations/{preparation_id}/customizations/{customization_id}/preview.glb',baseline_preview);reg('GET','/api/assets/{asset_id}/preparations/{preparation_id}/customizations/{customization_id}/revisions/{revision_id}/preview.glb',rev_preview);reg('GET','/api/assets/{asset_id}/preparations/{preparation_id}/customizations/{customization_id}/revisions/{revision_id}/customized.blend',rev_blend);reg('GET','/api/assets/{asset_id}/preparations/{preparation_id}/customizations/{customization_id}/presets',presets);reg('PUT','/api/assets/{asset_id}/preparations/{preparation_id}/customizations/{customization_id}/presets',put_preset)
