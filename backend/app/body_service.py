from __future__ import annotations
import asyncio,json,math,re,shutil,time,uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable,Callable
from .asset_service import ASSET_ID_RE
from .body_profile import NATURAL_LIMITS,BREAST_SIZE_MAX,natural_values
from .blender_service import _read_stream,probe_blender_version,validate_blender_path
from .preparation_service import PREPARATION_ID_RE,load_preparation_report,resolve_preparation_root

Publish=Callable[[dict],Awaitable[None]]; HEX=re.compile(r'^[0-9a-f]{32}$')
SPECS={
'feminine_curves':('Curvas femininas','morph',0.,1.,0.),
'height':('Altura','structural',.90,1.10,1.),'head_size':('Tamanho da cabeça','structural',.85,1.15,1.),
'shoulder_width':('Largura dos ombros','structural',.88,1.12,1.),'hip_width':('Largura dos quadris','structural',.88,1.12,1.),
'arm_length':('Comprimento dos braços','structural',.92,1.08,1.),'leg_length':('Comprimento das pernas','structural',.92,1.08,1.),
'arm_volume':('Volume dos braços','morph',-.4,.5,0.),'leg_volume':('Volume das pernas','morph',-.4,.5,0.),
'torso_volume':('Volume do tronco','morph',-.35,.45,0.),'breast_size':('Volume dos seios','morph_optional',-.5,BREAST_SIZE_MAX,0.)}
PRESETS={'regular':{k:v[4] for k,v in SPECS.items()},'magro':{'shoulder_width':.97,'hip_width':.97,'arm_volume':-.3,'leg_volume':-.28,'torso_volume':-.28},'musculoso':{'shoulder_width':1.04,'arm_volume':.34,'leg_volume':.26,'torso_volume':.2},'encorpado':{'shoulder_width':1.03,'hip_width':1.04,'arm_volume':.18,'leg_volume':.22,'torso_volume':.38}}
for p in PRESETS.values():
 p.update(natural_values(p))
 for k,v in SPECS.items(): p.setdefault(k,v[4])
class BodyError(ValueError):pass
@dataclass(frozen=True)
class BodyWorkspace:
 asset_id:str;preparation_id:str;body_id:str;root:Path;source:Path;baseline:Path;preview:Path;caps:Path;presets:Path
@dataclass(frozen=True)
class Revision:
 asset_id:str;preparation_id:str;body_id:str;revision_id:str;root:Path;baseline:Path;request:Path;blend:Path;preview:Path;report:Path;values:dict;bindings:dict;breast_markers:dict|None=None

def jwrite(p:Path,v): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def jread(p:Path):
 try:v=json.loads(p.read_text(encoding='utf-8'))
 except Exception as e: raise BodyError(f'JSON interno inválido: {p.name}') from e
 if not isinstance(v,dict):raise BodyError(f'JSON interno inválido: {p.name}')
 return v
def prepared(a,p):
 if not ASSET_ID_RE.fullmatch(a) or not PREPARATION_ID_RE.fullmatch(p):raise BodyError('Identificador inválido.')
 r=load_preparation_report(a,p)
 if not r or not r.get('ready_for_body_customization'):raise BodyError('A base ainda requer revisão da Etapa 3.')
 b=resolve_preparation_root(a,p)/'output'/'prepared.blend'
 if not b.is_file():raise BodyError('prepared.blend não encontrado.')
 return b
async def create_workspace(a,p):
 src=prepared(a,p);bid=uuid.uuid4().hex;root=resolve_preparation_root(a,p)/'customizations'/bid
 w=BodyWorkspace(a,p,bid,root,root/'source.blend',root/'baseline.blend',root/'baseline.glb',root/'capabilities.json',root/'presets.json')
 root.mkdir(parents=True);shutil.copy2(src,w.source);jwrite(w.presets,{'format_version':1,'presets':{}});return w
def root_for(a,p,b):
 if not HEX.fullmatch(b):raise BodyError('Identificador de personalização inválido.')
 r=resolve_preparation_root(a,p)/'customizations'/b
 if not r.is_dir():raise FileNotFoundError(b)
 return r
def caps_for(a,p,b):
 f=root_for(a,p,b)/'capabilities.json'
 if not f.is_file():raise FileNotFoundError(f.name)
 return current_capabilities(jread(f))
def current_capabilities(c):
 c['control_specs']={k:{'label':v[0],'kind':v[1],'min':NATURAL_LIMITS[k][0],'max':NATURAL_LIMITS[k][1],'default':v[4]} for k,v in SPECS.items()}
 for k in SPECS:c.setdefault('controls',{}).setdefault(k,{'enabled':False,'reason':'Prepare os controles novamente para inspecionar este ajuste.'})
 c['builtin_presets']=PRESETS
 c['natural_shape']={'enabled':True,'version':2,'breast_volume_unrestricted':True,'breast_technical_max':BREAST_SIZE_MAX}
 return c
