import json
from pathlib import Path
import pytest
from app import export_service as s

@pytest.fixture()
def root(tmp_path,monkeypatch): monkeypatch.setattr(s,'assets_root',lambda:tmp_path); return tmp_path

def make_preparation(root:Path):
 a,p='a'*32,'b'*32; prep=root/a/'preparations'/p; (prep/'output').mkdir(parents=True); (prep/'output'/'prepared.blend').write_bytes(b'prepared'); (prep/'preparation.json').write_text(json.dumps({'ready_for_body_customization':True})); return a,p,prep

def make_customization(root:Path):
 a,p,prep=make_preparation(root); c,r='c'*32,'d'*32; rev=prep/'customizations'/c/'revisions'/r; rev.mkdir(parents=True); (rev/'customized.blend').write_bytes(b'custom'); (rev/'request.json').write_text(json.dumps({'values':{'height':1.05},'bindings':{'arm_volume':'auto:arm'}})); return a,p,c,r,rev

def test_lists_prepared_and_customized_sources(root):
 a,p,c,r,_=make_customization(root); rows=s.list_export_sources(); assert {x['kind'] for x in rows}=={'preparation','customization_revision'}; custom=next(x for x in rows if x['kind']=='customization_revision'); assert custom['asset_id']==a and custom['preparation_id']==p and custom['customization_id']==c and custom['revision_id']==r and custom['body_editable'] is True

def test_project_records_body_state_and_copies_source(root):
 a,p,c,r,rev=make_customization(root); project=s.create_project({'kind':'customization_revision','asset_id':a,'preparation_id':p,'customization_id':c,'revision_id':r},'Meu personagem'); assert project.source_blend.read_bytes()==b'custom'; data=s.load_project(project.project_id); assert data['format']=='bodiez-project' and data['format_version']==1; assert data['body']['values']['height']==1.05; assert data['body']['bindings']['arm_volume']=='auto:arm'; assert data['editability']['authoritative_format']=='blend'; assert data['editability']['interchange_exports_retain_bodiez_control_semantics'] is False; assert (rev/'customized.blend').read_bytes()==b'custom'

def test_pose_and_animation_sources_capture_stage5_state(root):
 a,p,c,r,_=make_customization(root); sid,pose_id,anim_id='e'*32,'f'*32,'1'*32; session=root/'stage5'/sid; session.mkdir(parents=True); source={'kind':'customization_revision','asset_id':a,'preparation_id':p,'customization_id':c,'revision_id':r}; (session/'session.json').write_text(json.dumps({'source':source})); (session/'poses.json').write_text(json.dumps({'poses':{'Hero':{'rotations_degrees':{'Head':{'x':10}}}}})); pose=session/'pose_revisions'/pose_id; pose.mkdir(parents=True); (pose/'posed.blend').write_bytes(b'pose'); (pose/'pose.json').write_text(json.dumps({'rotations_degrees':{'Head':{'x':5,'y':0,'z':0}}})); anim=session/'animations'/anim_id; anim.mkdir(parents=True); (anim/'retargeted.blend').write_bytes(b'anim'); (anim/'report.json').write_text(json.dumps({'status':'ready','root_motion_note':'preserved'})); (anim/'manifest.json').write_text(json.dumps({'root_motion':'preserve','original_name':'walk.fbx'})); rows=s.list_export_sources(); assert {'pose_revision','animation_result'}<={x['kind'] for x in rows}; project=s.create_project({'kind':'animation_result','session_id':sid,'animation_id':anim_id},'Animado'); data=s.load_project(project.project_id); assert data['body']['values']['height']==1.05; assert data['poses']['library']['Hero']['rotations_degrees']['Head']['x']==10; assert data['animation']['manifest']['original_name']=='walk.fbx'

def test_export_job_validates_formats_and_resolution(root):
 a,p,_=make_preparation(root); project=s.create_project({'kind':'preparation','asset_id':a,'preparation_id':p},'Base'); job=s.create_export_job(project.project_id,['blend','glb','glb','png'],1024); assert job.formats==('blend','glb','png'); request=json.loads(job.request.read_text()); assert request['resolution']==1024 and request['outputs']['png']=='character.png';
 with pytest.raises(s.ExportError): s.create_export_job(project.project_id,['obj'],1024)
 with pytest.raises(s.ExportError): s.create_export_job(project.project_id,['blend'],999)

def test_project_ids_and_download_paths_are_confined(root):
 a,p,_=make_preparation(root); project=s.create_project({'kind':'preparation','asset_id':a,'preparation_id':p},'Safe'); job=s.create_export_job(project.project_id,['blend'],512); (job.root/'character-editable.blend').write_bytes(b'out'); assert s.export_file(project.project_id,job.export_id,'blend').read_bytes()==b'out'
 with pytest.raises(s.ExportError): s.project_for('../escape')
 with pytest.raises(s.ExportError): s.export_file(project.project_id,job.export_id,'../x')
