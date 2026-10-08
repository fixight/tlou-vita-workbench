"""Check editor visibility and retained export data in a real Blender scene."""
import importlib.util
import json
from pathlib import Path
import sys
import bpy

root = Path(__file__).resolve().parents[1]
folder = root / 'editor_exports' / 'austin_editor'
fbx = '--fbx' in sys.argv
if fbx:
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(folder / 'scene.fbx'))
else:
    bpy.ops.wm.open_mainfile(filepath=str(folder / 'scene.blend'))
before = {o.name: (len(o.data.vertices), len(o.data.polygons))
          for o in bpy.context.scene.objects if o.type == 'MESH'}
spec = importlib.util.spec_from_file_location('editor_tools', root / 'tlou_extractor' / 'blender_streaming_tools.py')
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)
tools.register()
print('Registered editor', flush=True)
scene = bpy.context.scene
assert scene.nd_editor_level == 'hom-house-interior'
assert all(o.hide_get() and o.hide_render for o in scene.objects
           if o.get('nd_type') in ('collision', 'region_volume', 'streaming_metadata'))
volumes = [o for o in scene.objects if o.get('nd_type') == 'region_volume']
assert len(volumes) == 375 and all(o.display_type == 'WIRE' for o in volumes)
assert len(tools.collect_streaming()['regions']) == 221
print('Collected all hidden regions', flush=True)
scene.nd_show_streaming = True
assert any(not o.hide_get() for o in volumes)
assert all(o.hide_get() for o in volumes if tools.parent_region(o).get('nd_type') == 'gameplay_region')
scene.nd_show_streaming = False
scene.nd_editor_level = 'hom-house-yard'
assert any(not o.hide_get() for o in scene.objects if o.get('nd_type') == 'visual')
assert all(o.hide_get() for o in scene.objects
           if o.get('nd_type') == 'visual' and o.get('nd_level_id') != 'hom-house-yard')
scene.nd_show_collisions = True
assert any(not o.hide_get() for o in scene.objects if o.get('nd_type') == 'collision')
tools.register()  # Running Alt-P twice must be safe.
import runpy
runpy.run_path(str(root / 'tlou_extractor' / 'blender_streaming_tools.py'), run_name='__main__')
print('Visibility switching passed', flush=True)
assert before == {o.name: (len(o.data.vertices), len(o.data.polygons))
                  for o in scene.objects if o.type == 'MESH'}
visible = sum(not o.hide_get() for o in scene.objects if o.get('nd_type') == 'visual')
report = {'source': 'fbx' if fbx else 'blend', 'visible_visual_meshes': visible,
          'retained_meshes': len(before), 'regions': 221, 'volumes': len(volumes), 'status': 'passed'}
if not fbx:
    source = root / 'tlou_extractor' / 'blender_streaming_tools.py'
    text = bpy.data.texts.get(source.name) or bpy.data.texts.new(source.name)
    text.clear()
    text.write(source.read_text(encoding='utf-8'))
    bpy.ops.nd.focus_level()
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / 'scene_editor.blend'))
    (folder / source.name).write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
(folder / ('editor_fbx_check.json' if fbx else 'editor_view_check.json')).write_text(json.dumps(report, indent=2))
print('EDITOR VIEW PASSED', report)
