"""Real mesh failures must be caught before exporting the customized body."""
import shutil
import subprocess
from pathlib import Path

import pytest

BLENDER = shutil.which('blender')
SCRIPTS = Path(__file__).resolve().parents[1] / 'blender_scripts'


@pytest.mark.skipif(BLENDER is None, reason='Blender is not installed')
def test_guard_moderates_combined_shapes_and_detects_crossings(tmp_path):
    script = tmp_path/'guard.py'
    script.write_text(f'''
import bpy, sys, numpy as np
sys.path.insert(0, {str(SCRIPTS)!r})
from natural_shape import ShapeGuard, apply_guarded, crossings, points, touching
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
mesh=bpy.data.meshes.new('Body')
mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
obj=bpy.data.objects.new('Body',mesh);bpy.context.collection.objects.link(obj)
obj.shape_key_add(name='Basis');key=obj.shape_key_add(name='Excessive')
key.data[2].co.y=-1
bpy.context.view_layer.update();guard=ShapeGuard([obj])
def apply(values): key.value=values['breast_size']
values,report=apply_guarded({{'breast_size':1}},apply,guard)
assert 0 < values['breast_size'] < 1
assert not report['attempts'][0]['accepted']
assert report['attempts'][-1]['accepted']
assert points(obj)[2,1] > 0, 'Triangle must not invert'
assert np.linalg.norm(points(obj)[2]-np.array([0,1,0])) <= .06
same,report=apply_guarded(values,apply,guard)
assert same==values, 'Reapplying accepted values must be stable'
restored,report=apply_guarded({{'breast_size':0}},apply,guard)
assert np.max(np.abs(points(obj)-np.array([(0,0,0),(1,0,0),(0,1,0)]))) < 1e-7
# Two disconnected triangles intersect away from shared vertices/edges.
tri=np.array([(0,1,2),(3,4,5)])
p=np.array([(0,0,0),(1,0,0),(0,1,0),(.2,.2,-.2),(.2,.2,.2),(.7,.2,.2)])
assert crossings(p,tri)=={{(0,1)}}
# A near-plane numerical contact must not be mistaken for penetration.
p[3,2]=-1e-8
assert not crossings(p,tri)
assert touching(p[tri[0]],p[tri[1]],.0002)
assert not touching(p[tri[0]],p[tri[1]]+np.array([0,0,1]),.0002)
# A new crossing between previously separated surfaces must reduce the request.
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
mesh=bpy.data.meshes.new('Separated')
mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0),(.2,.2,.02),(.2,.2,.06),(.7,.2,.06)],[],[(0,1,2),(3,4,5)])
obj=bpy.data.objects.new('Separated',mesh);bpy.context.collection.objects.link(obj)
obj.shape_key_add(name='Basis');key=obj.shape_key_add(name='Crossing')
for i in [3,4,5]: key.data[i].co.z-=.04
bpy.context.view_layer.update();guard=ShapeGuard([obj])
values,report=apply_guarded({{'breast_size':1}},apply,guard)
assert 0 < values['breast_size'] <= .5
assert report['attempts'][0]['meshes']['Separated']['new_crossings']==1
assert report['attempts'][-1]['accepted']
print('NATURAL_GUARD_OK')
''')
    result = subprocess.run([BLENDER, '--background', '--factory-startup', '--disable-autoexec',
                             '--python-exit-code', '1', '--python', str(script)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout+result.stderr
    assert 'NATURAL_GUARD_OK' in result.stdout
