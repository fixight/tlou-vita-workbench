"""Blender-side roundtrip check: --background --python this.py -- export_folder."""
import json
from pathlib import Path
import sys
import bpy

folder = Path(sys.argv[sys.argv.index('--')+1]).resolve()
source = json.loads((folder/'scene.json').read_text(encoding='utf-8'))
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.fbx(filepath=str(folder/'scene.fbx'))
objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
assert len(objects) == len(source['meshes']) + len(source['collisions'])
for expected in source['collisions']:
    obj = bpy.data.objects.get(expected['name'])
    assert obj is not None and obj.get('collision_kind') == 'triangle_mesh'
    assert len(obj.data.polygons) == len(expected['faces'])
    duplicates = len(expected['faces']) - len({tuple(sorted(f)) for f in expected['faces']})
    assert len(obj.data.vertices) == len(expected['vertices']) + 3*duplicates
    actual = [obj.matrix_world @ v.co for v in obj.data.vertices]
    transformed = [(x,-z,y) for x,y,z in expected['vertices']]
    for axis in range(3):
        for operation in (min,max):
            error=abs(operation(v[axis] for v in actual)-operation(v[axis] for v in transformed))
            assert error < 0.0001, (obj.name,axis,error)
result = {'meshes':len(objects),'collision_objects':len(source['collisions']),
          'collision_triangles':sum(len(m['faces']) for m in source['collisions']),
          'image_count':len(bpy.data.images),'roundtrip':'passed'}
(folder/'roundtrip.json').write_text(json.dumps(result,indent=2))
print(result)
