import bpy,json,math,sys
from pathlib import Path
from mathutils import Matrix,Vector
profiles=json.loads(Path('D:/TLOUPS4/DoorInteractions/vita_profiles.json').read_text())
for profile in profiles:
    door=next(o for o in bpy.context.scene.objects if o.get('nd_type')=='interactive_door' and o.get('nd_door_id')==profile['door_id'])
    door['nd_door_interaction_profile']=json.dumps(profile)
    name='InteractionEntry_'+profile['door_id']
    marker=bpy.data.objects.get(name)
    if not marker:
        marker=bpy.data.objects.new(name,None);bpy.context.scene.collection.objects.link(marker)
    marker.parent=door;marker.empty_display_type='ARROWS';marker.empty_display_size=.3
    marker['nd_type']='interaction_entry';marker['nd_export']=False
    marker['nd_door_id']=profile['door_id'];marker['nd_character_clip']=profile['clip']
    x,y,z=profile['entry']
    world=Matrix.Translation(Vector((x,-z,y))) @ Matrix.Rotation(math.radians(profile['visual_yaw']),4,'Z')
    marker.matrix_world=world;door['nd_door_entry_object']=marker.name
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath='D:/TLOUPS4/AustinStaticLighting/scene_door_process.blend')
print('DOOR_PROCESS_SCENE_SAVED',flush=True)
