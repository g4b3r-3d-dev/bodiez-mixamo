from __future__ import annotations
import asyncio,json
from pathlib import Path
import pytest
from app.body_service import BodyError,create_workspace,create_revision,list_presets,save_preset
from app.body_service import caps_for, normalize, PRESETS
from app.body_profile import NATURAL_LIMITS

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

def test_natural_limits_upgrade_existing_workspaces_and_presets(tmp_path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));w.caps.write_text(json.dumps(caps()))
 current=caps_for(a,p,w.body_id)
 assert current['natural_shape']['enabled']
 assert not current['controls']['feminine_curves']['enabled']
 assert current['control_specs']['head_size']['max']==1.06
 values={'head_size':1.15,'arm_volume':.5,'leg_length':.92}
 r=create_revision(a,p,w.body_id,values,{})
 assert r.values['head_size']==1.06 and r.values['arm_volume']==.28 and r.values['leg_length']==.96
 assert json.loads(r.request.read_text())['requested_values']['head_size']==1.15
 saved=save_preset(a,p,w.body_id,'Antigo',values,{})
 assert saved['values']==r.values
 assert normalize(current,r.values,r.bindings)[0]==r.values
 for preset in PRESETS.values():
  assert all(NATURAL_LIMITS[k][0]<=v<=NATURAL_LIMITS[k][1] for k,v in preset.items())

def test_existing_morph_range_is_respected():
 c=caps();c['morph_sources'][1].update(slider_min=-.1,slider_max=.3)
 for value in [-.2,.4]:
  with pytest.raises(BodyError,match='intervalo da fonte'):
   normalize(c,{'breast_size':value},{'breast_size':'real:breast'})

def marker_caps():
 c=caps()
 c['morph_sources'].append({'source_id':'markers:breast_size','type':'markers','control_hint':'breast_size','slider_min':-.5,'slider_max':1,'targets':[]})
 c['breast_marker_info']={'height':2,'radius_min':.05,'radius_max':.19,'radius_default':.12,'bounds_min':[-1,0,-.4],'bounds_max':[1,2,.4],'up':[0,1,0],'front':[0,0,1],'left':[1,0,0],'origin':[0,1,0],'chest_min':1.2,'chest_max':1.8}
 return c

def markers():return {'left':[.15,1.5,.2],'right':[-.15,1.5,.2],'radius':.12}

def test_marker_revision_and_preset_roundtrip(tmp_path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));w.caps.write_text(json.dumps(marker_caps()))
 bindings={'breast_size':'markers:breast_size'}
 r=create_revision(a,p,w.body_id,{'breast_size':-.4},bindings,markers())
 assert json.loads(r.request.read_text())['breast_markers']==markers()
 assert r.breast_markers==markers()
 save_preset(a,p,w.body_id,'Seios',{'breast_size':.5},bindings,markers())
 assert list_presets(a,p,w.body_id)['custom']['Seios']['breast_markers']==markers()

@pytest.mark.parametrize('invalid',[
 None, {}, {'left':[.15,1.5,.2],'radius':.12},
 {**markers(),'left':[float('nan'),1.5,.2]},
 {**markers(),'left':[True,1.5,.2]},
 {**markers(),'left':[10,1.5,.2]},
 {**markers(),'left':[.15,.1,.2]},
 {**markers(),'left':[.15,1.5,-.2]},
 {**markers(),'right':[.15,1.5,.2]},
 {**markers(),'radius':10},
 {**markers(),'radius':float('inf')},
])
def test_reject_invalid_markers_before_creating_revision(tmp_path,monkeypatch,invalid):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));w.caps.write_text(json.dumps(marker_caps()))
 with pytest.raises(BodyError):create_revision(a,p,w.body_id,{'breast_size':.5},{'breast_size':'markers:breast_size'},invalid)
 assert not (w.root/'revisions').exists()

def test_markers_cannot_drive_other_regions(tmp_path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));w.caps.write_text(json.dumps(marker_caps()))
 with pytest.raises(BodyError,match='outra região'):create_revision(a,p,w.body_id,{'arm_volume':.2},{'arm_volume':'markers:breast_size'},markers())

def test_curves_roundtrip_limits_and_legacy_baseline(tmp_path,monkeypatch):
 a,p=setup(tmp_path,monkeypatch);w=asyncio.run(create_workspace(a,p));c=caps()
 w.caps.write_text(json.dumps(c))
 assert create_revision(a,p,w.body_id,{},{}).values['feminine_curves']==0
 with pytest.raises(BodyError,match='indisponível'):
  create_revision(a,p,w.body_id,{'feminine_curves':.5},{})
 c['controls']['feminine_curves']={'enabled':True}
 c['morph_sources'].append({'source_id':'auto:feminine_curves','type':'generated','control_hint':'feminine_curves','slider_min':0,'slider_max':1,'targets':[{'mesh':'Body','key':'Curves'}]})
 c['default_bindings']['feminine_curves']='auto:feminine_curves'
 w.caps.write_text(json.dumps(c))
 r=create_revision(a,p,w.body_id,{'feminine_curves':.65},{})
 assert json.loads(r.request.read_text())['resolved']['feminine_curves']==[{'mesh':'Body','key':'Curves'}]
 save_preset(a,p,w.body_id,'Curvas',{'feminine_curves':.65},{})
 saved=list_presets(a,p,w.body_id)['custom']['Curvas']
 assert saved['values']['feminine_curves']==.65
 assert saved['bindings']['feminine_curves']=='auto:feminine_curves'
 for value in [-.01,1.01,float('nan'),float('inf')]:
  with pytest.raises(BodyError,match='limite'):
   create_revision(a,p,w.body_id,{'feminine_curves':value},{})
 with pytest.raises(BodyError,match='outra região'):
  create_revision(a,p,w.body_id,{'feminine_curves':.5},{'feminine_curves':'auto:arm_volume','arm_volume':''})
