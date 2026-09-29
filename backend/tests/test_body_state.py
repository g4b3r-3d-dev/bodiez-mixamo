from __future__ import annotations
import asyncio,json
from pathlib import Path
import pytest
from app.body_service import BodyError,SPECS,create_revision,create_workspace
from app.body_state import load_current_state,save_current_state


def setup(tmp_path,monkeypatch):
 data=tmp_path/'data';monkeypatch.setenv('BODIEZ_DATA_DIR',str(data));a='a'*32;p='b'*32;root=data/'assets'/a/'preparations'/p;(root/'output').mkdir(parents=True);(root/'output'/'prepared.blend').write_bytes(b'BLENDER-v300');(root/'preparation.json').write_text(json.dumps({'ready_for_body_customization':True}));return a,p

def capabilities():
 return {'controls':{k:{'enabled':True} for k in SPECS},'morph_sources':[],'default_bindings':{}}

def defaults():return {k:v[4] for k,v in SPECS.items()}

def test_save_and_reload_baseline_state(tmp_path:Path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));w.caps.write_text(json.dumps(capabilities()));w.baseline.write_bytes(b'blend');w.preview.write_bytes(b'glb')
 saved=save_current_state(a,p,w.body_id,defaults(),{},None,None)
 assert saved['format']=='bodiez-body-state' and saved['revision_id'] is None
 loaded=load_current_state(a,p)
 assert loaded['customization_id']==w.body_id and loaded['values']==defaults()
 assert loaded['preview_url'].endswith('/preview.glb') and loaded['blend_url'] is None

def test_save_and_reload_exact_applied_revision(tmp_path:Path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));w.caps.write_text(json.dumps(capabilities()));w.baseline.write_bytes(b'blend');w.preview.write_bytes(b'glb')
 r=create_revision(a,p,w.body_id,{'height':1.03},{})
 r.blend.write_bytes(b'custom blend');r.preview.write_bytes(b'custom glb');r.report.write_text(json.dumps({'values':r.values}))
 saved=save_current_state(a,p,w.body_id,r.values,r.bindings,None,r.revision_id)
 assert saved['revision_id']==r.revision_id
 loaded=load_current_state(a,p)
 assert loaded['values']['height']==1.03
 assert r.revision_id in loaded['preview_url'] and r.revision_id in loaded['blend_url']

def test_reject_state_that_does_not_match_revision(tmp_path:Path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));w.caps.write_text(json.dumps(capabilities()));r=create_revision(a,p,w.body_id,{'height':1.02},{})
 r.blend.write_bytes(b'custom blend');r.preview.write_bytes(b'custom glb');r.report.write_text(json.dumps({'values':r.values}))
 with pytest.raises(BodyError,match='não corresponde'):
  save_current_state(a,p,w.body_id,{**r.values,'height':1.04},{},None,r.revision_id)

def test_missing_saved_state_is_not_invented(tmp_path:Path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch)
 with pytest.raises(FileNotFoundError):load_current_state(a,p)
