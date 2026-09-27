from __future__ import annotations
import asyncio,json,math,re,shutil,time,uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable,Callable
from fastapi import UploadFile
from .asset_service import MODEL_EXTENSIONS,RESOURCE_EXTENSIONS,MAX_MODEL_BYTES,MAX_RESOURCE_BYTES,MAX_TOTAL_RESOURCE_BYTES,AssetValidationError,_gltf_external_uris,_safe_filename,_validate_model_signature,_validate_resource_signature,_write_upload
from .blender_service import _read_stream,probe_blender_version,validate_blender_path
from .config import assets_root

Publish=Callable[[dict],Awaitable[None]];HEX=re.compile(r'^[0-9a-f]{32}$');STRUCTURAL_KEYS=('height','head_size','shoulder_width','hip_width','arm_length','leg_length')
class AnimationError(ValueError):pass
@dataclass(frozen=True)
class Stage5Session:
 session_id:str;root:Path;source:Path;baseline:Path;preview:Path;capabilities:Path;metadata:Path;poses:Path
@dataclass(frozen=True)
class PoseRevision:
 session_id:str;revision_id:str;root:Path;baseline:Path;request:Path;blend:Path;preview:Path;report:Path
@dataclass(frozen=True)
class AnimationJob:
 session_id:str;animation_id:str;root:Path;baseline:Path;working_model:Path;output_blend:Path;preview:Path;report:Path;root_motion:str

def jwrite(p:Path,v):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');t.replace(p)
def jread(p:Path):
 try:v=json.loads(p.read_text(encoding='utf-8'))
 except Exception as e:raise AnimationError(f'JSON interno inválido: {p.name}') from e
 if not isinstance(v,dict):raise AnimationError(f'JSON interno inválido: {p.name}')
 return v
def valid_id(v,label):
 if not HEX.fullmatch(v):raise AnimationError(f'{label} inválido.')
 return v
def stage5_root():
 r=assets_root()/'stage5';r.mkdir(parents=True,exist_ok=True);return r
def safe_dict(p):
 try:
  v=json.loads(p.read_text(encoding='utf-8'));return v if isinstance(v,dict) else {}
 except Exception:return {}

def list_sources():
 rows=[];root=assets_root()
 if not root.exists():return rows
 for ad in root.iterdir():
  if not ad.is_dir() or not HEX.fullmatch(ad.name):continue
  pp=ad/'preparations'
  if not pp.is_dir():continue
  for pd in pp.iterdir():
   if not pd.is_dir() or not HEX.fullmatch(pd.name):continue
   rep=safe_dict(pd/'preparation.json');blend=pd/'output'/'prepared.blend'
   if rep.get('ready_for_body_customization') and blend.is_file():rows.append({'kind':'preparation','asset_id':ad.name,'preparation_id':pd.name,'label':f'Base preparada · {ad.name[:8]}','proportions_changed':False,'updated_at':int(blend.stat().st_mtime)})
   cp=pd/'customizations'
   if not cp.is_dir():continue
   for cd in cp.iterdir():
    if not cd.is_dir() or not HEX.fullmatch(cd.name):continue
    rp=cd/'revisions'
    if not rp.is_dir():continue
    for rd in rp.iterdir():
     if not rd.is_dir() or not HEX.fullmatch(rd.name):continue
     b=rd/'customized.blend'
     if not b.is_file():continue
     q=safe_dict(rd/'request.json');vals=q.get('values') if isinstance(q.get('values'),dict) else {};changed=any(abs(float(vals.get(k,1))-1)>1e-6 for k in STRUCTURAL_KEYS)
     rows.append({'kind':'customization_revision','asset_id':ad.name,'preparation_id':pd.name,'customization_id':cd.name,'revision_id':rd.name,'label':f'Corpo personalizado · {ad.name[:8]} · {rd.name[:6]}','proportions_changed':changed,'updated_at':int(b.stat().st_mtime)})
 rows.sort(key=lambda x:x['updated_at'],reverse=True);return rows[:100]

def resolve_source(spec):
 kind=str(spec.get('kind',''));a=valid_id(str(spec.get('asset_id','')),'Asset');p=valid_id(str(spec.get('preparation_id','')),'Preparação');prep=assets_root()/a/'preparations'/p
 if kind=='preparation':
  path=prep/'output'/'prepared.blend';report=safe_dict(prep/'preparation.json')
  if not report.get('ready_for_body_customization') or not path.is_file():raise AnimationError('A preparação selecionada não está aprovada para uso.')
  return path,{'kind':kind,'asset_id':a,'preparation_id':p,'proportions_changed':False}
 if kind=='customization_revision':
  c=valid_id(str(spec.get('customization_id','')),'Personalização');r=valid_id(str(spec.get('revision_id','')),'Revisão');rd=prep/'customizations'/c/'revisions'/r;path=rd/'customized.blend'
  if not path.is_file():raise AnimationError('Revisão corporal não encontrada.')
  q=safe_dict(rd/'request.json');vals=q.get('values') if isinstance(q.get('values'),dict) else {};changed=any(abs(float(vals.get(k,1))-1)>1e-6 for k in STRUCTURAL_KEYS)
  return path,{'kind':kind,'asset_id':a,'preparation_id':p,'customization_id':c,'revision_id':r,'proportions_changed':changed,'body_values':vals}
 raise AnimationError('Tipo de fonte inválido.')

