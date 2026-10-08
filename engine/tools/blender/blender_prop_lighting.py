"""Offline fallback lighting for props without native per-instance light streams.

This is a port approximation sampled from visible native-lit surfaces, NOT a
reader for Naughty Dog light probes. No mesh/collision topology is changed.
"""
from collections import defaultdict
import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

LAYER = 'ND_StaticIrradiance'
MODE = 'surface_sampled_port_approximation'


def _sample(image, uv, cache):
    if image.name not in cache:
        pixels = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(pixels)
        cache[image.name] = pixels.reshape(image.size[1], image.size[0], 4)
    pixels = cache[image.name]
    height, width = pixels.shape[:2]
    x = max(0, min(width-1, float(uv[0])*width-.5))
    y = max(0, min(height-1, float(uv[1])*height-.5))
    ix, iy = int(x), int(y)
    fx, fy = x-ix, y-iy
    return ((pixels[iy,ix]*(1-fx)+pixels[iy,min(ix+1,width-1)]*fx)*(1-fy)
            +(pixels[min(iy+1,height-1),ix]*(1-fx)
              +pixels[min(iy+1,height-1),min(ix+1,width-1)]*fx)*fy)


def _corner_light(obj, loop_index, material, cache):
    mesh = obj.data
    if obj.get('nd_static_lighting_mode') == 'directional_atlas_candidate':
        maps = {node.label: node.image for node in material.node_tree.nodes
                if node.type == 'TEX_IMAGE' and node.image} if material and material.use_nodes else {}
        keys = ('g_tLmBaseColor','g_tLmLightColor','g_tLmLightDir')
        uv = mesh.uv_layers.get('ND_LightingUV')
        if uv and all(key in maps for key in keys):
            coord = uv.data[loop_index].uv
            base = _sample(maps[keys[0]],coord,cache)[:3]
            direct = _sample(maps[keys[1]],coord,cache)[:3]
            direction = _sample(maps[keys[2]],coord,cache)[:3]
            direction = Vector((float(direction[0]),-float(direction[2]),float(direction[1]))).normalized()
            return np.maximum(base+direct*max(0,mesh.corner_normals[loop_index].vector.dot(direction)),0)
    attr = mesh.color_attributes.get(LAYER)
    index = mesh.loops[loop_index].vertex_index if attr.domain == 'POINT' else loop_index
    return np.maximum(np.array(attr.data[index].color[:3]),0)


def _make_surface_index(objects):
    points, triangles, colors = [], [], []
    cache = {}
    for obj in objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        start = len(points)
        points.extend(obj.matrix_world @ vertex.co for vertex in mesh.vertices)
        for tri in mesh.loop_triangles:
            material = mesh.materials[tri.material_index] if tri.material_index < len(mesh.materials) else None
            # Cutout/blended surfaces must not act as solid lighting barriers.
            if material and material.get('nd_transparency_image'):
                continue
            triangles.append(tuple(start+index for index in tri.vertices))
            colors.append(np.mean([_corner_light(obj,index,material,cache) for index in tri.loops],axis=0))
    return (BVHTree.FromPolygons(points,triangles,all_triangles=True),colors) if triangles else (None,[])


def _preview_material(obj):
    """Use the same albedo * irradiance presentation as native baked surfaces."""
    for slot in obj.material_slots:
        if slot.material and slot.material.get("nd_static_lighting_mode") == MODE:
            continue
        if not slot.material or not slot.material.use_nodes:
            continue
        material = slot.material.copy()
        slot.material = material
        material.name += '_PortLighting'
        material['nd_static_lighting_mode'] = MODE
        nodes, links = material.node_tree.nodes, material.node_tree.links
        shader = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'),None)
        output = next((node for node in nodes if node.type == 'OUTPUT_MATERIAL' and node.is_active_output),None)
        if not shader or not output:
            continue
        albedo = shader.inputs['Base Color']
        multiply = nodes.new('ShaderNodeMixRGB')
        multiply.blend_type = 'MULTIPLY'
        multiply.inputs[0].default_value = 1
        if albedo.is_linked:
            links.new(albedo.links[0].from_socket,multiply.inputs[1])
        else:
            multiply.inputs[1].default_value = albedo.default_value
        vertex = nodes.new('ShaderNodeVertexColor')
        vertex.layer_name = LAYER
        links.new(vertex.outputs['Color'],multiply.inputs[2])
        emission = nodes.new('ShaderNodeEmission')
        emission.inputs['Strength'].default_value = 1
        links.new(multiply.outputs[0],emission.inputs['Color'])
        links.new(emission.outputs[0],output.inputs['Surface'])
        material.cycles.emission_sampling = 'NONE'


