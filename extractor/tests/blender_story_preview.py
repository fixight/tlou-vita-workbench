"""Exercise the authored Austin tour against real extracted streaming sets."""
import importlib.util
import json
from pathlib import Path
import bpy

root = Path(__file__).resolve().parents[1]
folder = root / 'editor_exports' / 'austin_editor'
bpy.ops.wm.open_mainfile(filepath=str(folder / 'scene_editor.blend'))
source = root / 'tlou_extractor' / 'blender_streaming_tools.py'
spec = importlib.util.spec_from_file_location('story_tools', source)
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)
tools.register()
scene = bpy.context.scene
geometry = {o.name: (len(o.data.vertices), len(o.data.polygons)) for o in scene.objects if o.type == 'MESH'}
original = tools.metadata()
assert len(tools.STORY_ROUTE) == 14
assert bpy.ops.nd.story_step(direction=1) == {'FINISHED'}
assert int(scene.nd_story_step) == 0
assert bpy.ops.nd.story_step(direction=-1) == {'CANCELLED'}
scene.nd_story_variant = 2
assert bpy.ops.nd.story_apply() == {'FINISHED'}
report = json.loads(scene['nd_story_report'])
assert 'hom-house-interior' in report['hidden']
assert 'hom-house-interior-low' in report['shown']
assert 'hom-house-interior' not in report['display']
scene.nd_story_variant = 99
try:
    result = bpy.ops.nd.story_apply()
except RuntimeError as exc:
    assert 'Допустимые варианты' in str(exc)
else:
    assert result == {'CANCELLED'}
assert json.loads(scene['nd_story_report']) == report
scene.nd_story_variant = 1
assert bpy.ops.nd.story_apply() == {'FINISHED'}
reports = []
for i, (_, record) in enumerate(tools.STORY_ROUTE):
    if i:
        assert bpy.ops.nd.story_step(direction=1) == {'FINISHED'}
    actual = json.loads(scene['nd_story_report'])
    expected = record['sets'][actual['variant']]
    assert set(actual['display']) == set(expected['display'])
    assert set(actual['resident_only']) == set(expected.get('resident_only', [])) - set(expected['display'])
    if reports:
        previous = reports[-1]
        assert set(actual['shown']) == set(actual['visible']) - set(previous['visible'])
        assert set(actual['hidden']) == set(previous['visible']) - set(actual['visible'])
        assert set(actual['request_unload']) == set(previous['required']) - set(actual['required'])
    for obj in scene.objects:
        if obj.get('nd_type') == 'visual':
            wanted = obj.get('nd_level_id') in expected['display'] and not tools.is_editor_helper(obj)
            assert obj.hide_get() == (not wanted)
        elif obj.get('nd_type') == 'region_volume':
            assert obj.hide_get() and obj.hide_render
    reports.append(actual)
    print('Tour step passed', i + 1, flush=True)
assert bpy.ops.nd.story_step(direction=1) == {'CANCELLED'}
assert bpy.ops.nd.story_step(direction=-1) == {'FINISHED'}
scene.nd_show_collisions = True
display = set(json.loads(scene['nd_display_levels']))
for obj in scene.objects:
    if obj.get('nd_type') == 'collision':
        owner = obj['nd_level_id']
        assert obj.hide_get() == (not (owner in display or owner.removesuffix('-col') in display))
assert tools.metadata() == original
assert len(tools.collect_streaming()['regions']) == 221
assert geometry == {o.name: (len(o.data.vertices), len(o.data.polygons)) for o in scene.objects if o.type == 'MESH'}
tools.register()
text = bpy.data.texts.get(source.name) or bpy.data.texts.new(source.name)
text.clear()
text.write(source.read_text(encoding='utf-8'))
bpy.ops.wm.save_as_mainfile(filepath=str(folder / 'scene_streaming_preview.blend'))
(folder / source.name).write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
(folder / 'story_preview_validation.json').write_text(json.dumps({'status':'passed', 'steps': reports,
    'regions_preserved': 221, 'meshes_preserved': len(geometry)}, ensure_ascii=False, indent=2), encoding='utf-8')
print('STORY PREVIEW PASSED', flush=True)
