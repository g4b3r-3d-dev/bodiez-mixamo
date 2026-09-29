"""Real Blender regression test for the optional painted breast mask."""
import shutil
import subprocess
from pathlib import Path

import pytest

BLENDER = shutil.which('blender')
MORPH_DIR = Path(__file__).resolve().parents[1] / 'blender_scripts'
pytestmark = pytest.mark.skipif(BLENDER is None, reason='Blender is not installed')


def test_painted_mask_moves_only_brushed_surface(tmp_path):
    script = tmp_path / 'paint_mask.py'
    script.write_text(f'''
import bpy,sys
from mathutils import Vector
sys.path.insert(0,{str(MORPH_DIR)!r})
from breast_morph import marker_morphs,gltf
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
verts=[];faces=[]
for center in (.2,-.2):
 start=len(verts)
 for z in range(11):
  for x in range(11):
   dx=(x-5)*.015;dz=(z-5)*.015
   verts.append((center+dx,-.2-.018*(1-(dx/.075)**2-(dz/.075)**2),1.5+dz))
 for z in range(10):
  for x in range(10):
   i=start+z*11+x;faces.append((i,i+1,i+12,i+11))
mesh=bpy.data.meshes.new('Body');mesh.from_pydata(verts,[],faces);obj=bpy.data.objects.new('Body',mesh);bpy.context.collection.objects.link(obj);bpy.context.view_layer.update()
left=[gltf(Vector((.2+dx,-.218,1.5+dz))) for dx,dz in [(-.02,-.02),(0,-.02),(.02,-.02),(-.02,0),(0,0),(.02,0),(-.02,.02),(0,.02),(.02,.02)]]
right=[gltf(Vector((-.2+dx,-.218,1.5+dz))) for dx,dz in [(-.02,-.02),(0,-.02),(.02,-.02),(-.02,0),(0,0),(.02,0),(-.02,.02),(0,.02),(.02,.02)]]
markers={{'left':gltf(Vector((.2,-.218,1.5))),'right':gltf(Vector((-.2,-.218,1.5))),'radius':.11,'paint':{{'left':left,'right':right,'brush_radius':.032}}}}
info={{'height':2.,'front':[0,0,1],'up':[0,1,0],'left':[1,0,0]}}
marker_morphs([obj],markers,info)
key=mesh.shape_keys.key_blocks['Bodiez_Auto_breast_size']
# Apex/painted center must move.
assert (key.data[5*11+5].co-mesh.vertices[5*11+5].co).length>1e-4
assert (key.data[121+5*11+5].co-mesh.vertices[121+5*11+5].co).length>1e-4
# Outer corners are inside the old spherical radius but outside the painted mask.
for i in (0,10,110,120,121,131,231,241):
 assert (key.data[i].co-mesh.vertices[i].co).length<1e-7,(i,(key.data[i].co-mesh.vertices[i].co).length)
print('PAINT_MASK_OK')
''',encoding='utf-8')
    result = subprocess.run([BLENDER,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script)],capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PAINT_MASK_OK' in result.stdout
