"""Regression test for rounded/radial breast inflation instead of front extrusion."""
import shutil
import subprocess
from pathlib import Path

import pytest


BLENDER = shutil.which('blender')
MORPH_DIR = Path(__file__).resolve().parents[1] / 'blender_scripts'
pytestmark = pytest.mark.skipif(BLENDER is None, reason='Blender is not installed')


def test_balloon_field_expands_width_height_and_depth_together(tmp_path):
    check = tmp_path / 'check_balloon.py'
    check.write_text(f'''
import sys
sys.path.insert(0, {str(MORPH_DIR)!r})
from mathutils import Vector
from breast_morph import _balloon_delta

lateral=Vector((1,0,0)); up=Vector((0,0,1)); front=Vector((0,-1,0)); radius=.1

def d(x,y,z):
    delta,influence=_balloon_delta(x,y,z,radius,lateral,up,front)
    return delta,influence

apex,_=d(0,0,0)
side,_=d(.04,0,-.004)
lower,_=d(0,-.04,-.004)
upper,_=d(0,.04,-.004)
attachment,attachment_weight=d(0,-.06,-.06)

forward=apex.dot(front)
width=side.dot(lateral)
lower_fullness=-lower.dot(up)
upper_fullness=upper.dot(up)

assert forward > 0
assert width > 0 and lower_fullness > 0 and upper_fullness > 0
# Regression: enlargement must read as volume inflation. Width and lower-pole
# growth are at least comparable to the apex advance, not tiny side effects of
# a mostly-forward extrusion.
assert width >= forward * .95, (width, forward)
assert lower_fullness >= forward * .95, (lower_fullness, forward)
assert side.dot(front) < forward, 'Flank should round out instead of advancing beyond the apex'
assert lower_fullness > upper_fullness, 'Keep a slightly fuller lower pole'
assert attachment_weight == 0 and attachment.length < 1e-9, 'Chest attachment must stay fixed'
# The full-size target should remain moderate relative to the marker radius.
assert forward <= radius * .18, (forward, radius)
print('BALLOON_OK')
''', encoding='utf-8')
    result = subprocess.run(
        [BLENDER, '--background', '--factory-startup', '--disable-autoexec',
         '--python-exit-code', '1', '--python', str(check)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'BALLOON_OK' in result.stdout
