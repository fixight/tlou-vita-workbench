"""Blender adapter for static_lighting.py sidecars.

blender -b scene.blend --python blender_static_lighting.py -- --lighting lighting.json --output preview.blend
Creates an explicitly experimental, emission-only preview; no lamps or rebaking.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np


def digest(values):
    return hashlib.sha256(np.rint(values.astype(np.float64)*10000).astype('<i8').tobytes()).hexdigest()


def apply_lighting(manifest_path, output=None, configure_view=True):
    if output and bpy.data.filepath and Path(output).resolve()==Path(bpy.data.filepath).resolve():
        raise ValueError('Choose a new output .blend; preserve the source editor scene')
    manifest_path = Path(manifest_path)
    folder = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    blob = (folder/'streams.bin').read_bytes()
    lookup = {}
    for record in manifest['records']:
        for h in set(record['position_hashes']):
            lookup.setdefault((record['level'],h),[]).append(record)
    images = {}
    needed=set()
    for record in manifest['records']:
        stream=record['streams'].get('5')
        if not stream: continue
        uv=np.frombuffer(blob,dtype='<f4',offset=stream['offset'],count=stream['count']*2)
        if not np.any(uv) or uv.min()<0 or uv.max()>1: continue
        keys=('g_tLmBaseColor','g_tLmLightColor','g_tLmLightDir')
        if all(record['slots'].get(k) in manifest['textures'] for k in keys):
            needed.update(record['slots'][k] for k in keys)
    for h, entry in manifest['textures'].items():
        if h not in needed: continue
        existing=next((i for i in bpy.data.images if i.get('nd_static_lighting_texture')
                       and i.get('nd_source_hash')==h),None)
        if existing:
            images[h]=existing
            continue
        im = bpy.data.images.load(str(folder/entry['file']),check_existing=False)
        im.colorspace_settings.name = 'Non-Color'
        if tuple(im.size) != (entry['width'],entry['height']):
            raise ValueError('DDS decode failed: '+h)
        # Blender decodes BC6H into float pixels, unlike the old PNG path.
        im.filepath_raw = str(folder/(h+'.exr'))
        im.file_format = 'OPEN_EXR'
        im.save()
        im['nd_source_hash'] = h
        im['nd_static_lighting_texture'] = True
        im.buffers_free()
        images[h] = im
    levels = {r['level'] for r in manifest['records']}
    report = {'experimental':True,'modes':{},'matched':0,'unmatched':[],
              'notes':['Basis/direction formula is provisional, not a reconstruction of the original shader.',
                       'Non-normalized or empty stream 5 is preserved but not sampled as an atlas.',
                       'RGBMax indirect maps are extracted, but not decoded as RGBM without evidence.'],
              'records':[]}
    counts = Counter()
    for obj in bpy.context.scene.objects:
        if configure_view and obj.type == 'LIGHT':
            obj.hide_render = True; obj.hide_set(True)
        if obj.type != 'MESH':
            continue
        visible = obj.get('nd_type') == 'visual' and obj.get('nd_level_id') in levels
        if configure_view:
            obj.hide_render = not visible; obj.hide_set(not visible)
        if not visible: continue
        pos = np.empty(len(obj.data.vertices)*3,dtype=np.float32)
        obj.data.vertices.foreach_get('co',pos)
        candidates = lookup.get((obj.get('nd_level_id'),digest(pos)),[])
        source_name=obj.get('nd_source_mesh','')
        exact = [r for r in candidates if obj.name.endswith(r['mesh']) or obj.data.name==r['mesh']
                 or source_name.endswith(r['mesh'])]
        if exact: candidates = exact
        if len(candidates)!=1:
            report['unmatched'].append(obj.name); continue
        r = candidates[0]
        arrays = {int(k):np.frombuffer(blob,dtype='<f4',offset=v['offset'],count=v['count']*v['components'])
                  .reshape(v['count'],v['components']) for k,v in r['streams'].items()}
        report['matched'] += 1
        for attr, values in arrays.items():
            # Keep exact native data, including unknown/unused components.
            for component in range(values.shape[1]):
                name = f'ND_Stream{attr}_{component}'
                attribute = obj.data.attributes.get(name) or obj.data.attributes.new(name,'FLOAT','POINT')
                attribute.data.foreach_set('value',values[:,component].copy())
        if 8 not in arrays:
            if configure_view:
                obj.hide_render = True; obj.hide_set(True)
            counts['no_baked_stream'] += 1
            continue
        slots = r['slots']
        uv = arrays.get(5)
        atlas = (uv is not None and np.any(uv) and uv.min()>=0 and uv.max()<=1 and
                 all(slots.get(k) in images for k in ('g_tLmBaseColor','g_tLmLightColor','g_tLmLightDir')))
        mode = 'directional_atlas_candidate' if atlas else 'vertex_basis_candidate'
        counts[mode] += 1
        normal = np.empty(len(obj.data.vertices)*3,dtype=np.float32)
        obj.data.vertices.foreach_get('normal',normal)
        normal = normal.reshape(-1,3)
        # Blender coordinates (x,-z,y) -> native (x,y,z).
        native_normal = normal[:,[0,2,1]].copy(); native_normal[:,2] *= -1
        irradiance = arrays[8][:,:3].copy()
        if 9 in arrays and 10 in arrays:
            direction = arrays[10]*2-1
            length = np.linalg.norm(direction,axis=1,keepdims=True)
            direction = direction/np.maximum(length,1e-8)
            cosine = np.maximum(np.sum(native_normal*direction,axis=1),0)
            irradiance += arrays[9]*cosine[:,None]
        irradiance = np.maximum(irradiance,0)
        color = obj.data.color_attributes.get('ND_StaticIrradiance') or obj.data.color_attributes.new(
            name='ND_StaticIrradiance',type='FLOAT_COLOR',domain='POINT')
        color.data.foreach_set('color',np.column_stack((irradiance,np.ones(len(irradiance)))).astype('f4').ravel())
        if atlas:
            layer = obj.data.uv_layers.get('ND_LightingUV') or obj.data.uv_layers.new(name='ND_LightingUV')
            indices = np.empty(len(obj.data.loops),dtype=np.int32)
            obj.data.loops.foreach_get('vertex_index',indices)
            values = uv[indices].copy(); values[:,1] = 1-values[:,1]
            layer.data.foreach_set('uv',values.ravel())
        for slot in obj.material_slots:
            if slot.material is None or not slot.material.use_nodes: continue
            mat = slot.material.copy(); slot.material = mat
            mat.name += '_StaticPreview'; mat['nd_static_lighting_mode'] = mode
            mat['nd_shader_reconstruction'] = 'experimental'
            # Baked surfaces display radiance; they must not become new lamps.
            mat.cycles.emission_sampling = 'NONE'
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            shader = next((n for n in nodes if n.type=='BSDF_PRINCIPLED'),None)
            if shader is None: continue
            albedo = shader.inputs['Base Color']
            albedo_link = next(iter(albedo.links),None)
            output_node = next(n for n in nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output)
            vertex = nodes.new('ShaderNodeVertexColor'); vertex.layer_name = 'ND_StaticIrradiance'
            lighting = vertex.outputs['Color']
            if atlas:
                uv_node = nodes.new('ShaderNodeUVMap'); uv_node.uv_map = 'ND_LightingUV'
                maps = {}
                for key in ('g_tLmBaseColor','g_tLmLightColor','g_tLmLightDir'):
                    tex = nodes.new('ShaderNodeTexImage'); tex.image = images[slots[key]]
                    tex.label = key; tex.extension = 'EXTEND'
                    links.new(uv_node.outputs['UV'],tex.inputs['Vector']); maps[key]=tex.outputs['Color']
                separate = nodes.new('ShaderNodeSeparateXYZ'); links.new(maps['g_tLmLightDir'],separate.inputs[0])
                negate = nodes.new('ShaderNodeMath'); negate.operation='MULTIPLY'; negate.inputs[1].default_value=-1
                links.new(separate.outputs['Z'],negate.inputs[0])
                combine = nodes.new('ShaderNodeCombineXYZ')
                links.new(separate.outputs['X'],combine.inputs['X'])
                links.new(negate.outputs[0],combine.inputs['Y'])
                links.new(separate.outputs['Y'],combine.inputs['Z'])
                normalize = nodes.new('ShaderNodeVectorMath'); normalize.operation='NORMALIZE'
                links.new(combine.outputs[0],normalize.inputs[0])
                geometry = nodes.new('ShaderNodeNewGeometry')
                dot = nodes.new('ShaderNodeVectorMath'); dot.operation='DOT_PRODUCT'
                links.new(normalize.outputs[0],dot.inputs[0]); links.new(geometry.outputs['Normal'],dot.inputs[1])
                positive = nodes.new('ShaderNodeMath'); positive.operation='MAXIMUM'; positive.inputs[1].default_value=0
                links.new(dot.outputs['Value'],positive.inputs[0])
                direct = nodes.new('ShaderNodeVectorMath'); direct.operation='SCALE'
                links.new(maps['g_tLmLightColor'],direct.inputs[0]); links.new(positive.outputs[0],direct.inputs['Scale'])
                add = nodes.new('ShaderNodeVectorMath'); add.operation='ADD'
                links.new(maps['g_tLmBaseColor'],add.inputs[0]); links.new(direct.outputs[0],add.inputs[1])
                lighting=add.outputs[0]
            multiply = nodes.new('ShaderNodeMixRGB'); multiply.blend_type='MULTIPLY'; multiply.inputs[0].default_value=1
            if albedo_link: links.new(albedo_link.from_socket,multiply.inputs[1])
            else: multiply.inputs[1].default_value=albedo.default_value
            links.new(lighting,multiply.inputs[2])
            emission = nodes.new('ShaderNodeEmission'); emission.inputs['Strength'].default_value=1
            links.new(multiply.outputs[0],emission.inputs['Color'])
            links.new(emission.outputs[0],output_node.inputs['Surface'])
        obj['nd_static_lighting_mode']=mode
        primary=obj.data.uv_layers.get('UVMap')
        if primary: obj.data.uv_layers.active=primary; primary.active_render=True
        report['records'].append({'object':obj.name,'mode':mode,'slots':slots})
    import importlib.util
    helper_path = Path(__file__).with_name('blender_prop_lighting.py')
    spec = importlib.util.spec_from_file_location('nd_prop_lighting', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    report['prop_lighting'] = helper.repair_prop_lighting([
        obj for obj in bpy.context.scene.objects if obj.get('nd_level_id') in levels])
    report['modes']=dict(counts)
    scene=bpy.context.scene
    if configure_view:
        configure_preview_view()
    scene['nd_static_lighting_experimental']=True
    scene['nd_static_lighting_manifest']=str(manifest_path.resolve())
    text=bpy.data.texts.get('STATIC_LIGHTING_README') or bpy.data.texts.new('STATIC_LIGHTING_README')
    text.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (folder/'blender_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if output:
        # Save outside the input folder without breaking external texture paths.
        for image in bpy.data.images:
            if image.filepath: image.filepath=bpy.path.abspath(image.filepath)
        output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=True,relative_remap=False)
        output.with_suffix('.lighting_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('STATIC LIGHTING PREVIEW',report['matched'],dict(counts),'unmatched',len(report['unmatched']),flush=True)
    return report


def configure_preview_view():
    scene=bpy.context.scene
    for obj in scene.objects:
        if obj.type=='LIGHT':
            obj.hide_render=True; obj.hide_set(True)
    scene.world=bpy.data.worlds.new('Static preview - no environment light')
    scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=0
    scene.cycles.max_bounces=0
    scene.view_settings.view_transform='AgX'
    scene.view_settings.exposure=3  # display exposure only; native HDR values stay unchanged.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.shading.type='MATERIAL'
                area.spaces.active.shading.use_scene_world=True
                area.spaces.active.shading.use_scene_lights=True


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--lighting',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    apply_lighting(args.lighting,args.output)
