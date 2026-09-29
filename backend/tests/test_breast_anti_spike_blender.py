"""Regression for the topology-aware anti-spike breast deformation."""
import shutil
import subprocess
from pathlib import Path

import pytest


BLENDER = shutil.which('blender')
MORPH_DIR = Path(__file__).resolve().parents[1] / 'blender_scripts'
pytestmark = pytest.mark.skipif(BLENDER is None, reason='Blender is not installed')


def test_anti_spike_smoothing_reduces_needles_and_keeps_boundary_fixed(tmp_path):
    check = tmp_path / 'check_anti_spike.py'
    check.write_text(f'''
import sys
sys.path.insert(0, {str(MORPH_DIR)!r})
import bpy
from mathutils import Vector
from breast_morph import _anti_spike_smooth

# 9x9 regular patch. Outer ring represents the chest attachment and must not move.
size=9
verts=[]
for y in range(size):
    for x in range(size):
        verts.append(((x-4)*.02, (y-4)*.02, 0.0))
faces=[]
for y in range(size-1):
    for x in range(size-1):
        a=y*size+x
        faces.append((a,a+1,a+1+size,a+size))
mesh_data=bpy.data.meshes.new('AntiSpikePatch')
mesh_data.from_pydata(verts, [], faces);mesh_data.update()
obj=bpy.data.objects.new('AntiSpikePatch',mesh_data);bpy.context.scene.collection.objects.link(obj)
points=[obj.matrix_world@v.co for v in mesh_data.vertices]

deltas=[];weights=[]
for y in range(size):
    for x in range(size):
        boundary=x in (0,size-1) or y in (0,size-1)
        if boundary:
            deltas.append(Vector());weights.append(0.0);continue
        # Broad forward expansion with one deliberately catastrophic needle.
        d=Vector((0,0,.35))
        if x==4 and y==4:d.z=4.0
        deltas.append(d);weights.append(1.0)

smoothed,report=_anti_spike_smooth(obj,points,deltas,weights,.10,20.0)
assert report['iterations'] >= 5
assert report['clamped_edges'] > 0
assert report['max_neighbor_jump_after'] < report['max_neighbor_jump_before']*.45, report
# The fixed attachment ring must stay exactly on the original chest.
for y in range(size):
    for x in range(size):
        if x in (0,size-1) or y in (0,size-1):
            assert smoothed[y*size+x].length < 1e-9
# The center must no longer behave like an isolated needle.
center=smoothed[4*size+4]
neighbours=[smoothed[3*size+4],smoothed[5*size+4],smoothed[4*size+3],smoothed[4*size+5]]
avg=sum(neighbours,Vector())/len(neighbours)
assert (center-avg).length < .12, ((center-avg).length,report)
print('ANTI_SPIKE_OK',report)
''', encoding='utf-8')
    result = subprocess.run(
        [BLENDER, '--background', '--factory-startup', '--disable-autoexec',
         '--python-exit-code', '1', '--python', str(check)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'ANTI_SPIKE_OK' in result.stdout