async def create_session(spec):
 src,meta=resolve_source(spec);sid=uuid.uuid4().hex;root=stage5_root()/sid;root.mkdir(parents=True);w=Stage5Session(sid,root,root/'source.blend',root/'baseline.blend',root/'baseline.glb',root/'capabilities.json',root/'session.json',root/'poses.json');shutil.copy2(src,w.source);jwrite(w.metadata,{'format_version':1,'session_id':sid,'created_at':int(time.time()),'source':meta,'status':'queued'});jwrite(w.poses,{'format_version':1,'poses':{}});return w
def session_for(sid):
 valid_id(sid,'Sessão');root=stage5_root()/sid
 if not root.is_dir():raise FileNotFoundError(sid)
 return Stage5Session(sid,root,root/'source.blend',root/'baseline.blend',root/'baseline.glb',root/'capabilities.json',root/'session.json',root/'poses.json')
def capabilities_for(sid):
 w=session_for(sid)
 if not w.capabilities.is_file():raise FileNotFoundError(w.capabilities.name)
 c=jread(w.capabilities);c['source']=jread(w.metadata).get('source',{});return c
def normalize_rotations(sid,rotations):
 c=capabilities_for(sid);names={str(x.get('name')) for x in c.get('bones',[]) if isinstance(x,dict)}
 if not isinstance(rotations,dict) or len(rotations)>160:raise AnimationError('Pose inválida ou grande demais.')
 out={}
 for bone,axes in rotations.items():
  if bone not in names:raise AnimationError(f'Osso inexistente na base atual: {bone}')
  if not isinstance(axes,dict):raise AnimationError(f'Rotação inválida para {bone}.')
  clean={}
  for axis in ('x','y','z'):
   try:v=float(axes.get(axis,0))
   except Exception as e:raise AnimationError(f'Rotação inválida para {bone}.') from e
   if not math.isfinite(v) or not -180<=v<=180:raise AnimationError('Rotações devem ficar entre -180° e 180°.')
   clean[axis]=round(v,5)
  if any(abs(v)>1e-8 for v in clean.values()):out[bone]=clean
 return out
def create_pose_revision(sid,rotations):
 w=session_for(sid);clean=normalize_rotations(sid,rotations);rid=uuid.uuid4().hex;root=w.root/'pose_revisions'/rid;root.mkdir(parents=True);req=root/'pose.json';jwrite(req,{'format_version':1,'rotations_degrees':clean});return PoseRevision(sid,rid,root,w.baseline,req,root/'posed.blend',root/'posed.glb',root/'result.json')
def save_pose(sid,name,rotations):
 w=session_for(sid);name=name.strip()
 if not name or len(name)>64:raise AnimationError('Nome de pose inválido.')
 clean=normalize_rotations(sid,rotations);c=capabilities_for(sid);d=jread(w.poses);poses=d.setdefault('poses',{});poses[name]={'name':name,'saved_at':int(time.time()),'target_signature':c.get('target_signature'),'rotations_degrees':clean};jwrite(w.poses,d);return poses[name]
def list_poses(sid):return jread(session_for(sid).poses)

async def create_animation_job(sid,model:UploadFile,resources:list[UploadFile],root_motion):
 w=session_for(sid)
 if not w.baseline.is_file():raise AnimationError('Sessão ainda não foi preparada no Blender.')
 if root_motion not in {'preserve','in_place'}:raise AnimationError('Modo de movimento da raiz inválido.')
 name=_safe_filename(model.filename);ext=Path(name).suffix.lower()
 if ext not in MODEL_EXTENSIONS:raise AnimationError('Animações devem ser FBX, GLB ou GLTF.')
 aid=uuid.uuid4().hex;root=w.root/'animations'/aid;orig=root/'original';work=root/'working';om=orig/name;wm=work/name
 try:
  await _write_upload(model,om,MAX_MODEL_BYTES);_validate_model_signature(om);seen=set();total=0
  for res in resources:
   rn=_safe_filename(res.filename);sx=Path(rn).suffix.lower()
   if sx not in RESOURCE_EXTENSIONS:raise AnimationError(f'Dependência não permitida: {rn}')
   if rn==name or rn in seen:raise AnimationError(f'Arquivo duplicado: {rn}')
   seen.add(rn);size=await _write_upload(res,orig/rn,MAX_RESOURCE_BYTES);_validate_resource_signature(orig/rn);total+=size
   if total>MAX_TOTAL_RESOURCE_BYTES:raise AnimationError('Dependências da animação excedem 1 GB.')
  missing=[x for x in _gltf_external_uris(om) if x not in seen]
  if missing:raise AnimationError('GLTF referencia dependências não selecionadas: '+', '.join(missing))
  work.mkdir(parents=True,exist_ok=True);shutil.copy2(om,wm)
  for rn in seen:shutil.copy2(orig/rn,work/rn)
  jwrite(root/'manifest.json',{'format_version':1,'animation_id':aid,'original_name':name,'root_motion':root_motion,'original_preserved':True,'created_at':int(time.time())})
  return AnimationJob(sid,aid,root,w.baseline,wm,root/'retargeted.blend',root/'retargeted.glb',root/'report.json',root_motion)
 except (AssetValidationError,AnimationError):shutil.rmtree(root,ignore_errors=True);raise
 finally:
  await model.close()
  for res in resources:await res.close()
