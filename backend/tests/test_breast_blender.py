"""Real Blender tests for weighted bones and world-space surface markers."""
import shutil
import subprocess
from pathlib import Path

import pytest

BLENDER = shutil.which('blender')
SCRIPT = Path(__file__).resolve().parents[1] / 'blender_scripts' / 'body_customize.py'
pytestmark = pytest.mark.skipif(BLENDER is None, reason='Blender is not installed')


def blender(tmp_path, code):
    script = tmp_path / 'check.py'
    script.write_text(code)
    result = subprocess.run([BLENDER, '--background', '--factory-startup', '--disable-autoexec',
                             '--python-exit-code', '1', '--python', str(script)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'BREAST_OK' in result.stdout


def test_marker_morph_locality_restore_clothing_and_transformed_gltf(tmp_path):
    blender(tmp_path, f'''
import bpy, json, runpy, math
from pathlib import Path
from mathutils import Vector
body=runpy.run_path({str(SCRIPT)!r})
from breast_morph import gltf
root=Path({str(tmp_path)!r})
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.object.armature_add();arm=bpy.context.object
bpy.ops.object.mode_set(mode='EDIT');arm.data.edit_bones.remove(arm.data.edit_bones[0])
for name,head in [('Hips',(0,0,1)),('Head',(0,0,1.9)),('LeftArm',(.5,0,1.7)),('RightArm',(-.5,0,1.7)),('Chest',(0,0,1.5))]:
 b=arm.data.edit_bones.new(name);b.head=head;b.tail=Vector(head)+Vector((0,0,.1))
bpy.ops.object.mode_set(mode='OBJECT')
# Rotation, translation and scale catch incorrect glTF/Blender space conversion.
arm.location=(2,-3,4);arm.rotation_euler=(.2,-.3,.4);arm.scale=(1.2,1.2,1.2)
verts=[];faces=[]
for y in [-.2,.2]:
 start=len(verts)
 for z in range(15):
  for x in range(15):verts.append((-.35+x*.05,y,1.1+z*.05))
 for z in range(14):
  for x in range(14):
   i=start+z*15+x;faces.append((i,i+1,i+16,i+15))
for name in ['Body','Shirt']:
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces)
 obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);obj.parent=arm
 obj.vertex_groups.new(name='Chest').add(list(range(len(verts))),1,'REPLACE')
 obj.modifiers.new('Rig','ARMATURE').object=arm
 obj.shape_key_add(name='Basis');original=obj.shape_key_add(name='OriginalChest')
 for vertex in list(original.data)[:225]:vertex.co.y-=.08
 original.value=.5
bpy.context.view_layer.update()
markers={{'left':gltf(arm.matrix_world@Vector((.15,-.24,1.5))),'right':gltf(arm.matrix_world@Vector((-.15,-.24,1.5))),'radius':.13}}
bpy.ops.wm.save_as_mainfile(filepath=str(root/'source.blend'))
body['prep'](*[str(root/n) for n in ['source.blend','baseline.blend','before.glb','caps.json']])
caps=json.loads((root/'caps.json').read_text())
assert caps['controls']['breast_size']['requires_markers']
assert 'auto:breast_size' not in caps['default_bindings']
values=dict(height=1,head_size=1,shoulder_width=1,hip_width=1,arm_length=1,leg_length=1,breast_size=1)
for value in [1,-.5,0]:
 values['breast_size']=value
 (root/'request.json').write_text(json.dumps({{'values':values,'bindings':{{'breast_size':'markers:breast_size'}},'breast_markers':markers}}))
 body['apply'](*[str(root/n) for n in ['baseline.blend','request.json','after.blend','after.glb','result.json']])
 obj=bpy.data.objects['Body'];key=obj.data.shape_keys.key_blocks['Bodiez_Auto_breast_size']
 changed=0
 for i,(base,target) in enumerate(zip(obj.data.vertices,key.data)):
  distance=(target.co-base.co).length
  if i>=225:assert distance<1e-7, 'Back must remain unchanged'
  if distance>1e-6:changed+=1
  shirt=bpy.data.objects['Shirt'].data.shape_keys.key_blocks[key.name]
  assert (shirt.data[i].co-target.co).length<1e-7
 assert 0<changed<200,changed
 assert abs(key.value-value)<1e-6
 assert obj.data.shape_keys.key_blocks['OriginalChest'].value==.5
 assert json.loads((root/'result.json').read_text())['breast_markers']['affected_vertices_per_side'][0]>0
 def positions():
  o=bpy.data.objects['Body'];ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());me=ev.to_mesh()
  result=[ev.matrix_world@v.co for v in me.vertices];ev.to_mesh_clear();return result
 expected=positions()
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 bpy.ops.import_scene.gltf(filepath=str(root/'after.glb'))
 # glTF splits vertices at triangle normals: compare nearest positions, not indices.
 from mathutils.kdtree import KDTree
 tree=KDTree(len(expected))
 for i,p in enumerate(expected):tree.insert(p,i)
 tree.balance()
 assert max(tree.find(p)[2] for p in positions())<1e-5
 if value==0:
  actual=positions();bpy.ops.wm.open_mainfile(filepath=str(root/'baseline.blend'),load_ui=False)
  baseline=positions();tree=KDTree(len(baseline))
  for i,p in enumerate(baseline):tree.insert(p,i)
  tree.balance();assert max(tree.find(p)[2] for p in actual)<1e-5
# Surface validation rejects detached markers even when they lie in the model bounds.
markers['left'][0]+=.5
(root/'request.json').write_text(json.dumps({{'values':values,'bindings':{{'breast_size':'markers:breast_size'}},'breast_markers':markers}}))
try:body['apply'](*[str(root/n) for n in ['baseline.blend','request.json','invalid.blend','invalid.glb','invalid.json']])
except RuntimeError as e:assert 'superfície' in str(e)
else:raise AssertionError('Detached marker accepted')
print('BREAST_OK')
''')


def test_paired_breast_bones_need_real_weights_and_generate_local_morph(tmp_path):
    blender(tmp_path, f'''
import bpy,runpy,json
from pathlib import Path
from mathutils import Vector
body=runpy.run_path({str(SCRIPT)!r})
from breast_morph import breast_bones,bone_morphs
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.object.armature_add();arm=bpy.context.object
bpy.ops.object.mode_set(mode='EDIT');arm.data.edit_bones.remove(arm.data.edit_bones[0])
for name,x in [('Breast.L',.2),('Breast.R',-.2),('Chest',0)]:
 b=arm.data.edit_bones.new(name);b.head=(x,0,1.5);b.tail=(x,-.2,1.5)
bpy.ops.object.mode_set(mode='OBJECT')
mesh=bpy.data.meshes.new('Body');mesh.from_pydata([(.2,-.2,1.5),(-.2,-.2,1.5),(0,.2,1.5),(.2,-.2,1.6)],[],[(0,1,3),(1,2,3)])
obj=bpy.data.objects.new('Body',mesh);bpy.context.collection.objects.link(obj)
assert not breast_bones(arm,[obj])
obj.vertex_groups.new(name='Breast.L').add([0,3],1,'REPLACE')
assert not breast_bones(arm,[obj])
obj.vertex_groups.new(name='Breast.R').add([1],1,'REPLACE')
obj.vertex_groups.new(name='Chest').add([2],1,'REPLACE')
bones=breast_bones(arm,[obj]);assert bones=={{'left':'Breast.L','right':'Breast.R'}}
assert bone_morphs(arm,[obj],bones)
key=mesh.shape_keys.key_blocks['Bodiez_Auto_breast_size']
assert key.data[0].co.y<-.3 and key.data[1].co.y<-.3
assert (key.data[2].co-mesh.vertices[2].co).length<1e-7
assert key.slider_min==-.5 and key.value==0
obj.parent=arm;obj.modifiers.new('Rig','ARMATURE').object=arm
root=Path({str(tmp_path)!r})
bpy.ops.wm.save_as_mainfile(filepath=str(root/'source.blend'))
original=(root/'source.blend').read_bytes()
body['prep'](*[str(root/n) for n in ['source.blend','baseline.blend','before.glb','caps.json']])
caps=json.loads((root/'caps.json').read_text())
assert caps['controls']['breast_size']['enabled']
assert not caps['controls']['breast_size']['requires_markers']
assert caps['default_bindings']['breast_size']=='auto:breast_size'
source=next(s for s in caps['morph_sources'] if s['source_id']=='auto:breast_size')
values=dict(height=1,head_size=1,shoulder_width=1,hip_width=1,arm_length=1,leg_length=1,breast_size=.5)
(root/'request.json').write_text(json.dumps({{'values':values,'resolved':{{'breast_size':source['targets']}}}}))
body['apply'](*[str(root/n) for n in ['baseline.blend','request.json','after.blend','after.glb','result.json']])
applied=json.loads((root/'result.json').read_text())['values']['breast_size']
assert 0 < applied <= .5
assert bpy.data.objects['Body'].data.shape_keys.key_blocks['Bodiez_Auto_breast_size'].value==applied
assert (root/'source.blend').read_bytes()==original
print('BREAST_OK')
''')


def test_breast_apex_symmetry_and_attachment_are_preserved(tmp_path):
    blender(tmp_path, f'''
import bpy,runpy
body=runpy.run_path({str(SCRIPT)!r})
from breast_morph import marker_morphs
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
vertices=[];faces=[]
for center in [.2,-.2]:
 start=len(vertices)
 for z in range(21):
  for x in range(21):
   dx=(x-10)*.01;dz=(z-10)*.01
   vertices.append((center+dx,-(.2-.025*((dx/.1)**2+(dz/.1)**2)),1.5+dz))
 for z in range(20):
  for x in range(20):
   i=start+z*21+x;faces.append((i,i+1,i+22,i+21))
# Below the breast and behind its estimated attachment plane, but still
# inside the old ellipsoid: this must not become a second chest bulge.
vertices.append((.2,-.14,1.44))
mesh=bpy.data.meshes.new('Breasts');mesh.from_pydata(vertices,[],faces)
obj=bpy.data.objects.new('Breasts',mesh);bpy.context.collection.objects.link(obj)
bpy.context.view_layer.update()
markers={{'left':[.2,1.5,.2],'right':[-.2,1.5,.2],'radius':.1}}
info={{'height':2,'front':[0,0,1],'up':[0,1,0],'left':[1,0,0]}}
marker_morphs([obj],markers,info)
key=mesh.shape_keys.key_blocks['Bodiez_Auto_breast_size']
assert (key.data[-1].co-mesh.vertices[-1].co).length<1e-7, 'Lower chest must remain anchored'
assert max(abs(target.co.y-base.co.y) for base,target in zip(mesh.vertices,key.data))<.025, 'Projection must remain moderate'
# Enlargement must add width and height, rather than only push the apex forward.
def delta(i):return key.data[i].co-mesh.vertices[i].co
apex_projection=-delta(220).y
left_flank,right_flank=10*21+6,10*21+14
lower,upper=6*21+10,14*21+10
assert delta(left_flank).x < 0 < delta(right_flank).x
assert delta(lower).z < 0 < delta(upper).z
assert delta(right_flank).x >= apex_projection*.7, 'Growth still dominated by forward extrusion'
assert -delta(lower).z >= apex_projection*.7, 'Lower pole needs distributed fullness'
assert -delta(lower).z > delta(upper).z, 'Upper attachment should expand more gently'
for z in range(21):
 for x in range(21):
  i=z*21+x;j=441+z*21+(20-x)
  a=key.data[i].co-mesh.vertices[i].co;b=key.data[j].co-mesh.vertices[j].co
  assert abs(a.x+b.x)<1e-7 and abs(a.y-b.y)<1e-7 and abs(a.z-b.z)<1e-7, 'Symmetric bases must deform symmetrically'
def reduced(i):return mesh.vertices[i].co-.5*(key.data[i].co-mesh.vertices[i].co)
for side in range(2):
 start=side*441;apex=-reduced(start+220).y
 for z in range(7,14):
  for x in range(7,14):
   assert -reduced(start+z*21+x).y<=apex+1e-6, 'Reduction created a central dent'
print('BREAST_OK')
''')