def repair_prop_lighting(objects=None, update_preview=True, max_distance=8.0):
    """Bake local estimates once, by level, using rays blocked by lit geometry.

    Leave valid native lighting and artist-authored color attributes unchanged.
    Unresolved props remain reported; they are never declared native-lit.
    Moving props need runtime probes later: these values describe the saved pose.
    """
    objects = list(objects if objects is not None else bpy.context.scene.objects)
    levels = defaultdict(list)
    for obj in objects:
        if obj.type == 'MESH' and obj.get('nd_type') == 'visual':
            levels[str(obj.get('nd_level_id') or 'level')].append(obj)
    report = {'method':MODE,'repaired':[],'unresolved':[],'sampled_vertices':0, 'existing_approximations':[]}
    directions = [Vector(direction) for direction in
                  ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))]
    shared_indices = {}
    for level, meshes in levels.items():
        for obj in meshes:
            if obj.get('nd_static_lighting_mode') == MODE:
                current = list(value for row in obj.matrix_world for value in row)
                if list(obj.get('nd_lighting_reference_matrix',[])) != current:
                    attr = obj.data.color_attributes.get(LAYER)
                    if attr:
                        obj.data.color_attributes.remove(attr)
        donors = [obj for obj in meshes if obj.data.color_attributes.get(LAYER)
                  and obj.get('nd_static_lighting_mode') != MODE]
        report['existing_approximations'].extend(obj.name for obj in meshes
            if obj.get('nd_static_lighting_mode') == MODE and obj.data.color_attributes.get(LAYER))
        targets = [obj for obj in meshes if len(obj.data.vertices)
                   and not obj.data.color_attributes.get(LAYER)
                   and not obj.data.color_attributes.get('Col')]
        if not targets:
            continue
        print('PROP LIGHTING LEVEL',level,'sources',len(donors),'targets',len(targets),flush=True)
        if donors:
            tree, colors = _make_surface_index(donors)
            source_label = 'native-lit surfaces in '+level
        else:
            # Shared actor packages may contain no environment geometry.
            # Select spatially by rays, constrained to the same chapter family.
            family = level.split('-')[0]
            if family not in shared_indices:
                chapter_donors = [obj for other_level, items in levels.items()
                    if other_level.split('-')[0] == family for obj in items
                    if obj.data.color_attributes.get(LAYER)
                    and obj.get('nd_static_lighting_mode') != MODE]
                shared_indices[family] = _make_surface_index(chapter_donors)
            tree, colors = shared_indices[family]
            source_label = 'nearby native-lit chapter surfaces: '+family
        for obj in targets:
            if tree is None:
                report['unresolved'].append(obj.name)
                continue
            values = []
            unresolved_vertices = 0
            normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
            for vertex in obj.data.vertices:
                normal = (normal_matrix @ vertex.normal).normalized()
                origin = obj.matrix_world @ vertex.co + normal*.01
                total = np.zeros(3)
                weight_sum = 0.0
                for direction in directions:
                    position, _, triangle, distance = tree.ray_cast(origin,direction,max_distance)
                    if position is None or distance < .005:
                        continue
                    weight = (.25+max(0,normal.dot(direction)))/(1+distance)
                    total += colors[triangle]*weight
                    weight_sum += weight
                if weight_sum:
                    values.append((*tuple(total/weight_sum),1))
                else:
                    values.append((0,0,0,1))
                    unresolved_vertices += 1
            if not values or unresolved_vertices == len(values):
                report['unresolved'].append(obj.name)
                continue
            # Do not modify another instance sharing this mesh datablock.
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            attr = obj.data.color_attributes.new(name=LAYER,type='FLOAT_COLOR',domain='POINT')
            attr.data.foreach_set('color',np.array(values,dtype='f4').ravel())
            obj['nd_static_lighting_mode'] = MODE
            obj['nd_lighting_source'] = source_label
            obj['nd_lighting_unresolved_vertices'] = unresolved_vertices
            obj['nd_lighting_reference_matrix'] = list(value for row in obj.matrix_world for value in row)
            if update_preview:
                _preview_material(obj)
            report['repaired'].append(obj.name)
            report['sampled_vertices'] += len(values)
    return report
