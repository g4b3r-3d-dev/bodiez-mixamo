from __future__ import annotations
import json,time
from pathlib import Path
from .body_service import BodyError,SPECS,caps_for,jread,jwrite,normalize,normalize_markers,revision_root,root_for
from .preparation_service import resolve_preparation_root

STATE_FILE='body_state.json'

def _same(a,b):
 return json.dumps(a,sort_keys=True,separators=(',',':'))==json.dumps(b,sort_keys=True,separators=(',',':'))

def _urls(a,p,b,revision_id=None):
 base=f'/api/assets/{a}/preparations/{p}/customizations/{b}'
 if revision_id:
  return (f'{base}/revisions/{revision_id}/preview.glb',f'{base}/revisions/{revision_id}/customized.blend')
 return (f'{base}/preview.glb',None)

def save_current_state(a,p,b,values,bindings,breast_markers=None,revision_id=None):
 root_for(a,p,b);caps=caps_for(a,p,b)
 values,bindings=normalize(caps,values,bindings,breast_markers)
 markers=normalize_markers(caps,breast_markers)
 if revision_id:
  rr=revision_root(a,p,b,revision_id);request=rr/'request.json';report=rr/'result.json';blend=rr/'customized.blend';preview=rr/'customized.glb'
  if not all(x.is_file() for x in (request,report,blend,preview)):
   raise BodyError('A revisão atual ainda não terminou; aguarde a aplicação antes de salvar o estado.')
  req=jread(request);result=jread(report)
  applied_values,applied_bindings=normalize(caps,result.get('values',req.get('values',{})),req.get('bindings',{}),req.get('breast_markers'))
  applied_markers=normalize_markers(caps,req.get('breast_markers'))
  if not (_same(values,applied_values) and _same(bindings,applied_bindings) and _same(markers,applied_markers)):
   raise BodyError('O estado atual não corresponde à revisão aplicada. Aplique as alterações antes de salvar.')
 else:
  defaults={k:spec[4] for k,spec in SPECS.items()}
  if any(abs(values[k]-defaults[k])>1e-8 for k in defaults):
   raise BodyError('Aplique as alterações antes de salvar o estado atual.')
 data={'format':'bodiez-body-state','format_version':1,'saved_at':int(time.time()),'asset_id':a,'preparation_id':p,'customization_id':b,'revision_id':revision_id,'values':values,'bindings':bindings,'breast_markers':markers}
 path=resolve_preparation_root(a,p)/STATE_FILE;jwrite(path,data)
 preview_url,blend_url=_urls(a,p,b,revision_id)
 return {**data,'capabilities':caps,'preview_url':preview_url,'blend_url':blend_url}

def load_current_state(a,p):
 path=resolve_preparation_root(a,p)/STATE_FILE
 if not path.is_file():raise FileNotFoundError(STATE_FILE)
 data=jread(path)
 if data.get('format')!='bodiez-body-state' or data.get('format_version')!=1:raise BodyError('Estado corporal salvo incompatível.')
 if data.get('asset_id')!=a or data.get('preparation_id')!=p:raise BodyError('Estado corporal salvo pertence a outra preparação.')
 b=data.get('customization_id')
 if not isinstance(b,str):raise BodyError('Estado corporal salvo sem personalização válida.')
 root_for(a,p,b);caps=caps_for(a,p,b)
 values,bindings=normalize(caps,data.get('values',{}),data.get('bindings',{}),data.get('breast_markers'))
 markers=normalize_markers(caps,data.get('breast_markers'))
 revision_id=data.get('revision_id')
 if revision_id is not None:
  rr=revision_root(a,p,b,revision_id)
  if not (rr/'customized.blend').is_file() or not (rr/'customized.glb').is_file():raise BodyError('Os arquivos da revisão salva não estão mais disponíveis.')
 preview_url,blend_url=_urls(a,p,b,revision_id)
 return {**data,'values':values,'bindings':bindings,'breast_markers':markers,'capabilities':caps,'preview_url':preview_url,'blend_url':blend_url}
