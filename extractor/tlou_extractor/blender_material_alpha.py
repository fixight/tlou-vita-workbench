"""Blender opacity from native separate masks, preserving baked surface shading."""
from pathlib import Path
import json
import re
import bpy


def configure(material, enabled=True):
    if not material.use_nodes:
        return False
    image = bpy.data.images.get(material.get('nd_transparency_image', ''))
    if not image:
        return False
    nodes, links = material.node_tree.nodes, material.node_tree.links
    output = next((n for n in nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output), None)
    if not output or not output.inputs['Surface'].links:
        return False
    mix = next((n for n in nodes if n.get('nd_opacity_role')=='mix'), None)
    if mix is None:
        surface = output.inputs['Surface'].links[0].from_socket
        mix = nodes.new('ShaderNodeMixShader'); mix['nd_opacity_role']='mix'; mix.label='Native opacity'
        transparent = nodes.new('ShaderNodeBsdfTransparent'); transparent['nd_opacity_role']='transparent'
        links.new(transparent.outputs[0], mix.inputs[1]); links.new(surface, mix.inputs[2])
        links.new(mix.outputs[0], output.inputs['Surface'])
        texture = nodes.new('ShaderNodeTexImage'); texture['nd_opacity_role']='texture'
        texture.label='g_tNdFetchTransparencyMap'; texture.image=image
        # Follow the original albedo's texture coordinates, never the lightmap UV.
        shader = next((n for n in nodes if n.type=='BSDF_PRINCIPLED'), None)
        pending = [link.from_node for link in shader.inputs['Base Color'].links] if shader else []
        seen = set()
        while pending:
            node = pending.pop(0)
            if node in seen: continue
            seen.add(node)
            if node.type=='TEX_IMAGE' and node.image:
                if node.inputs['Vector'].links:
                    links.new(node.inputs['Vector'].links[0].from_socket,texture.inputs['Vector'])
                texture.extension=node.extension
                break
            pending.extend(link.from_node for socket in node.inputs for link in socket.links)
        channel = nodes.new('ShaderNodeSeparateColor'); channel.mode='RGB'; channel['nd_opacity_role']='red'
        links.new(texture.outputs['Color'],channel.inputs[0])
        scale = nodes.new('ShaderNodeMath'); scale.operation='MULTIPLY'; scale['nd_opacity_role']='scale'
        links.new(channel.outputs['Red'],scale.inputs[0])
        cutoff = nodes.new('ShaderNodeMath'); cutoff.operation='GREATER_THAN'; cutoff['nd_opacity_role']='cutoff'
        links.new(scale.outputs[0],cutoff.inputs[0])
    if output.inputs['Surface'].links[0].from_node!=mix:
        links.new(output.inputs['Surface'].links[0].from_socket,mix.inputs[2])
        links.new(mix.outputs[0],output.inputs['Surface'])
    by_role = {n.get('nd_opacity_role'):n for n in nodes if n.get('nd_opacity_role')}
    by_role['texture'].image=image
    by_role['scale'].inputs[1].default_value=float(material.get('nd_alpha_strength',1.0))
    by_role['cutoff'].inputs[1].default_value=float(material.get('nd_alpha_cutoff',.5))
    for link in list(mix.inputs[0].links): links.remove(link)
    mode=material.get('nd_alpha_mode','BLEND')
    if enabled and mode!='OPAQUE':
        links.new(by_role['cutoff' if mode=='MASK' else 'scale'].outputs[0],mix.inputs[0])
    else: mix.inputs[0].default_value=1
    if hasattr(material,'surface_render_method'): material.surface_render_method='DITHERED'
    elif hasattr(material,'blend_method'): material.blend_method='HASHED'
    material.use_backface_culling=False
    return True


def attach(material, path, key=''):
    image=bpy.data.images.load(str(Path(path).resolve()),check_existing=True)
    image.colorspace_settings.name='Non-Color'
    material['nd_transparency_image']=image.name
    material['nd_transparency_hash']=key
    if 'nd_alpha_mode' not in material: material['nd_alpha_mode']='BLEND'
    if 'nd_alpha_strength' not in material: material['nd_alpha_strength']=1.0
    if 'nd_alpha_cutoff' not in material: material['nd_alpha_cutoff']=.5
    for name in ('nd_alpha_strength','nd_alpha_cutoff'):
        material.id_properties_ui(name).update(min=0.0,max=1.0,soft_min=0.0,soft_max=1.0)
    return configure(material)


def canonical(name):
    name=re.sub(r'\.\d{3}(?=_|$)','',name)
    return re.sub(r'(?:_StaticPreview|_PortLighting|_native)+$','',name)


def apply_manifest(path, missing_only=False):
    path=Path(path)
    document=json.loads(path.read_text(encoding='utf-8')); lookup={};fallback={};by_identity={}
    for record in document['records']:
        key=(record['old_material'],record['diffuse_hash'],record['normal_hash'])
        fallback.setdefault(key,[]).append(record)
        lookup.setdefault(key+(record['source'],),[]).append(record)
        by_identity.setdefault((record['diffuse_hash'],record['normal_hash'],record['source']),[]).append(record)
    used={slot.material for obj in bpy.context.scene.objects if obj.type=='MESH'
          for slot in obj.material_slots if slot.material}
    report={'materials':0,'by_material':{},'missing_images':[],'ambiguous':[]}
    for material in used:
        if missing_only and material.get('nd_transparency_image'): continue
        key=(canonical(material.name),material.get('nd_diffuse_hash',material.get('diffuse_hash','')),
             material.get('nd_normal_hash',material.get('normal_hash','')))
        source=material.get('nd_material_source')
        records=lookup.get(key+(source,),[]) if source else fallback.get(key,[])
        # Lighting/prop copies can rename materials; retain the original PAK and texture hashes.
        if not records and source and key[1]:
            records=by_identity.get((key[1],key[2],source),[])
        if not records:continue
        if len({r['transparency_hash'] for r in records})!=1:
            report['ambiguous'].append(material.name);continue
        record=records[0];image=path.parent/record['image']
        if not image.is_file():report['missing_images'].append(str(image));continue
        if attach(material,image,record['transparency_hash']):
            report['materials']+=1
            label=record['material_name']
            report['by_material'][label]=report['by_material'].get(label,0)+1
    bpy.context.scene['nd_alpha_preview']=True
    if hasattr(bpy.context.scene,'cycles'):
        bpy.context.scene.cycles.transparent_max_bounces=max(16,bpy.context.scene.cycles.transparent_max_bounces)
    return report


def apply_imported(folder):
    count=0; missing=[]
    for material in bpy.data.materials:
        uri=material.get('nd_transparency_uri')
        if not uri: continue
        path=Path(folder)/uri
        if not path.is_file(): missing.append(material.name); continue
        count+=bool(attach(material,path,material.get('nd_transparency_hash','')))
    bpy.context.scene['nd_alpha_preview']=True
    if hasattr(bpy.context.scene,'cycles'):
        bpy.context.scene.cycles.transparent_max_bounces=max(16,bpy.context.scene.cycles.transparent_max_bounces)
    return {'materials':count,'missing':missing}


def toggle(scene):
    for material in bpy.data.materials:
        if material.get('nd_transparency_image'): configure(material,getattr(scene,'nd_alpha_preview',scene.get('nd_alpha_preview',True)))
