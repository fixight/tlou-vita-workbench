"""Blender integration: upgrade, native position selection and LVL5 + TLTR export."""
import sys
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from tlou_extractor.blender_native_streaming import upgrade_scene
from tlou_extractor.blender_vita_export import export_vita

args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
if not bpy.data.filepath:
    root=bpy.data.objects.new('streaming metadata',None);bpy.context.scene.collection.objects.link(root)
    root['nd_type']='streaming_metadata';root['nd_streaming_json']=json.dumps({'regions':[]})
    for level in ['hom-house-interior','hom-road-suburb']:
        mesh=bpy.data.meshes.new(level);mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
        obj=bpy.data.objects.new(level,mesh);bpy.context.scene.collection.objects.link(obj)
        obj['nd_type']='visual';obj['nd_level_id']=level
        attr=mesh.color_attributes.new(name='ND_StaticIrradiance',type='FLOAT_COLOR',domain='CORNER')
        for item in attr.data:item.color=(1,1,1,1)
before={o.name:tuple(x for row in o.matrix_world for x in row) for o in bpy.context.scene.objects if o.get('nd_type')=='visual'}
native=upgrade_scene()
for name,matrix in before.items():assert matrix==tuple(x for row in bpy.data.objects[name].matrix_world for x in row)
namespace={'__name__':'nd_native_test','__file__':r'D:\TLOUPS4\fervent-pascal\tlou_extractor\blender_streaming_tools.py'}
exec(compile(bpy.data.texts['blender_streaming_tools.py'].as_string(),'blender_streaming_tools.py','exec'),namespace)
namespace['register']();bpy.context.scene.nd_native_enabled=True
player=namespace['ensure_player'](bpy.context.scene)
record=next(r for r in native['regions'] if r['id']=='world-home:regionshape-4747');shape=record['shapes'][0]
point=[(a+b)/2 for a,b in zip(shape['bounds_min'],shape['bounds_max'])]
player.location=(point[0],-point[2],point[1]);bpy.context.view_layer.update()
report=namespace['player_update'](bpy.context.scene,True)
assert report['interregion_rule']=='native_first_match' and report['native_selection']['region_id']
assert len(namespace['NATIVE_TASK_ITEMS'])==27
if args and args[0].endswith('.blend'):
    bpy.ops.wm.save_as_mainfile(filepath=args[0])
    print('PASS: upgraded actual scene, visual transforms unchanged, 27 original tasks, native position selection',flush=True)
else:
    output=Path(r'D:\TLOUPS4\NativeStreamingBlenderTest')
    trigger=next(o for o in bpy.context.scene.objects if o.get('nd_region_id')=='hom-house-interior:hom-house-rgn-explosion-downstairs-1' and o.get('nd_type')=='gameplay_region')
    trigger['nd_cpp_enabled']=True;trigger['nd_cpp_action']='JoelRoomExplosion'
    trigger['nd_cpp_phase']='enter';trigger['nd_cpp_once']=True;trigger['nd_cpp_parameters']='{"delay":2.5}'
    trigger.hide_set(False);bpy.context.view_layer.objects.active=trigger;trigger.select_set(True)
    assert bpy.ops.nd.trigger_details()=={'FINISHED'}
    assert 'ss-hom-house-joel-room-1' in bpy.data.texts['TLOU_TRIGGER_DETAILS.txt'].as_string()
    bpy.context.scene.nd_show_gameplay=True;bpy.context.scene.nd_gameplay_filter='events'
    audio=next(o for o in bpy.context.scene.objects if o.get('nd_trigger_category')=='audio_zone')
    reflection=next(o for o in bpy.context.scene.objects if o.get('nd_trigger_category')=='reflection')
    assert not trigger.hide_get() and audio.hide_get() and reflection.hide_get()
    bpy.context.scene.nd_gameplay_filter='audio_zone'
    assert trigger.hide_get() and not audio.hide_get()
    bpy.context.scene.nd_gameplay_filter='__ALL__'
    result=export_vita(output,scope='ALL')
    metadata=json.loads((output/'assets/metadata/streaming_runtime.json').read_text(encoding='utf-8'))
    assert (output/'assets/metadata/world-home.tltr').read_bytes()[:8]==b'TLTR\x01\0\0\0'
    assert all(metadata['levels'][level]['engine_file']=='app0:/'+result['levels'][level]['file'] for level in result['levels'])
    assert result['streaming']['exported_chunks']==2
    for filename in ('NativeStreaming.h','HomeStory.h','StreamingIntegrationExample.cpp'):
        assert (output/'assets/metadata'/filename).is_file(),filename
    bindings=json.loads((output/'assets/metadata/trigger_bindings.json').read_text(encoding='utf-8'))
    binding=next(b for b in bindings['bindings'] if b['region_id']==trigger['nd_region_id'])
    assert binding['action']['action']=='JoelRoomExplosion' and binding['action']['once']
    assert binding['action']['parameters']=={'delay':2.5} and binding['volumes']
    print('PASS: Blender native metadata, task preview, two separate LVL5 chunks and TLTR with exact app0 paths',flush=True)