def animation_root(sid,aid):
 w=session_for(sid);valid_id(aid,'Animação');root=w.root/'animations'/aid
 if not root.is_dir():raise FileNotFoundError(aid)
 return root
async def run_blender(exe,args,publish,timeout=300):
 proc=await asyncio.create_subprocess_exec(str(exe),*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE);result={};o=asyncio.create_task(_read_stream(proc.stdout,'stdout',publish,result));e=asyncio.create_task(_read_stream(proc.stderr,'stderr',publish,result))
 try:code=await asyncio.wait_for(proc.wait(),timeout)
 except TimeoutError:proc.kill();await proc.wait();await asyncio.gather(o,e,return_exceptions=True);raise RuntimeError('O Blender excedeu o limite de tempo desta operação.')
 await asyncio.gather(o,e,return_exceptions=True)
 if code:raise RuntimeError(f'O Blender encerrou com código {code}.')
async def prepare_session(blender,script,w,publish):
 try:
  exe=validate_blender_path(blender);await probe_blender_version(exe);await publish({'type':'progress','value':10,'message':'Inspecionando esqueleto e pose de referência...'});await run_blender(exe,['--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script),'--','prepare',str(w.source),str(w.baseline),str(w.preview),str(w.capabilities)],publish);c=jread(w.capabilities);m=jread(w.metadata);c['source']=m.get('source',{});jwrite(w.capabilities,c);m['status']='ready';jwrite(w.metadata,m);await publish({'type':'success','message':'Workspace de poses e animações preparado.','result':{'session_id':w.session_id,'capabilities':c,'preview_url':f'/api/stage5/sessions/{w.session_id}/preview.glb'}})
 except Exception as e:await publish({'type':'error','message':str(e),'code':'STAGE5_PREPARE_ERROR'})
async def apply_pose(blender,script,r,publish):
 try:
  exe=validate_blender_path(blender);await probe_blender_version(exe);await publish({'type':'progress','value':20,'message':'Aplicando pose sobre a referência atual...'});await run_blender(exe,['--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script),'--','pose',str(r.baseline),str(r.request),str(r.blend),str(r.preview),str(r.report)],publish);await publish({'type':'success','message':'Pose aplicada no Blender.','result':{'session_id':r.session_id,'revision_id':r.revision_id,'preview_url':f'/api/stage5/sessions/{r.session_id}/poses/{r.revision_id}/preview.glb','blend_url':f'/api/stage5/sessions/{r.session_id}/poses/{r.revision_id}/posed.blend','application':jread(r.report)}})
 except Exception as e:await publish({'type':'error','message':str(e),'code':'POSE_APPLY_ERROR'})
async def process_animation(blender,script,j,publish):
 try:
  exe=validate_blender_path(blender);await probe_blender_version(exe);await publish({'type':'progress','value':10,'message':'Inspecionando esqueleto da animação...'});await run_blender(exe,['--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script),'--','animation',str(j.baseline),str(j.working_model),str(j.output_blend),str(j.preview),str(j.report),j.root_motion],publish,420);rep=jread(j.report);result={'session_id':j.session_id,'animation_id':j.animation_id,'report':rep,'preview_url':f'/api/stage5/sessions/{j.session_id}/animations/{j.animation_id}/preview.glb' if j.preview.is_file() else None,'blend_url':f'/api/stage5/sessions/{j.session_id}/animations/{j.animation_id}/retargeted.blend' if j.output_blend.is_file() else None};msg='Animação retargeteada e validada.' if rep.get('status')=='ready' else 'Animação inspecionada; intervenção necessária.';await publish({'type':'success','message':msg,'result':result})
 except Exception as e:
  rep=safe_dict(j.report) if j.report.is_file() else None;await publish({'type':'error','message':str(e),'code':'ANIMATION_PROCESS_ERROR','result':{'report':rep} if rep else None})
