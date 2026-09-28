from __future__ import annotations
import asyncio,json
from pathlib import Path
import pytest
from app.body_service import BodyError,create_workspace,create_revision,list_presets,save_preset

def setup(tmp_path,monkeypatch,ready=True):
 data=tmp_path/'data';monkeypatch.setenv('BODIEZ_DATA_DIR',str(data));a='a'*32;p='b'*32;root=data/'assets'/a/'preparations'/p;(root/'output').mkdir(parents=True);(root/'output'/'prepared.blend').write_bytes(b'BLENDER-v300');(root/'preparation.json').write_text(json.dumps({'ready_for_body_customization':ready}));return a,p

def caps():return {'controls':{k:{'enabled':k!='breast_size'} for k in ['height','head_size','shoulder_width','hip_width','arm_length','leg_length','arm_volume','leg_volume','torso_volume','breast_size']},'morph_sources':[{'source_id':'auto:arm_volume','type':'generated','control_hint':'arm_volume','driven':False,'slider_min':-1,'slider_max':1,'targets':[{'mesh':'Body','key':'A'}]},{'source_id':'real:breast','type':'existing','control_hint':None,'driven':False,'slider_min':0,'slider_max':1,'targets':[{'mesh':'Body','key':'Breast'}]}],'default_bindings':{'arm_volume':'auto:arm_volume'}}

def test_workspace_preserves_stage3(tmp_path:Path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));assert w.source.read_bytes()==b'BLENDER-v300'

def test_requires_stage3_ready(tmp_path:Path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch,False)
 with pytest.raises(BodyError):asyncio.run(create_workspace(a,p))

def test_limits_and_explicit_breast_binding(tmp_path:Path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));w.caps.write_text(json.dumps(caps()))
 with pytest.raises(BodyError,match='limite'):create_revision(a,p,w.body_id,{'height':1.5},{})
 with pytest.raises(BodyError,match='indisponível'):create_revision(a,p,w.body_id,{'breast_size':.5},{})
 r=create_revision(a,p,w.body_id,{'breast_size':.5},{'breast_size':'real:breast'});assert r.values['breast_size']==.5

def test_presets_json(tmp_path:Path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));w.caps.write_text(json.dumps(caps()));save_preset(a,p,w.body_id,'Teste',{'height':1.02},{});assert list_presets(a,p,w.body_id)['custom']['Teste']['values']['height']==1.02

def test_explicitly_unbind_generated_morph(tmp_path, monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));w.caps.write_text(json.dumps(caps()))
 revision=create_revision(a,p,w.body_id,{'arm_volume':0},{'arm_volume':''})
 assert 'arm_volume' not in revision.bindings
 assert 'arm_volume' not in json.loads(revision.request.read_text())['resolved']
 with pytest.raises(BodyError,match='sem fonte'):
  create_revision(a,p,w.body_id,{'arm_volume':.2},{'arm_volume':''})
