"""Rebind existing editor meshes using native material and geometry identity."""
import bpy, hashlib, json, re
from pathlib import Path
import numpy as np

root=Path(__file__).resolve().parents[1]
folder=root/'editor_exports/austin_editor'
bindings=json.loads((folder/'material_repair_bindings.json').read_text(encoding='utf-8'))
manifest=json.loads((folder/'texture_hq_bindings_manifest.json').read_text(encoding='utf-8'))
uv_binary=(folder/'material_repair_uv.bin').read_bytes()
bpy.ops.wm.open_mainfile(filepath=str(folder/'scene_textures_hq.blend'))
def canonical(name): return re.sub(r'\.\d{3}$','',name)
lookup={}
for record in bindings['records']:
    for digest in record['position_hashes']:
        lookup.setdefault((record['level'],canonical(record['old_material']),digest),[]).append(record)
images={(image.get('nd_source_hash'),image.colorspace_settings.name):image
        for image in bpy.data.images if image.get('nd_source_hash')}
def image_for(h,space):
    key=(h,space)
    if key not in images:
        entry=manifest[h]
        image=bpy.data.images.load(entry['png'],check_existing=False)
        image.colorspace_settings.name=space
        image['nd_source_hash']=h
        image['nd_source_width']=entry['w']; image['nd_source_height']=entry['h']
        images[key]=image
    return images[key]
fixed={}; changes=[]; unresolved=[]; matched=0; restored_uv=0; secondary_uv=0
geometry={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.context.scene.objects if o.type=='MESH'}
for obj in bpy.context.scene.objects:
    if obj.type!='MESH' or obj.get('nd_type')!='visual': continue
    positions=np.empty(len(obj.data.vertices)*3,dtype=np.float32)
    obj.data.vertices.foreach_get('co',positions)
    digest=hashlib.sha256(np.rint(positions.astype(np.float64)*10000).astype('<i8').tobytes()).hexdigest()
    for slot in obj.material_slots:
        old=slot.material
        if not old: continue
        candidates=lookup.get((obj.get('nd_level_id'),canonical(old.name),digest),[])
        pairs={(r['diffuse_hash'],r['normal_hash']) for r in candidates}
        if len(pairs)!=1:
            unresolved.append({'object':obj.name,'level':obj.get('nd_level_id'),'material':old.name,'matches':len(pairs)})
            continue
        record=candidates[0]; matched+=1
        if record.get('uv_streams'):
            loop_indices=np.empty(len(obj.data.loops),dtype=np.int32)
            obj.data.loops.foreach_get('vertex_index',loop_indices)
            if not obj.data.uv_layers: restored_uv+=1
            for stream in record['uv_streams']:
                assert stream['count']==len(obj.data.vertices), obj.name
                native=np.frombuffer(uv_binary,dtype='<f4',count=stream['count']*2,offset=stream['offset']).reshape(-1,2)
                values=native[loop_indices].copy()
                values[:,1]=1-values[:,1]  # Blender UVs use the opposite V convention to glTF/native data.
                name=('UVMap','NdUV5','NdUV12')[stream['channel']]
                layer=obj.data.uv_layers.get(name) or obj.data.uv_layers.new(name=name)
                layer.data.foreach_set('uv',values.reshape(-1))
                if stream['channel']:
                    secondary_uv+=1
                else:
                    layer.active_render=True
                    obj.data.uv_layers.active=layer
            primary=obj.data.uv_layers.get('UVMap')
            if primary:
                obj.data.uv_layers.active=primary
                primary.active_render=True
        h,n=record['diffuse_hash'],record['normal_hash']
        key=(old.name,h,n)
        if key not in fixed:
            mat=old.copy()
            mat.name=old.name+'_native'
            mat['nd_diffuse_hash']=h; mat['nd_normal_hash']=n; mat['nd_material_source']=record['source']
            nodes=mat.node_tree.nodes; links=mat.node_tree.links
            shader=next(node for node in nodes if node.type=='BSDF_PRINCIPLED')
            old_link=next(iter(shader.inputs['Base Color'].links),None)
            texture=old_link.from_node if old_link and old_link.from_node.type=='TEX_IMAGE' else None
            old_image=texture.image.name if texture and texture.image else None
            if h and h in manifest:
                if not texture:
                    texture=nodes.new('ShaderNodeTexImage')
                texture.image=image_for(h,'sRGB')
                links.new(texture.outputs['Color'],shader.inputs['Base Color'])
                nodes.active=texture
            else:
                for link in list(shader.inputs['Base Color'].links): links.remove(link)
                mat['nd_requires_shader_parameters']=True
            normal_link=next(iter(shader.inputs['Normal'].links),None)
            if n and n in manifest:
                normal_map=normal_link.from_node if normal_link and normal_link.from_node.type=='NORMAL_MAP' else nodes.new('ShaderNodeNormalMap')
                normal_texture=nodes.new('ShaderNodeTexImage')
                normal_texture.image=image_for(n,'Non-Color')
                links.new(normal_texture.outputs['Color'],normal_map.inputs['Color'])
                links.new(normal_map.outputs['Normal'],shader.inputs['Normal'])
            else:
                for link in list(shader.inputs['Normal'].links): links.remove(link)
            changes.append({'old_material':old.name,'old_image':old_image,'diffuse_hash':h,'normal_hash':n,
                            'new_image':manifest[h].get('name',h) if h in manifest else None,
                            'level':obj.get('nd_level_id')})
            fixed[key]=mat
        slot.material=fixed[key]
    if matched%500==0: print('Material slots matched',matched,flush=True)
assert matched>9500, (matched,len(unresolved),unresolved[:5])
assert geometry=={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.context.scene.objects if o.type=='MESH'}
unused=[image for image in bpy.data.images if image.users==0 and image.name!='Render Result']
bpy.data.batch_remove(ids=unused)
output=Path('D:/TLOUPS4/EditorFixedAustin')
output.mkdir(parents=True,exist_ok=True)
for image in bpy.data.images:
    if image.filepath:
        image.filepath=bpy.path.abspath(image.filepath)
bpy.ops.wm.save_as_mainfile(filepath=str(output/'scene_materials_uv_fixed.blend'),compress=True,relative_remap=False)
report={'matched_slots':matched,'unresolved':unresolved,'changes':changes,'geometry_preserved':len(geometry),
        'restored_missing_uv':restored_uv,'secondary_uv_layers':secondary_uv}
(output/'material_repair_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('MATERIAL REPAIR PASSED',matched,'unresolved',len(unresolved),'UV restored',restored_uv,'secondary',secondary_uv,flush=True)
