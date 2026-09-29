"""Real Blender regression tests; skipped when Blender is unavailable."""
import shutil
import subprocess
from pathlib import Path

import pytest

BLENDER = shutil.which('blender')
SCRIPTS = Path(__file__).resolve().parents[1] / 'blender_scripts'


@pytest.mark.skipif(BLENDER is None, reason='Blender is not installed')
def test_sparse_vertex_groups_without_error_output(tmp_path):
    script = tmp_path / 'check_groups.py'
    script.write_text(f'''
import bpy
import runpy
influenced = runpy.run_path({str(SCRIPTS / 'prepare_body.py')!r})['influenced']
mesh = bpy.data.meshes.new('SparseWeights')
mesh.from_pydata([(i, 0, 0) for i in range(610)], [], [])
obj = bpy.data.objects.new('SparseWeights', mesh)
bpy.context.collection.objects.link(obj)
group = obj.vertex_groups.new(name='Arm')
other = obj.vertex_groups.new(name='Leg')
other.add([0], 1.0, 'REPLACE')
group.add([1], 0.0005, 'REPLACE')
group.add([3, 7], 0.5, 'REPLACE')
assert influenced(obj, 'Arm') == [3, 7]
assert influenced(obj, 'Missing') == []
group.add(list(range(610)), 1.0, 'REPLACE')
sample = influenced(obj, 'Arm')
assert len(sample) == len(set(sample)) == 600
assert sample[0] == 0 and sample[-1] == 609
assert sample == sorted(sample)
print('BODIEZ_GROUP_TEST_OK')
''')
    result = subprocess.run(
        [BLENDER, '--background', '--factory-startup', '--python-exit-code', '1', '--python', str(script)],
        capture_output=True, text=True, timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert 'BODIEZ_GROUP_TEST_OK' in output
    assert 'Vertex not in group' not in output


@pytest.mark.skipif(BLENDER is None, reason='Blender is not installed')
def test_body_controls_survive_animation_and_glb_roundtrip(tmp_path):
    script = tmp_path / 'check_body.py'
    script.write_text(f'''
import bpy, json, runpy
from pathlib import Path
body = runpy.run_path({str(SCRIPTS / 'body_customize.py')!r})
root = Path({str(tmp_path)!r})
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.object.armature_add()
arm = bpy.context.object
bpy.ops.object.mode_set(mode='EDIT')
arm.data.edit_bones.remove(arm.data.edit_bones[0])
for name, x in [('Head', 0), ('LeftArm', 1), ('RightArm', -1)]:
    bone = arm.data.edit_bones.new('mixamorig:' + name)
    bone.head = (x, 0, 0)
    bone.tail = (x + .3, 0, 1)
    if name != 'Head':
        parent = arm.data.edit_bones.new(name+'Shoulder')
        parent.head = (0, 0, 0)
        parent.tail = bone.head
        bone.parent = parent
        bone.use_connect = True
bpy.ops.object.mode_set(mode='OBJECT')
for bone in arm.pose.bones:
    bone.keyframe_insert('scale', frame=1)
    bone.keyframe_insert('scale', frame=20)
action_name = arm.animation_data.action.name
track = arm.animation_data.nla_tracks.new()
track.strips.new('Imported animation', 1, arm.animation_data.action)
mesh = bpy.data.meshes.new('Body')
vertices = []; faces = []
for i, x in enumerate([0, 1, -1]):
    start = len(vertices)
    vertices += [(x-.2, -.1, .3), (x+.2, -.1, .3), (x+.2, .1, .8), (x-.2, .1, .8)]
    faces.append(tuple(range(start, start+4)))
mesh.from_pydata(vertices, [], faces)
obj = bpy.data.objects.new('Body', mesh)
bpy.context.collection.objects.link(obj)
obj.parent = arm
obj.modifiers.new('Rig', 'ARMATURE').object = arm
for i, name in enumerate(['Head', 'LeftArm', 'RightArm']):
    obj.vertex_groups.new(name='mixamorig:'+name).add(list(range(i*4, i*4+4)), 1, 'REPLACE')
bpy.ops.wm.save_as_mainfile(filepath=str(root/'source.blend'))
body['prep'](*[str(root/name) for name in ['source.blend','baseline.blend','baseline.glb','caps.json']])
caps = json.loads((root/'caps.json').read_text())
assert caps['controls']['head_size']['enabled']
assert caps['controls']['arm_volume']['enabled']
values = dict(height=1.1, head_size=1.15, shoulder_width=1.12, hip_width=1, arm_length=1, leg_length=1, arm_volume=.5)
resolved = {{'arm_volume': next(s['targets'] for s in caps['morph_sources'] if s['source_id']=='auto:arm_volume')}}
(root/'request.json').write_text(json.dumps({{'values':values, 'resolved':resolved}}))
body['apply'](*[str(root/name) for name in ['baseline.blend','request.json','changed.blend','changed.glb','result.json']])
bpy.ops.wm.open_mainfile(filepath=str(root/'changed.blend'), load_ui=False)
bpy.context.scene.frame_set(15)
arm = next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
assert arm.animation_data.action is None
assert not arm.animation_data.use_nla
assert action_name in bpy.data.actions
effective=json.loads((root/'result.json').read_text())['values']
assert 1 < effective['head_size'] <= 1.06
for name in ['mixamorig:LeftArm','mixamorig:RightArm']:
    assert arm.pose.bones[name].matrix_basis.to_quaternion().angle < 1e-6, 'Validation poses must not leak into the exported body'
validation=json.loads((root/'result.json').read_text())['natural_shape']['attempts'][-1]['meshes']
assert 'arms_down/Body' in validation and 'hip_flexion/Body' in validation
assert abs(arm.pose.bones['mixamorig:Head'].scale.x - effective['head_size']) < 1e-5
assert abs((arm.pose.bones['mixamorig:LeftArm'].head - arm.pose.bones['mixamorig:RightArm'].head).length - 2*effective['shoulder_width']) < 1e-5
assert abs(bpy.data.objects['Body'].data.shape_keys.key_blocks['Bodiez_Auto_arm_volume'].value-effective['arm_volume']) < 1e-5

def bounds():
    points=[]
    for o in bpy.context.scene.objects:
        if o.type!='MESH' or not any(m.type=='ARMATURE' for m in o.modifiers): continue
        ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get()); me=ev.to_mesh()
        points.extend([ev.matrix_world@v.co for v in me.vertices]); ev.to_mesh_clear()
    return [min(p[i] for p in points) for i in range(3)] + [max(p[i] for p in points) for i in range(3)]
expected=bounds()
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(root/'changed.glb'))
actual=bounds()
assert max(abs(a-b) for a,b in zip(expected, actual)) < 1e-4, (expected, actual)
# Restoring values must use the clean baseline, without accumulating deformation.
values.update(height=1, head_size=1, shoulder_width=1, arm_volume=0)
(root/'request.json').write_text(json.dumps({{'values':values, 'resolved':resolved}}))
body['apply'](*[str(root/name) for name in ['baseline.blend','request.json','restored.blend','restored.glb','restored.json']])
restored=bounds()
bpy.ops.wm.open_mainfile(filepath=str(root/'baseline.blend'), load_ui=False)
assert max(abs(a-b) for a,b in zip(restored,bounds())) < 1e-5
print('BODIEZ_BODY_TEST_OK')
''')
    result = subprocess.run(
        [BLENDER, '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1', '--python', str(script)],
        capture_output=True, text=True, timeout=120,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert 'BODIEZ_BODY_TEST_OK' in output


@pytest.mark.skipif(BLENDER is None, reason='Blender is not installed')
def test_torso_morph_covers_all_spine_bones_and_blended_weights(tmp_path):
    script = tmp_path / 'check_torso.py'
    script.write_text(f'''
import bpy, runpy
body=runpy.run_path({str(SCRIPTS / 'body_customize.py')!r})
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.object.armature_add();arm=bpy.context.object
bpy.ops.object.mode_set(mode='EDIT');arm.data.edit_bones.remove(arm.data.edit_bones[0])
for i,name in enumerate(['Spine','Spine1','Spine2']):
 bone=arm.data.edit_bones.new('mixamorig:'+name);bone.head=(0,0,i);bone.tail=(0,0,i+1)
bpy.ops.object.mode_set(mode='OBJECT')
mesh=bpy.data.meshes.new('Torso');mesh.from_pydata([(1,0,.5),(1,0,1.5),(1,0,2.5),(1,0,1)],[],[])
obj=bpy.data.objects.new('Torso',mesh);bpy.context.collection.objects.link(obj)
for i,name in enumerate(['Spine','Spine1','Spine2']):obj.vertex_groups.new(name='mixamorig:'+name).add([i],1,'REPLACE')
obj.vertex_groups[0].add([3],.5,'REPLACE');obj.vertex_groups[1].add([3],.5,'REPLACE')
mm=body['matches'](arm)
assert all(n in mm for n in ['spine','spine1','spine2'])
body['auto_morph'](obj,arm,[mm[n] for n in body['REGIONS']['torso_volume'] if n in mm],'Bodiez_Auto_torso_volume')
key=mesh.shape_keys.key_blocks['Bodiez_Auto_torso_volume']
for v in key.data:assert abs(v.co.x-1.65)<1e-5,tuple(v.co)
# Regenerating a legacy key must replace its displacement rather than add to it.
body['auto_morph'](obj,arm,[mm[n] for n in body['REGIONS']['torso_volume'] if n in mm],'Bodiez_Auto_torso_volume')
assert abs(key.data[3].co.x-1.65)<1e-5
print('TORSO_TEST_OK')
''')
    result = subprocess.run([BLENDER, '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1', '--python', str(script)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'TORSO_TEST_OK' in result.stdout


@pytest.mark.skipif(BLENDER is None, reason='Blender is not installed')
def test_joint_sampling_checks_full_group_and_preserves_pose(tmp_path):
    script = tmp_path / 'check_joint.py'
    script.write_text(f'''
import bpy, runpy
prep=runpy.run_path({str(SCRIPTS / 'prepare_body.py')!r})
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.object.armature_add();arm=bpy.context.object
bpy.ops.object.mode_set(mode='EDIT');bone=arm.data.edit_bones[0];bone.name='Arm';bone.head=(0,0,0);bone.tail=(0,2,0)
anchor=arm.data.edit_bones.new('Anchor');anchor.head=(0,0,0);anchor.tail=(0,2,0)
bpy.ops.object.mode_set(mode='OBJECT')
mesh=bpy.data.meshes.new('SparseInfluence');mesh.from_pydata([(i*.0001,1,0) for i in range(800)],[],[])
obj=bpy.data.objects.new('SparseInfluence',mesh);bpy.context.collection.objects.link(obj)
modifier=obj.modifiers.new('Armature','ARMATURE');modifier.object=arm
moving=obj.vertex_groups.new(name='Arm');fixed=obj.vertex_groups.new(name='Anchor')
moving.add(list(range(700)),.0011,'REPLACE');fixed.add(list(range(700)),.9989,'REPLACE')
moving.add(list(range(700,800)),1,'REPLACE')
bpy.context.view_layer.update()
pb=arm.pose.bones['Arm'];pb.rotation_mode='QUATERNION';original=pb.matrix_basis.copy()
result=prep['validate_joint'](arm,[obj],'Arm',2)
assert result['passed'],result
assert result['average_displacement']>.01,result
assert pb.rotation_mode=='QUATERNION'
assert all(abs(pb.matrix_basis[i][j]-original[i][j])<1e-6 for i in range(4) for j in range(4))
# Sampling must not approve a mesh whose armature modifier cannot deform it.
modifier.show_viewport=False;bpy.context.view_layer.update()
assert not prep['validate_joint'](arm,[obj],'Arm',2)['passed']
print('JOINT_SAMPLING_OK')
''')
    result = subprocess.run([BLENDER, '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1', '--python', str(script)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'JOINT_SAMPLING_OK' in result.stdout
