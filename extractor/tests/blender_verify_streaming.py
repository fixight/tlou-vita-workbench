"""Run in background Blender after producing streaming_validation/scene.fbx."""
import importlib.util
import json
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Vector

folder = Path(sys.argv[sys.argv.index('--')+1]).resolve()
source = json.loads((folder/'scene.json').read_text())['streaming']
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.fbx(filepath=str(folder/'scene.fbx'))
spec = importlib.util.spec_from_file_location('streaming_tools',folder/'blender_streaming_tools.py')
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)
tools.register()
import runpy
runpy.run_path(str(folder/'blender_streaming_tools.py'), run_name='__main__')
assert all(o.hide_get() and o.display_type == 'WIRE' and o.hide_render
           for o in bpy.context.scene.objects if o.get('nd_type') == 'region_volume')
actual = tools.collect_streaming()
assert len(actual['regions']) == len(source['regions'])
for expected, result in zip(source['regions'],actual['regions']):
    # FBX object ordering is not a stable identity.
    result = next(r for r in actual['regions'] if r['id'] == expected['id'])
    assert result.get('sets') == expected.get('sets')
    assert len(result['shapes']) == len(expected['shapes'])
    expected_points = [v for s in expected['shapes'] for f in s['faces'] for v in f['world_vertices']]
    actual_points = [v for s in result['shapes'] for v in s['vertices']]
    for axis in range(3):
        for op in (min,max):
            assert abs(op(v[axis] for v in expected_points)-op(v[axis] for v in actual_points)) < .003
parent = next(o for o in bpy.context.scene.objects if o.get('nd_type') == 'streaming_region')
rid = parent['nd_region_id']
before = next(r for r in actual['regions'] if r['id']==rid)['editor_origin']
parent.location += Vector((3,5,7))
bpy.context.view_layer.update()
bpy.context.view_layer.objects.active = parent
assert bpy.ops.nd.make_prefetch() == {'FINISHED'}
result = tools.write_streaming(folder/'streaming.bin')
changed = next(r for r in result['regions'] if r['id']==rid)
assert all(abs(a-b-c)<.001 for a,b,c in zip(changed['editor_origin'],before,[3,7,-5]))
assert len(changed['prefetch_shapes']) == len(changed['shapes'])
data=(folder/'streaming.bin').read_bytes()
magic,version,size=struct.unpack_from('<4sII',data)
assert (magic,version,size)==(b'TLST',1,len(data)-12)
assert json.loads(data[12:])['regions']==result['regions']
levels = tools.write_level_binaries(folder/'binary_test')
assert set(levels) == {'hom-house-interior'}
binary = (folder/'binary_test'/levels['hom-house-interior']).read_bytes()
magic,version,jsize,bsize = struct.unpack_from('<4sIII',binary)
assert (magic,version,bsize) == (b'TLVL',1,120)
description = json.loads(binary[16:16+jsize])
assert description['meshes'][0]['corner_count'] == 3
assert len(binary) == 16 + jsize + bsize
points = [struct.unpack_from('<10f',binary,16+jsize+i*40)[:3] for i in range(3)]
assert any(sum(abs(a-b) for a,b in zip(v,(1,0,0)))<.0001 for v in points)
root = next(o for o in bpy.context.scene.objects if o.get('nd_type') == 'streaming_metadata')
assert len(json.loads(root['nd_streaming_json'])['regions']) == 50
(folder/'streaming_roundtrip.json').write_text(json.dumps({'regions':len(result['regions']),
    'fbx_custom_properties':'passed','world_coordinates':'passed','edited_parent_transform':'passed',
    'prefetch_volumes':'passed','binary_roundtrip':'passed','level_binary':'passed'},indent=2))
print('STREAMING ROUNDTRIP PASSED')