def sources(c):return {x['source_id']:x for x in c.get('morph_sources',[]) if isinstance(x,dict) and x.get('source_id')}
def normalize_markers(c,markers,required=False):
 if markers is None and not required:return None
 info=c.get('breast_marker_info')
 if not info or not isinstance(markers,dict):raise BodyError('Posicione os dois marcadores dos seios na base original.')
 def number(v):
  if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):raise BodyError('Coordenadas dos marcadores inválidas.')
  return float(v)
 def point(raw,side,label='Marcador'):
  if not isinstance(raw,(list,tuple)) or len(raw)!=3:raise BodyError(f'{label} inválido.')
  p=[number(v) for v in raw]
  if any(v<info['bounds_min'][i]-info['height']*.005 or v>info['bounds_max'][i]+info['height']*.005 for i,v in enumerate(p)):raise BodyError(f'{label} fora dos limites do modelo.')
  elevation=sum(v*u for v,u in zip(p,info['up']))
  if not info['chest_min']<=elevation<=info['chest_max']:raise BodyError(f'{label} fora da região do peito.')
  offset=[v-o for v,o in zip(p,info['origin'])]
  if sum(v*f for v,f in zip(offset,info['front']))<=0:raise BodyError(f'{label} precisa ficar na frente do peito.')
  lateral=sum(v*l for v,l in zip(offset,info['left']))
  if lateral*(1 if side=='left' else -1)<=0:raise BodyError(f'{label} está no lado incorreto do personagem.')
  return p
 points={side:point(markers.get(side),side,'Marcador') for side in ('left','right')}
 radius=number(markers.get('radius'))
 if not info['radius_min']<=radius<=info['radius_max']:raise BodyError('Área de influência dos seios fora do limite.')
 distance=math.dist(points['left'],points['right'])
 if not info['height']*.02<=distance<=info['height']*.35:raise BodyError('Os marcadores precisam identificar dois seios separados na região do peito.')
 out={**points,'radius':radius}
 paint=markers.get('paint')
 if paint is not None:
  if not isinstance(paint,dict):raise BodyError('Pintura dos seios inválida.')
  brush=number(paint.get('brush_radius'))
  if not info['height']*.006<=brush<=info['height']*.055:raise BodyError('Tamanho do pincel fora do limite seguro.')
  clean={'brush_radius':brush}
  for side in ('left','right'):
   raw=paint.get(side)
   if not isinstance(raw,list) or not 3<=len(raw)<=512:raise BodyError('Pinte pelo menos três pontos em cada seio; máximo de 512 pontos por lado.')
   pts=[point(p,side,'Traço pintado') for p in raw]
   if max(math.dist(pts[0],p) for p in pts)<info['height']*.008:raise BodyError('A pintura precisa cobrir uma área, não apenas um ponto.')
   clean[side]=pts
  out['paint']=clean
 return out
def normalize(c,values,bindings,breast_markers=None):
 idx=sources(c);defaults=c.get('default_bindings',{});bindings={k:(bindings or {}).get(k,defaults.get(k)) for k,spec in SPECS.items() if spec[1]!='structural'};bindings={k:v for k,v in bindings.items() if v}
 if len(set(bindings.values()))!=len(bindings):raise BodyError('A mesma fonte de morph não pode controlar duas regiões.')
 for k,sid in bindings.items():
  s=idx.get(sid)
  if not s:raise BodyError(f'Fonte de morph inexistente para {k}.')
  if s.get('driven'):raise BodyError('Shape key com driver não pode ser sobrescrito diretamente.')
  if s.get('type') in ('generated','markers') and s.get('control_hint')!=k:raise BodyError('Morph assistido pertence a outra região.')
  if s.get('type')=='markers':normalize_markers(c,breast_markers,required=True)
 out={};controls=c.get('controls',{})
 for k,(label,kind,lo,hi,dft) in SPECS.items():
  try:v=float((values or {}).get(k,dft))
  except Exception as e:raise BodyError(f'Valor inválido para {label}.') from e
  if not math.isfinite(v):raise BodyError(f'Valor inválido para {label}.')
  if not lo<=v<=hi:raise BodyError(f'{label} fora do limite técnico [{lo}, {hi}].')
  if not (controls.get(k) or {}).get('enabled') and k not in bindings and abs(v-dft)>1e-8:raise BodyError(f'{label} indisponível nesta base.')
  if kind!='structural' and k not in bindings and abs(v-dft)>1e-8:raise BodyError(f'{label} sem fonte de morph selecionada.')
  if k in bindings and v<0 and float(idx[bindings[k]].get('slider_min',0))>=0:raise BodyError(f'{label} não aceita valor negativo.')
  if k in bindings and not float(idx[bindings[k]].get('slider_min',0))<=v<=float(idx[bindings[k]].get('slider_max',1)):raise BodyError(f'{label} fora do intervalo da fonte de morph.')
  out[k]=v
 return natural_values(out),bindings
