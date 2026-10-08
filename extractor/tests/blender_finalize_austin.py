"""Complete and verify the generated Austin workspace (not a user's edited file)."""
import importlib.util
import json
from pathlib import Path
import sys

import bpy

folder = Path(sys.argv[sys.argv.index('--')+1]).resolve()
repo = Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(folder/'scene.blend'))
supplement = json.loads((folder/'supplement.json').read_text(encoding='utf-8'))
collection = bpy.data.collections.get('Original game collision')
for item in supplement['collisions']:
    if any(o.get('nd_type') == 'collision' and o.name == item['name'] for o in bpy.context.scene.objects):
        continue
    points = list(item['vertices'])
    faces = []
    seen = set()
    for face in item['faces']:
        key = tuple(sorted(face))
        if key in seen:
            first = len(points)
            points.extend(item['vertices'][v] for v in face)
            faces.append(list(range(first,first+len(face))))
        else:
            seen.add(key)
            faces.append(face)
    mesh = bpy.data.meshes.new(item['name'])
    mesh.from_pydata([(x,-z,y) for x,y,z in points],[],faces)
    mesh.update()
    obj = bpy.data.objects.new(item['name'],mesh)
    collection.objects.link(obj)
    obj['nd_type'] = 'collision'
    obj['nd_level_id'] = item['level_id']
    obj['collision'] = True
    obj['collision_kind'] = 'triangle_mesh'
    obj['source_resource'] = item['source_resource']
    obj.display_type = 'WIRE'
    obj.hide_render = True

# Replace only generated region objects in this generated workspace.
for obj in list(bpy.context.scene.objects):
    if obj.get('nd_type') in ('streaming_metadata','streaming_region','gameplay_region','region_volume'):
        bpy.data.objects.remove(obj,do_unlink=True)
for text in list(bpy.data.texts):
    if text.name.startswith(('streaming.json','blender_streaming_tools.py')):
        bpy.data.texts.remove(text)
spec = importlib.util.spec_from_file_location('scene_export',repo/'tlou_extractor/blender_export.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.add_streaming(supplement['streaming'],folder)
bpy.context.view_layer.update()
spec = importlib.util.spec_from_file_location('streaming_tools',folder/'blender_streaming_tools.py')
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)
data = tools.write_streaming(folder/'streaming.bin')
source = json.loads((folder/'scene.json').read_text(encoding='utf-8'))
visuals = {o['nd_level_id'] for o in bpy.context.scene.objects if o.get('nd_type')=='visual'}
assert visuals == {x['level_id'] for x in source['level_glbs']}
assert len(data['regions']) == len(source['streaming']['regions'])
collisions = [o for o in bpy.context.scene.objects if o.get('nd_type')=='collision']
assert len(collisions) == len(source['collisions'])
assert sum(len(o.data.polygons) for o in collisions) == sum(len(c['faces']) for c in source['collisions'])
missing_images = [i.name for i in bpy.data.images if i.source=='FILE' and not i.packed_file and not Path(bpy.path.abspath(i.filepath)).exists()]
assert not missing_images, missing_images
assert all(o.hide_render for o in bpy.context.scene.objects if o.get('nd_type')=='region_volume')
(folder/'START_HERE.md').write_text((repo/'BLENDER_LEVEL_EDITOR.md').read_text(encoding='utf-8'),encoding='utf-8')
bpy.ops.export_scene.fbx(filepath=str(folder/'scene.fbx'),use_selection=False,object_types={'MESH','EMPTY'},
                         add_leaf_bones=False,bake_anim=False,use_custom_props=True,path_mode='COPY',embed_textures=True,
                         axis_forward='-Z',axis_up='Y')
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'scene.blend'))
report = {'visual_levels':len(visuals),'regions':len(data['regions']),
          'volumes':sum(len(r['shapes']) for r in data['regions']),
          'collision_meshes':len(collisions),'collision_triangles':sum(len(o.data.polygons) for o in collisions),
          'missing_images':missing_images,'streaming_metadata':'verified',
          'runtime_ready':False,'warnings':data['warnings']}
(folder/'editor_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('AUSTIN EDITOR VERIFIED', report)
