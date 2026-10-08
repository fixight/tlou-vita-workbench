"""Native updater must retain the user's preview state and object visibility."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from tlou_extractor.blender_native_streaming import upgrade_scene
from tlou_extractor import blender_streaming_tools as tools

scene=bpy.context.scene
if not bpy.data.filepath:
    root=bpy.data.objects.new('streaming metadata',None);scene.collection.objects.link(root)
    root['nd_type']='streaming_metadata'
    root['nd_streaming_json']=Path(r'D:\TLOUPS4\AustinStreaming\streaming_runtime.json').read_text(encoding='utf-8')
    for level in ('hom-house-interior','hom-road-suburb'):
        mesh=bpy.data.meshes.new(level);mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
        obj=bpy.data.objects.new(level,mesh);scene.collection.objects.link(obj)
        obj['nd_type']='visual';obj['nd_level_id']=level
    tools.register()
    tools.INITIALIZING=True
    scene.nd_editor_level='hom-road-suburb';scene.nd_show_gameplay=True
    scene.nd_gameplay_filter='events'
    scene.nd_native_enabled=False;scene.nd_native_task='12';scene.nd_native_object_flag=True
    scene.nd_story_step='5';scene.nd_story_variant=2;scene.nd_player_sim_enabled=True
    tools.INITIALIZING=False
    scene['nd_display_levels']=json.dumps(['hom-road-suburb'])
    scene['nd_story_active']=True;scene['nd_player_report']='{"sentinel":true}'
    tools.update_visibility(scene)
    for kind in ('player_preview','player_spawn'):
        obj=bpy.data.objects.new(kind,None);scene.collection.objects.link(obj)
        obj['nd_type']=kind;obj.location=(12,34,56)
else:
    # First registration after loading must also retain saved RNA/ID properties.
    tools.register(preserve_scene=True)

fields=('nd_editor_level','nd_show_gameplay','nd_gameplay_filter','nd_native_enabled','nd_native_task',
        'nd_native_object_flag','nd_story_step','nd_story_variant','nd_player_sim_enabled')
state={key:getattr(scene,key) for key in fields}
custom={key:scene.get(key) for key in ('nd_display_levels','nd_story_active','nd_player_report')}
bpy.context.view_layer.update()
objects={o.name:(tuple(v for row in o.matrix_world for v in row),o.hide_get(),o.hide_render,o.hide_viewport)
         for o in scene.objects}
upgrade_scene()
assert {key:getattr(scene,key) for key in fields}==state
assert {key:scene.get(key) for key in custom}==custom
for name,previous in objects.items():
    obj=bpy.data.objects[name]
    assert (tuple(v for row in obj.matrix_world for v in row),obj.hide_get(),obj.hide_render,obj.hide_viewport)==previous,name
print('PASS: upgrade retains story, task, native mode, simulation, visible chunks, spawn and existing objects',flush=True)
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
if args:
    bpy.ops.wm.save_as_mainfile(filepath=args[0])