def create_revision(a,p,b,values,bindings,breast_markers=None):
 r=root_for(a,p,b);c=caps_for(a,p,b);v,m=normalize(c,values,bindings,breast_markers);markers=normalize_markers(c,breast_markers);rid=uuid.uuid4().hex;rr=r/'revisions'/rid;rr.mkdir(parents=True)
 resolved={k:list(sources(c)[sid].get('targets',[])) for k,sid in m.items()};req=rr/'request.json';jwrite(req,{'values':v,'requested_values':{k:float((values or {}).get(k,s[4])) for k,s in SPECS.items()},'bindings':m,'resolved':resolved,'breast_markers':markers})
 return Revision(a,p,b,rid,rr,r/'baseline.blend',req,rr/'customized.blend',rr/'customized.glb',rr/'result.json',v,m,markers)
async def run(exe,args,publish,timeout=240):
 proc=await asyncio.create_subprocess_exec(str(exe),*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE);mark={};o=asyncio.create_task(_read_stream(proc.stdout,'stdout',publish,mark));e=asyncio.create_task(_read_stream(proc.stderr,'stderr',publish,mark))
 try:code=await asyncio.wait_for(proc.wait(),timeout)
 except TimeoutError:proc.kill();await proc.wait();raise RuntimeError('Blender excedeu o tempo limite.')
 await asyncio.gather(o,e,return_exceptions=True)
 if code:raise RuntimeError(f'Blender encerrou com código {code}.')
async def prepare_controls(blender,script,w,publish,timeout=240):
 try:
  exe=validate_blender_path(blender);await probe_blender_version(exe);await publish({'type':'progress','value':15,'message':'Inspecionando rig, shape keys e drivers...'})
  await run(exe,['--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script),'--','prepare',str(w.source),str(w.baseline),str(w.preview),str(w.caps)],publish,timeout)
  c=current_capabilities(jread(w.caps));jwrite(w.caps,c)
  await publish({'type':'success','message':'Controles corporais preparados.','result':{'asset_id':w.asset_id,'preparation_id':w.preparation_id,'customization_id':w.body_id,'preview_url':f'/api/assets/{w.asset_id}/preparations/{w.preparation_id}/customizations/{w.body_id}/preview.glb','capabilities':c}})
 except Exception as e:await publish({'type':'error','message':str(e),'code':'BODY_PREPARE_ERROR'})
async def apply_controls(blender,script,r,publish,timeout=240):
 try:
  exe=validate_blender_path(blender);await probe_blender_version(exe);await publish({'type':'progress','value':15,'message':'Ajustando o corpo e verificando a forma e as articulações...'})
  await run(exe,['--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script),'--','apply',str(r.baseline),str(r.request),str(r.blend),str(r.preview),str(r.report)],publish,timeout)
  application=jread(r.report)
  await publish({'type':'success','message':'Personalização aplicada no Blender.','result':{'asset_id':r.asset_id,'preparation_id':r.preparation_id,'customization_id':r.body_id,'revision_id':r.revision_id,'preview_url':f'/api/assets/{r.asset_id}/preparations/{r.preparation_id}/customizations/{r.body_id}/revisions/{r.revision_id}/preview.glb','blend_url':f'/api/assets/{r.asset_id}/preparations/{r.preparation_id}/customizations/{r.body_id}/revisions/{r.revision_id}/customized.blend','values':application.get('values',r.values),'bindings':r.bindings,'breast_markers':r.breast_markers,'application':application}})
 except Exception as e:await publish({'type':'error','message':str(e),'code':'BODY_APPLY_ERROR'})
def revision_root(a,p,b,rid):
 if not HEX.fullmatch(rid):raise BodyError('Revisão inválida.')
 r=root_for(a,p,b)/'revisions'/rid
 if not r.is_dir():raise FileNotFoundError(rid)
 return r
def list_presets(a,p,b):
 d=jread(root_for(a,p,b)/'presets.json');return {'format_version':1,'builtin':PRESETS,'custom':d.get('presets',{})}
def save_preset(a,p,b,name,values,bindings,breast_markers=None):
 name=name.strip()
 if not name or len(name)>64:raise BodyError('Nome de preset inválido.')
 c=caps_for(a,p,b);v,m=normalize(c,values,bindings,breast_markers);markers=normalize_markers(c,breast_markers);f=root_for(a,p,b)/'presets.json';d=jread(f);d.setdefault('presets',{})[name]={'name':name,'saved_at':int(time.time()),'values':v,'bindings':m,'breast_markers':markers};jwrite(f,d);return d['presets'][name]
