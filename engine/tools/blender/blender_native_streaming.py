"""Run in Blender Text Editor to upgrade existing scenes' native streaming data."""
import bpy
import json
import sys
from pathlib import Path

PROJECT=Path(r'D:\TLOUPS4\fervent-pascal')
BUNDLE=Path(r'D:\TLOUPS4\AustinStreaming\streaming_runtime.json')


def upgrade_scene(bundle=BUNDLE, add_missing=True):
    native=json.loads(Path(bundle).read_text(encoding='utf-8'))
    roots=[o for o in bpy.context.scene.objects if o.get('nd_type')=='streaming_metadata']
    if len(roots)!=1:raise ValueError('Expected one TLOU streaming metadata object')
    old=json.loads(roots[0]['nd_streaming_json'])
    records={r['id']:r for r in native['regions']}
    for r in old['regions']:
        if r['id'] not in records:records[r['id']]=r
    native['regions']=list(records.values())
    # Keep old visual coverage; binary paths are resolved anew on Vita export.
    native['visual_level_ids']=old.get('visual_level_ids',[])
    roots[0]['nd_streaming_json']=json.dumps(native,ensure_ascii=False,separators=(',',':'))
    existing={o.get('nd_region_id') for o in bpy.context.scene.objects if o.get('nd_type') in ('streaming_region','gameplay_region')}
    added=0
    if add_missing:
        collection=bpy.data.collections.get('ND Native Regions') or bpy.data.collections.new('ND Native Regions')
        if collection.name not in bpy.context.scene.collection.children:bpy.context.scene.collection.children.link(collection)
        for record in native['regions']:
            if record['id'] in existing:continue
            parent=bpy.data.objects.new(record['name'],None);collection.objects.link(parent)
            parent['nd_type']=record['type'];parent['nd_region_id']=record['id'];parent['nd_level_id']=record['source_level']
            parent['nd_preview_set']=1;parent['nd_export']=False;parent.hide_render=True;parent.hide_set(True)
            for number,shape in enumerate(record['shapes']):
                vertices=[];faces=[]
                for face in shape['faces']:
                    corners=face['world_vertices'];start=len(vertices)
                    vertices.extend((p[0],-p[2],p[1]) for p in corners)
                    faces.append(list(range(start,start+len(corners))))
                mesh=bpy.data.meshes.new(record['name']+'_volume');mesh.from_pydata(vertices,[],faces);mesh.update()
                obj=bpy.data.objects.new(record['name']+'__shape_'+str(number),mesh);collection.objects.link(obj);obj.parent=parent
                obj['nd_type']='region_volume';obj['nd_region_id']=record['id'];obj['nd_level_id']=record['source_level'];obj['nd_role']='display'
                obj['nd_export']=False;obj.hide_render=True;obj.display_type='WIRE';obj.hide_set(True)
                if 'analytic' in shape:obj['nd_analytic_json']=json.dumps(shape['analytic'])
            added+=1
    cards={card['id']:card for card in native.get('trigger_catalog',{}).get('triggers',[])}
    for obj in bpy.context.scene.objects:
        if obj.get('nd_type') not in ('streaming_region','gameplay_region'):continue
        card=cards.get(obj.get('nd_region_id'))
        if card:
            obj['nd_trigger_info_json']=json.dumps(card,ensure_ascii=False,separators=(',',':'))
            obj['nd_trigger_category']=card['category']
        defaults={'nd_cpp_enabled':False,'nd_cpp_action':'','nd_cpp_phase':'enter',
                  'nd_cpp_once':False,'nd_cpp_target':'','nd_cpp_parameters':'{}'}
        for key,value in defaults.items():
            if key not in obj:obj[key]=value
    for filename in ('blender_streaming_tools.py','blender_vita_export.py','blender_native_streaming.py'):
        text=bpy.data.texts.get(filename) or bpy.data.texts.new(filename);text.clear()
        text.write((PROJECT/'tlou_extractor'/filename).read_text(encoding='utf-8'))
    bpy.context.scene['nd_native_bundle']=str(bundle)
    namespace={'__name__':'nd_native_upgrade_tools','__file__':str(PROJECT/'tlou_extractor/blender_streaming_tools.py')}
    exec(compile(bpy.data.texts['blender_streaming_tools.py'].as_string(),'blender_streaming_tools.py','exec'),namespace)
    had_native_mode=hasattr(bpy.context.scene,'nd_native_enabled') or 'nd_native_enabled' in bpy.context.scene
    namespace['register'](preserve_scene=True)
    if not had_native_mode: bpy.context.scene.nd_native_enabled=True
    print(f'[TLOU Native] Upgraded {len(native["regions"])} regions; added {added}; current scene view preserved',flush=True)
    return native


if __name__=='__main__':upgrade_scene()
