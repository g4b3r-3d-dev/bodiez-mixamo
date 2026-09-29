"""Check the actual localized geometry, restoration, and GLB export in Blender."""
import shutil
import subprocess
from pathlib import Path

import pytest

BLENDER = shutil.which('blender')
SCRIPT = Path(__file__).resolve().parents[1] / 'blender_scripts' / 'body_customize.py'
pytestmark = pytest.mark.skipif(BLENDER is None, reason='Blender is not installed')


def test_curves_shape_locality_transforms_and_restore(tmp_path):
    script = tmp_path / 'check.py'
    script.write_text(f'''
import bpy, runpy, json
from mathutils import Vector
from pathlib import Path
body=runpy.run_path({str(SCRIPT)!r})
from curve_morph import curve_morphs, KEY
root=Path({str(tmp_path)!r})
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.object.armature_add();arm=bpy.context.object
bpy.ops.object.mode_set(mode='EDIT');arm.data.edit_bones.remove(arm.data.edit_bones[0])
for name,head in [('Hips',(0,0,1)),('Head',(0,0,2)),('LeftArm',(.5,0,1.7)),('RightArm',(-.5,0,1.7)),('LeftUpLeg',(.15,0,.94)),('RightUpLeg',(-.15,0,.94))]:
 b=arm.data.edit_bones.new(name);b.head=head;b.tail=Vector(head)+Vector((0,0,.1))
bpy.ops.object.mode_set(mode='OBJECT')
arm.location=(2,-3,4);arm.rotation_euler=(.2,-.3,.4);arm.scale=(1.2,1.2,1.2)
# Waist pair, hip pair, glute, abdomen, chest, knee, hand beside hip.
verts=[(.2,0,1.27),(-.2,0,1.27),(.25,0,.94),(-.25,0,.94),(0,.2,.94),(0,-.2,.94),(0,-.2,1.7),(.15,0,.4),(.25,0,.94)]
for name in ['Body','Clothes']:
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],[(0,1,2),(2,3,4),(4,5,6),(6,7,8)])
 obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);obj.parent=arm
 obj.vertex_groups.new(name='Hips').add(list(range(8)),1,'REPLACE')
 obj.vertex_groups.new(name='LeftArm').add([8],1,'REPLACE')
 obj.modifiers.new('Rig','ARMATURE').object=arm
 obj.shape_key_add(name='Basis');obj.shape_key_add(name='Existing').value=.2
bpy.context.view_layer.update()
assert not curve_morphs(arm,[obj],{{}}), 'Missing rig landmarks must disable control'
bpy.ops.wm.save_as_mainfile(filepath=str(root/'source.blend'))
original=(root/'source.blend').read_bytes()
body['prep'](*[str(root/n) for n in ['source.blend','baseline.blend','before.glb','caps.json']])
caps=json.loads((root/'caps.json').read_text())
assert caps['controls']['feminine_curves']['enabled']
source=next(s for s in caps['morph_sources'] if s['source_id']=='auto:feminine_curves')
# A customization prepared by the previous algorithm must be regenerated.
old=bpy.data.objects['Body'];old['bodiez_version_'+KEY]=1
old.data.shape_keys.key_blocks[KEY].data[0].co.x+=10
bpy.ops.wm.save_as_mainfile(filepath=str(root/'baseline.blend'))
values=dict(height=1,head_size=1,shoulder_width=1,hip_width=1,arm_length=1,leg_length=1)
for value in [1,.35,0]:
 values['feminine_curves']=value
 (root/'request.json').write_text(json.dumps({{'values':values,'resolved':{{'feminine_curves':source['targets']}}}}))
 body['apply'](*[str(root/n) for n in ['baseline.blend','request.json','after.blend','after.glb','result.json']])
 obj=bpy.data.objects['Body'];key=obj.data.shape_keys.key_blocks[KEY]
 assert obj['bodiez_version_'+KEY]==2, 'Old curves must upgrade when applied'
 assert abs(key.value-value)<1e-6
 assert .17<key.data[0].co.x<.19 and -.19<key.data[1].co.x<-.17, 'Waist narrowing must stay moderate and symmetric'
 assert .27<key.data[2].co.x<.29 and -.29<key.data[3].co.x<-.27, 'Hip widening must stay moderate and symmetric'
 assert .22<key.data[4].co.y<.245, 'Glute projection must stay moderate'
 for i in [5,6,7,8]:
  assert (key.data[i].co-Vector(verts[i])).length<1e-6, 'Abdomen, chest, knee and hand must stay unchanged'
 assert obj.data.shape_keys.key_blocks['Existing'].value==bpy.data.objects['Clothes'].data.shape_keys.key_blocks['Existing'].value
 for i in range(len(verts)):
  assert (key.data[i].co-bpy.data.objects['Clothes'].data.shape_keys.key_blocks[KEY].data[i].co).length<1e-6
 # Validate rendered/evaluated positions after exporting and reimporting the GLB.
 def positions():
  o=bpy.data.objects['Body'];ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());me=ev.to_mesh()
  result=[ev.matrix_world@v.co for v in me.vertices];ev.to_mesh_clear();return result
 expected=positions()
 if value==0:
  assert max((p-obj.matrix_world@Vector(v)).length for p,v in zip(expected,verts))<1e-5
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 bpy.ops.import_scene.gltf(filepath=str(root/'after.glb'))
 from mathutils.kdtree import KDTree
 tree=KDTree(len(expected))
 for i,p in enumerate(expected):tree.insert(p,i)
 tree.balance();assert max(tree.find(p)[2] for p in positions())<1e-5
assert (root/'source.blend').read_bytes()==original
print('CURVES_OK')
''')
    result = subprocess.run([BLENDER, '--background', '--factory-startup', '--disable-autoexec',
                             '--python-exit-code', '1', '--python', str(script)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'CURVES_OK' in result.stdout
