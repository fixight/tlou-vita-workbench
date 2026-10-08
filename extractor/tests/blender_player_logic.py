import bpy, json, importlib.util, sys
from mathutils import Matrix
from pathlib import Path
root=Path(sys.argv[sys.argv.index('--')+1])
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
document=json.loads((root/'editor_exports/austin_editor/streaming.json').read_text(encoding='utf-8'))
meta=bpy.data.objects.new('TLOU_STREAMING_DATA',None);bpy.context.scene.collection.objects.link(meta)
meta['nd_type']='streaming_metadata';meta['nd_streaming_json']=json.dumps(document)
for record in document['regions']:
    parent=bpy.data.objects.new(record['name'],None);bpy.context.scene.collection.objects.link(parent)
    parent['nd_type']=record['type'];parent['nd_region_id']=record['id']
    parent['nd_preview_set']=record.get('selector',{}).get('value',1)
    for index,shape in enumerate(record['shapes']):
        mesh=bpy.data.meshes.new('volume');mesh.from_pydata([(x,-z,y) for x,y,z in shape['vertices']],[],shape['faces']);mesh.update()
        child=bpy.data.objects.new(record['name']+'__volume_'+str(index),mesh)
        bpy.context.scene.collection.objects.link(child);child.parent=parent;child['nd_type']='region_volume'
summary=json.loads(Path('D:/TLOUPS4/AustinStaticLighting/lighting_summary.json').read_text(encoding='utf-8'))
for level in summary['levels']:
    obj=bpy.data.objects.new(level,None);bpy.context.scene.collection.objects.link(obj)
    obj['nd_type']='visual';obj['nd_level_id']=level
bpy.context.view_layer.update()
for name in ('blender_streaming_tools.py','region_runtime.py'):
    t=bpy.data.texts.get(name) or bpy.data.texts.new(name)
    t.clear();t.write((root/'tlou_extractor'/name).read_text(encoding='utf-8'));t.use_fake_user=True
spec=importlib.util.spec_from_file_location('nd_tools',root/'tlou_extractor/blender_streaming_tools.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.register();s=bpy.context.scene
m.prepare_player_regions(s)
assert s.nd_player_family=='hom'
assert any(rid.startswith('mil-') for rid in m.PLAYER_CACHE['skipped_regions'])
print('VOLUMES',len(m.PLAYER_CACHE['volumes']),'ERRORS',json.dumps(m.PLAYER_CACHE['errors']),flush=True)
p=m.ensure_player(s)
r=m.player_update(s,True)
assert 'world-home:regionshape-4747' in r['active_streaming'],r
assert r['visible_levels']
first=r
# Walk through representative native region centers.
checks=[]
for suffix in ('4746','4752','6157','7267'):
    volume=next(v for v in m.PLAYER_CACHE['volumes'] if v['region'].endswith('regionshape-'+suffix))
    p.matrix_world=Matrix.Translation(volume['shape']['center'])
    r=m.player_update(s,True)
    assert volume['region'] in r['active_regions']
    assert r['request_unload']==sorted(set(first['required'])-set(r['required']))
    checks.append({'region':volume['region'],'visible':r['visible_levels']})
    first=r
# Hold outside, then deliberately allow an empty set.
p.matrix_world=Matrix.Translation((100000,100000,100000))
r=m.player_update(s,True);assert r['held_outside'] and r['display']==first['display']
s.nd_player_hold_outside=False;r=m.player_update(s,True);assert not r['display']
s.nd_player_hold_outside=True
s.nd_player_sim_enabled=True
assert not s.get('nd_player_error'),s.get('nd_player_error')
assert bpy.app.timers.is_registered(m.player_timer)
s.nd_player_sim_enabled=False
assert not bpy.app.timers.is_registered(m.player_timer)
# Repeated script execution must replace, not duplicate handlers/timers.
m.register();assert sum(getattr(h,'_nd_player_preview',False) for h in bpy.app.handlers.depsgraph_update_post)==1
m.prepare_player_regions(s)
v=next(v for v in m.PLAYER_CACHE['volumes'] if v['region']=='world-home:regionshape-4747')
p.matrix_world=Matrix.Translation(v['shape']['center']);m.player_update(s,True)
obj=m.PLAYER_CACHE['parents'][v['region']]
obj['nd_preview_set']=2;r2=m.player_update(s,True)
obj['nd_preview_set']=1;r1=m.player_update(s,True)
assert any(c['region']==v['region'] and c['variant']==2 for c in r2['conditions'])
assert any(c['region']==v['region'] and c['variant']==1 for c in r1['conditions'])
bpy.ops.nd.player_create()
assert not any(rid.startswith('mil-') for rid in r1['active_regions'])
assert sum(o.get('nd_type')=='visual' for o in s.objects)==37
out=Path('D:/TLOUPS4/AustinStaticLighting')
for image in bpy.data.images:
    if image.source=='FILE' and image.filepath and Path(image.filepath).is_absolute():
        image.filepath='//'+Path(image.filepath).relative_to(out).as_posix()
assert all(image.packed_file or not image.filepath or image.filepath.startswith('//') for image in bpy.data.images if image.source=='FILE')
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D' and s.camera:
            view=area.spaces.active.region_3d
            view.view_rotation=s.camera.matrix_world.to_quaternion()
            view.view_distance=4
            view.view_location=s.camera.matrix_world.translation + s.camera.matrix_world.to_quaternion() @ __import__('mathutils').Vector((0,0,-4))
            view.view_perspective='PERSP'
out=Path('D:/TLOUPS4/AustinStaticLighting')
report={'volumes':len(m.PLAYER_CACHE['volumes']),'geometry_errors':m.PLAYER_CACHE['errors'],'positions_checked':checks,'home':r1,'tests':'passed'}
(out/'player_preview_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PLAYER LOGIC VERIFIED',flush=True)
