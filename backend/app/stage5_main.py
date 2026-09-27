from __future__ import annotations
import asyncio,json,uuid
from pathlib import Path
from fastapi import File,Form,HTTPException,Request,UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from .stage4_main import app,_assert_http_origin
from .animation_service import animation_root,apply_pose,capabilities_for,create_animation_job,create_pose_revision,create_session,list_poses,list_sources,process_animation,prepare_session,save_pose,session_for
from .blender_service import validate_blender_path
from .config import load_settings
from .task_store import store
SCRIPT=Path(__file__).resolve().parents[1]/'blender_scripts'/'pose_animation.py'
class SourceRequest(BaseModel):
 kind:str;asset_id:str;preparation_id:str;customization_id:str|None=None;revision_id:str|None=None
class PoseRequest(BaseModel):rotations:dict[str,dict[str,float]]=Field(default_factory=dict)
class SavedPoseRequest(PoseRequest):name:str=Field(min_length=1,max_length=64)
def reg(method,path,fn,**kw):
 if not any(getattr(r,'path',None)==path and method in (getattr(r,'methods',None) or set()) for r in app.routes):app.add_api_route(path,fn,methods=[method],**kw)
def api_error(e):
 if isinstance(e,FileNotFoundError):return HTTPException(404,'Recurso da Etapa 5 não encontrado.')
 return HTTPException(422,str(e))
def blender_path():
 p=load_settings().get('blender_path')
 if not p:raise HTTPException(409,'Configure o Blender antes de usar poses e animações.')
 validate_blender_path(p);return p
async def sources(request:Request):_assert_http_origin(request);return {'items':list_sources()}
async def create_stage5_session(request:Request,body:SourceRequest):
 _assert_http_origin(request);blender=blender_path()
 try:w=await create_session(body.model_dump(exclude_none=True))
 except Exception as e:raise api_error(e) from e
 tid=uuid.uuid4().hex;await store.create(tid)
 async def pub(x):await store.publish(tid,x)
 asyncio.create_task(prepare_session(blender,SCRIPT,w,pub));return {'session_id':w.session_id,'task_id':tid}
async def session_info(request:Request,session_id:str):
 _assert_http_origin(request)
 try:return {'session_id':session_id,'capabilities':capabilities_for(session_id),'poses':list_poses(session_id)}
 except Exception as e:raise api_error(e) from e
async def session_preview(request:Request,session_id:str):
 _assert_http_origin(request)
 try:p=session_for(session_id).preview
 except Exception as e:raise api_error(e) from e
 if not p.is_file():raise HTTPException(404,'Preview da sessão ainda não disponível.')
 return FileResponse(p,media_type='model/gltf-binary',filename='stage5-reference.glb',headers={'Cache-Control':'no-store'})
async def apply_pose_route(request:Request,session_id:str,body:PoseRequest):
 _assert_http_origin(request);blender=blender_path()
 try:r=create_pose_revision(session_id,body.rotations)
 except Exception as e:raise api_error(e) from e
 tid=uuid.uuid4().hex;await store.create(tid)
 async def pub(x):await store.publish(tid,x)
 asyncio.create_task(apply_pose(blender,SCRIPT,r,pub));return {'session_id':session_id,'revision_id':r.revision_id,'task_id':tid}
async def poses_route(request:Request,session_id:str):
 _assert_http_origin(request)
 try:return list_poses(session_id)
 except Exception as e:raise api_error(e) from e
async def save_pose_route(request:Request,session_id:str,body:SavedPoseRequest):
 _assert_http_origin(request)
 try:return save_pose(session_id,body.name,body.rotations)
 except Exception as e:raise api_error(e) from e
def send(path,name,media='application/octet-stream'):
 if not path.is_file():raise HTTPException(404,'Arquivo ainda não disponível.')
 return FileResponse(path,media_type=media,filename=name,headers={'Cache-Control':'no-store'})
async def pose_preview(request:Request,session_id:str,revision_id:str):
 _assert_http_origin(request)
 try:
  root=session_for(session_id).root/'pose_revisions'/revision_id
  if not root.is_dir():raise FileNotFoundError(revision_id)
  return send(root/'posed.glb','posed.glb','model/gltf-binary')
 except HTTPException:raise
 except Exception as e:raise api_error(e) from e
async def pose_blend(request:Request,session_id:str,revision_id:str):
 _assert_http_origin(request)
 try:
  root=session_for(session_id).root/'pose_revisions'/revision_id
  if not root.is_dir():raise FileNotFoundError(revision_id)
  return send(root/'posed.blend','posed.blend')
 except HTTPException:raise
 except Exception as e:raise api_error(e) from e
async def import_animation(request:Request,session_id:str,model:UploadFile=File(...),resources:list[UploadFile]=File(default=[]),root_motion:str=Form(default='preserve')):
 _assert_http_origin(request);blender=blender_path()
 try:j=await create_animation_job(session_id,model,resources,root_motion)
 except Exception as e:raise api_error(e) from e
 tid=uuid.uuid4().hex;await store.create(tid)
 async def pub(x):await store.publish(tid,x)
 asyncio.create_task(process_animation(blender,SCRIPT,j,pub));return {'session_id':session_id,'animation_id':j.animation_id,'task_id':tid}
async def animation_report(request:Request,session_id:str,animation_id:str):
 _assert_http_origin(request)
 try:
  p=animation_root(session_id,animation_id)/'report.json'
  if not p.is_file():raise FileNotFoundError(p.name)
  return json.loads(p.read_text(encoding='utf-8'))
 except Exception as e:raise api_error(e) from e
async def animation_preview(request:Request,session_id:str,animation_id:str):
 _assert_http_origin(request)
 try:return send(animation_root(session_id,animation_id)/'retargeted.glb','retargeted.glb','model/gltf-binary')
 except HTTPException:raise
 except Exception as e:raise api_error(e) from e
async def animation_blend(request:Request,session_id:str,animation_id:str):
 _assert_http_origin(request)
 try:return send(animation_root(session_id,animation_id)/'retargeted.blend','retargeted.blend')
 except HTTPException:raise
 except Exception as e:raise api_error(e) from e
reg('GET','/api/stage5/sources',sources);reg('POST','/api/stage5/sessions',create_stage5_session,status_code=202);reg('GET','/api/stage5/sessions/{session_id}',session_info);reg('GET','/api/stage5/sessions/{session_id}/preview.glb',session_preview);reg('POST','/api/stage5/sessions/{session_id}/pose',apply_pose_route,status_code=202);reg('GET','/api/stage5/sessions/{session_id}/poses',poses_route);reg('PUT','/api/stage5/sessions/{session_id}/poses',save_pose_route);reg('GET','/api/stage5/sessions/{session_id}/poses/{revision_id}/preview.glb',pose_preview);reg('GET','/api/stage5/sessions/{session_id}/poses/{revision_id}/posed.blend',pose_blend);reg('POST','/api/stage5/sessions/{session_id}/animations',import_animation,status_code=202);reg('GET','/api/stage5/sessions/{session_id}/animations/{animation_id}',animation_report);reg('GET','/api/stage5/sessions/{session_id}/animations/{animation_id}/preview.glb',animation_preview);reg('GET','/api/stage5/sessions/{session_id}/animations/{animation_id}/retargeted.blend',animation_blend)
