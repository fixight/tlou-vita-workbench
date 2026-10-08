"""Standalone Blender exporter for TLOU_Vita's LVL5 and 16-byte Vertex ABI.

Run in Text Editor, then N -> Vita. No render meshes are used as collision.
"""
bl_info = {'name':'TLOU Vita Native Level Exporter','author':'VitaEngine contributors',
           'version':(1,5,0),'blender':(4,1,0),'category':'Import-Export',
           'location':'View3D > Sidebar > Vita'}
import hashlib
import json
import math
import re
import struct
import datetime
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from bpy.props import StringProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty

VERTEX = struct.Struct('<4B3h2e2b')
assert VERTEX.size == 16
EXPORT_BASE_DIR='D:/VitaEngine/app0/exports/'


def export_native_streaming(root,level_files):
    roots=[o for o in bpy.context.scene.objects if o.get('nd_type')=='streaming_metadata']
    if not roots:return None
    import sys
    project=Path(r'D:\TLOUPS4\fervent-pascal')
    if str(project) not in sys.path:sys.path.insert(0,str(project))
    # The editor may already have an older exporter module loaded in this session.
    import importlib
    from tlou_extractor import streaming_package
    importlib.reload(streaming_package)
    upgrade_document,write_package=streaming_package.upgrade_document,streaming_package.write_package
    text=bpy.data.texts.get('blender_streaming_tools.py')
    if text:
        namespace={'__name__':'nd_vita_metadata','__file__':str(project/'tlou_extractor/blender_streaming_tools.py')}
        exec(compile(text.as_string(),'blender_streaming_tools.py','exec'),namespace)
        document=namespace['collect_streaming']()
    else:document=json.loads(roots[0]['nd_streaming_json'])
    if not document.get('native_grids'):
        bundle=Path(bpy.context.scene.get('nd_native_bundle',r'D:\TLOUPS4\AustinStreaming\streaming_runtime.json'))
        if not bundle.exists():raise ValueError('Run blender_native_streaming.py to install native streaming metadata')
        document=upgrade_document(document,json.loads(bundle.read_text(encoding='utf-8')))
    else:document=upgrade_document(document,document)
    result=write_package(document,root/'assets/metadata',level_files)
    payload=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    (root/'assets/metadata/streaming.bin').write_bytes(struct.pack('<4sII',b'TLST',1,len(payload))+payload)
    (root/'assets/metadata/streaming.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    import shutil
    shutil.copyfile(project/'tlou_extractor/NativeStreaming.h',root/'assets/metadata/NativeStreaming.h')
    return {'packages':result['runtime_packages'],'exported_chunks':len(level_files),
             'diagnostic_triggers':result['diagnostic_triggers'],
            'display_targets_without_chunk':[n for n,r in result['levels'].items() if not r.get('engine_file') and any(n in s['display'] for region in result['regions'] for s in region.get('sets',{}).values())]}


def new_build_folder(base=EXPORT_BASE_DIR):
    base=Path(bpy.path.abspath(str(base)))
    folder=base/('build_'+datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f'))
    folder.mkdir(parents=True,exist_ok=False)
    return folder


def combine_levels(root,level_files):
    """LVL5 keeps ALL collision before ALL instances; concatenate sections separately."""
    entries=[];instance_count=0;triangle_count=0;spawn=None
    for name in level_files.values():
        path=root/name
        with path.open('rb') as source:
            header=source.read(32)
        magic,instances,triangles,lights,*start=struct.unpack('<4sIII4f',header)
        if magic!=b'LVL5' or lights: raise ValueError('Unsupported chunk header')
        entries.append((path,triangles*36));instance_count+=instances;triangle_count+=triangles
        if spawn is None:spawn=start
    if max(instance_count,triangle_count)>0xffffffff: raise ValueError('LVL5 counts exceed uint32')
    def copy_exact(source,out,length):
        while length:
            block=source.read(min(length,1024*1024))
            if not block:raise ValueError('Truncated level chunk')
            out.write(block);length-=len(block)
    with (root/'level.bin').open('wb') as out:
        out.write(struct.pack('<4sIII4f',b'LVL5',instance_count,triangle_count,0,*spawn))
        for path,collision_bytes in entries:
            with path.open('rb') as source:
                source.seek(32);copy_exact(source,out,collision_bytes)
        for path,collision_bytes in entries:
            with path.open('rb') as source:
                source.seek(32+collision_bytes)
                copy_exact(source,out,path.stat().st_size-32-collision_bytes)
    return {'file':'level.bin','instances':instance_count,'collision_triangles':triangle_count}


def native(v):
    return Vector((v.x, v.z, -v.y))


def oct_normal(n):
    x,y,z = n
    divisor = abs(x)+abs(y)+abs(z)
    if divisor < 1e-12: return (0,0)
    x,y,z = x/divisor,y/divisor,z/divisor
    if z < 0:
        x,y = (1-abs(y))*(1 if x>=0 else -1), (1-abs(x))*(1 if y>=0 else -1)
    return round(x*127),round(y*127)


def safe_name(value):
    stem = re.sub(r'[^A-Za-z0-9_-]', '_', value)[:64] or 'level'
    return stem+'_'+hashlib.sha256(value.encode()).hexdigest()[:10]


def player_yaw(player):
    if 'spawn_yaw' in player:return float(player['spawn_yaw'])
    # SINGLE_ARROW points along local Z; old PlayerStart rotates it -90 degrees onto +Y.
    axis=Vector((0,0,1)) if player.type=='EMPTY' and player.empty_display_type=='SINGLE_ARROW' else Vector((0,1,0))
    direction=native(player.matrix_world.to_3x3()@axis)
    if direction.x*direction.x+direction.z*direction.z>1e-10:
        return math.degrees(math.atan2(-direction.x,-direction.z))
    return math.degrees(player.matrix_world.to_euler('XYZ').z)


def spawn_candidate(obj):
    name=re.sub(r'\.\d{3}$','',obj.name)
    name=re.sub(r'[^a-z0-9]','',name.lower())
    return obj.get('nd_type') in ('player_start','player_spawn','spawn_point') or name in ('playerstart','playerspawn','spawnpoint')


def spawn_changed(scene,context):
    obj=scene.nd_vita_spawn
    scene['nd_vita_spawn_name']=obj.name if obj else ''
    if obj:scene['nd_vita_spawn_object']=obj
    elif 'nd_vita_spawn_object' in scene:del scene['nd_vita_spawn_object']


def resolve_spawn(scene):
    explicit=getattr(scene,'nd_vita_spawn',None) or scene.get('nd_vita_spawn_object')
    name=scene.get('nd_vita_spawn_name','')
    if explicit is None and name: explicit=scene.objects.get(name)
    if explicit:
        if explicit.name not in scene.objects:raise ValueError('Spawn marker is outside the current scene')
        return explicit
    if name:raise ValueError('Selected spawn marker is missing: '+name)
    candidates=[o for o in scene.objects if spawn_candidate(o)]
    if len(candidates)>1:raise ValueError('Several spawn markers: choose "Маркер спавна" in N → Vita')
    return candidates[0] if candidates else None


def pixels(image, cache):
    if image.name not in cache:
        a=np.empty(len(image.pixels),dtype=np.float32)
        image.pixels.foreach_get(a)
        if len(a) != image.size[0]*image.size[1]*4 or not len(a):
            raise ValueError('Image unavailable: '+image.name)
        cache[image.name]=a.reshape(image.size[1],image.size[0],4)
    return cache[image.name]


def sample(image,uv,cache):
    a=pixels(image,cache); h,w=a.shape[:2]
    x=max(0,min(w-1,uv[0]*w-.5)); y=max(0,min(h-1,uv[1]*h-.5))
    ix,iy=int(x),int(y); fx,fy=x-ix,y-iy
    return ((a[iy,ix]*(1-fx)+a[iy,min(ix+1,w-1)]*fx)*(1-fy)+
            (a[min(iy+1,h-1),ix]*(1-fx)+a[min(iy+1,h-1),min(ix+1,w-1)]*fx)*fy)


def lighting(mesh, loop, mat, obj, name, cache, report):
    attr=mesh.color_attributes.get(name)
    if name=='ND_StaticIrradiance' and obj.get('nd_static_lighting_mode')=='directional_atlas_candidate':
        maps={n.label:n.image for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image} if mat and mat.use_nodes else {}
        uv=mesh.uv_layers.get('ND_LightingUV')
        if not uv or not all(k in maps for k in ('g_tLmBaseColor','g_tLmLightColor','g_tLmLightDir')):
            raise ValueError('Missing native lighting atlas/UV: '+obj.name)
        tex=uv.data[loop].uv
        base=sample(maps['g_tLmBaseColor'],tex,cache)[:3]
        direct=sample(maps['g_tLmLightColor'],tex,cache)[:3]
        d=sample(maps['g_tLmLightDir'],tex,cache)[:3]
        d=Vector((float(d[0]),-float(d[2]),float(d[1]))).normalized()
        # Same space/formula as the imported native lighting preview.
        return (*tuple(base+direct*max(0,mesh.corner_normals[loop].vector.dot(d))),1)
    if not attr and name=='ND_StaticIrradiance':
        attr=mesh.color_attributes.get('Col')
    if attr:
        idx=mesh.loops[loop].vertex_index if attr.domain=='POINT' else loop
        return tuple(attr.data[idx].color)
    report['unlit_objects'].add(obj.name)
    # Unresolved: preserve the existing appearance and report it explicitly.
    # Missing light is not evidence that the object should be black.
    return (1,1,1,1)


def albedo(mat):
    if not mat or not mat.use_nodes: return None
    shader=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
    if not shader: return None
    socket=shader.inputs['Base Color']
    if socket.is_linked:
        node=socket.links[0].from_node
        if node.type!='TEX_IMAGE' or node.image is None:
            raise ValueError('Unsupported albedo graph: '+mat.name)
        if node.inputs['Vector'].is_linked and node.inputs['Vector'].links[0].from_node.type not in ('UVMAP','TEX_COORD'):
            raise ValueError('Bake procedural/mapped albedo first: '+mat.name)
        return node
    return None


def uv_layer(mesh,mat):
    node=albedo(mat)
    if node and node.inputs['Vector'].is_linked:
        source=node.inputs['Vector'].links[0]
        if source.from_node.type=='UVMAP':
            uv=mesh.uv_layers.get(source.from_node.uv_map)
            if uv is None: raise ValueError('Missing albedo UV: '+source.from_node.uv_map)
            return uv
        if source.from_socket.name!='UV': raise ValueError('Only UV texture coordinates supported: '+mat.name)
    return mesh.uv_layers.get('UVMap') or mesh.uv_layers.active


def resize_rgba(a,limit):
    h,w=a.shape[:2]
    if not limit or max(w,h)<=limit:return a
    scale=limit/max(w,h);nw,nh=max(1,round(w*scale)),max(1,round(h*scale))
    x=np.clip((np.arange(nw)+.5)*w/nw-.5,0,w-1)
    y=np.clip((np.arange(nh)+.5)*h/nh-.5,0,h-1)
    ix,iy=x.astype(int),y.astype(int);fx=(x-ix)[None,:,None];fy=(y-iy)[:,None,None]
    bottom=a[iy[:,None],ix[None,:]]*(1-fx)+a[iy[:,None],np.minimum(ix+1,w-1)[None,:]]*fx
    top=a[np.minimum(iy+1,h-1)[:,None],ix[None,:]]*(1-fx)+a[np.minimum(iy+1,h-1)[:,None],np.minimum(ix+1,w-1)[None,:]]*fx
    return bottom*(1-fy)+top*fy


def export_texture(mat,root,cache,exported,report,max_texture_size=0):
    node=albedo(mat); image=node.image if node else None
    key=(mat.name if mat else 'white')
    if key in exported: return exported[key]
    if image:
        # Albedo is written once; keep only native lighting atlases in the persistent cache.
        a=resize_rgba(pixels(image,{}),max_texture_size)
        # Image.pixels exposes file sample values: byte PNG sRGB is already encoded.
        # Only scene-linear float images need encoding for the GL_RGBA renderer.
        if image.is_float and image.colorspace_settings.name not in ('Non-Color','Raw','sRGB'):
            rgb=np.maximum(a[:,:,:3],0)
            a[:,:,:3]=np.where(rgb<=.0031308,rgb*12.92,1.055*rgb**(1/2.4)-.055)
        report['texture_dimensions'][key]=[int(a.shape[1]),int(a.shape[0])]
    else:
        color=(1,1,1,1)
        if mat and mat.use_nodes:
            shader=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
            if shader: color=tuple(shader.inputs['Base Color'].default_value)
        a=np.array(color,dtype=np.float32).reshape(1,1,4)
        rgb=np.maximum(a[:,:,:3],0); a[:,:,:3]=np.where(rgb<=.0031308,rgb*12.92,1.055*rgb**(1/2.4)-.055)
    # Режим поверхности сохраняется отдельно от RGBA, чтобы движок не гадал
    # по сглаженным краям масок и не путал их со стеклом.
    mode=str(mat.get('nd_alpha_mode','BLEND' if mat.get('nd_transparency_image') else 'OPAQUE') if mat else 'OPAQUE').upper()
    if mode not in ('OPAQUE','MASK','BLEND'): raise ValueError('Unsupported alpha mode: '+mode)
    cutoff=float(mat.get('nd_alpha_cutoff',.5)) if mat else .5
    if not math.isfinite(cutoff) or not 0<=cutoff<=1: raise ValueError('Invalid alpha cutoff: '+key)
    double_sided=bool(mat.get('nd_double_sided',mode!='OPAQUE' and not mat.use_backface_culling)) if mat else False
    # Native mask is combined into albedo alpha.
    if mat and mat.get('nd_transparency_image') and mat.get('nd_alpha_mode','BLEND')!='OPAQUE':
        mask=bpy.data.images.get(mat['nd_transparency_image'])
        if mask is None: raise ValueError('Missing opacity image: '+mat.name)
        m=pixels(mask,{})[:,:,0]; h,w=a.shape[:2]
        yi=np.minimum((np.arange(h)+.5)*m.shape[0]/h,m.shape[0]-1).astype(int)
        xi=np.minimum((np.arange(w)+.5)*m.shape[1]/w,m.shape[1]-1).astype(int)
        opacity=m[yi[:,None],xi[None,:]]*float(mat.get('nd_alpha_strength',1))
        if mat.get('nd_alpha_mode')=='MASK': opacity=opacity>float(mat.get('nd_alpha_cutoff',.5))
        a[:,:,3]*=opacity
        report['alpha_materials'].append(key)
    data=np.rint(np.clip(a,0,1)*255).astype(np.uint8)
    payload=struct.pack('<III',a.shape[1],a.shape[0],data.nbytes)+data.tobytes()
    # Одинаковые RGBA с разными режимами должны быть разными ресурсами.
    mode_id={'OPAQUE':0,'MASK':1,'BLEND':2}[mode]
    material_key=struct.pack('<BBf',mode_id,int(double_sided),cutoff)
    filename=hashlib.sha256(payload+material_key).hexdigest()[:24]+'.bin'
    path=root/'assets'/'textures'/filename
    if not path.exists(): path.write_bytes(payload)
    exported[key]='app0:/assets/textures/'+filename
    report['material_settings'][exported[key]]={'alpha_mode':mode,'alpha_cutoff':cutoff,'double_sided':double_sided}
    return exported[key]



def write_material_settings(root,settings):
    """MAT1 sidecar: UTF-8 texture path, alpha mode, culling and cutoff."""
    with (root/'assets/metadata/materials.bin').open('wb') as out:
        out.write(struct.pack('<4sI',b'MAT1',len(settings)))
        for texture_path,material in sorted(settings.items()):
            encoded=texture_path.encode('utf-8')
            out.write(struct.pack('<H',len(encoded))+encoded)
            out.write(struct.pack('<BBf',{'OPAQUE':0,'MASK':1,'BLEND':2}[material['alpha_mode']],
                                  int(material['double_sided']),material['alpha_cutoff']))


def kd_batches(triangles,max_polys=4500,max_size=170,min_size=5):
    """Median spatial split. Bound real vertices; polygon budget is always strict."""
    if not len(triangles): return
    points=triangles[:,:,:3]
    extent=points.max(axis=(0,1))-points.min(axis=(0,1))
    centers=points.mean(axis=1)
    center_extent=np.ptp(centers,axis=0)
    if len(triangles)<=max_polys and (extent.max()<=max_size or
        (center_extent.max()<=min_size and extent.max()<=655)):
        yield triangles;return
    if len(triangles)==1:
        if extent.max()>655: raise ValueError('Triangle exceeds int16 position range')
        yield triangles;return
    axis=int(np.argmax(center_extent))
    order=np.argsort(centers[:,axis],kind='stable');mid=len(order)//2
    yield from kd_batches(triangles[order[:mid]],max_polys,max_size,min_size)
    yield from kd_batches(triangles[order[mid:]],max_polys,max_size,min_size)


def quantize_batch_positions(positions):
    """One world-centimetre grid for every batch; retain the existing int16 ABI.

    Round world coordinates FIRST. Rounding relative coordinates, even with a
    snapped origin, gives different round-to-even results at ties for odd origins.
    The origin is an integer number of grid steps and is selected to fit int16.
    """
    positions=np.asarray(positions,dtype=np.float64)
    if positions.ndim!=2 or positions.shape[1]!=3 or not len(positions):
        raise ValueError('Expected nonempty Nx3 vertex positions')
    if not np.isfinite(positions).all(): raise ValueError('Non-finite vertex position')
    world_grid=np.rint(positions*100.0)
    # Guard the conversion and midpoint arithmetic against int64 overflow.
    if np.abs(world_grid).max()>2**52: raise ValueError('World position exceeds quantization range')
    world_grid=world_grid.astype(np.int64)
    lower=world_grid.min(axis=0);upper=world_grid.max(axis=0)
    # local = world_grid - origin, with -32768 <= local <= 32767.
    origin_min=upper-32767;origin_max=lower+32768
    if np.any(origin_min>origin_max): raise ValueError('Position span out of int16 range')
    origin=np.rint((lower+upper)*.5).astype(np.int64)
    origin=np.maximum(origin_min,np.minimum(origin,origin_max))
    local=world_grid-origin
    return local,origin.astype(np.float64)/100.0


def write_batch(corners,texture,root,instances,gain,report):
    corners=np.asarray(corners,dtype=np.float32).reshape(-1,12)
    low=corners[:,:3].min(axis=0).astype(np.float64)
    high=corners[:,:3].max(axis=0).astype(np.float64)
    local_positions,center=quantize_batch_positions(corners[:,:3])
    payload=bytearray(struct.pack('<I',len(corners)))
    for row,local_position in zip(corners,local_positions):
        p,n,t,color=row[:3],row[3:6],row[6:8],row[8:12]
        if not np.isfinite(row).all(): raise ValueError('Non-finite vertex')
        xyz=[int(v) for v in local_position]
        if any(v<-32768 or v>32767 for v in xyz): raise ValueError('Position out of int16 range')
        rgb=[float(c)*gain for c in color[:3]]
        if any(c<0 or c>1 for c in rgb): report['clipped_color_corners']+=1
        rgba=[round(max(0,min(1,c))*255) for c in (*rgb,float(color[3]))]
        payload.extend(VERTEX.pack(*rgba,*xyz,*t,*oct_normal(n)))
    filename=hashlib.sha256(payload).hexdigest()[:24]+'.bin'
    path=root/'assets'/'models'/filename
    if not path.exists(): path.write_bytes(payload)
    matrix=[1,0,0,0,0,1,0,0,0,0,1,0,*center,1]
    instances.append((matrix,tuple(v-.0051 for v in low),tuple(v+.0051 for v in high),
                      'app0:/assets/models/'+filename,texture))


def repair_missing_prop_lighting(objects, update_preview=True):
    # File-relative import keeps the standalone Blender add-on usable.
    import importlib.util
    path = Path(__file__).with_name('blender_prop_lighting.py')
    if not path.exists():
        path = Path(r'D:\TLOUPS4\fervent-pascal\tlou_extractor\blender_prop_lighting.py')
    spec = importlib.util.spec_from_file_location('nd_prop_lighting', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.repair_prop_lighting(objects, update_preview=update_preview)


def export_vita(folder,scope='ALL',color_layer='ND_StaticIrradiance',gain=1.0,
                batch_mode='KD',max_polys=4500,max_size=170,min_size=5,max_texture_size=0,require_spawn=False,max_sky_texture_size=1024):
    if max_polys<1 or max_size<=0 or min_size<0 or max_sky_texture_size<1: raise ValueError('Invalid batch/sky texture limits')
    if batch_mode not in ('KD','OBJECT') or max_texture_size<0 or gain<0 or not math.isfinite(gain):
        raise ValueError('Invalid export settings')
    root=Path(bpy.path.abspath(str(folder))); root.mkdir(parents=True,exist_ok=True)
    for name in ('models','textures','levels','metadata'): (root/'assets'/name).mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene
    bpy.context.view_layer.update()
    player=resolve_spawn(scene)
    if require_spawn and player is None:raise ValueError('Choose a spawn marker in N → Vita or create PlayerStart')
    deps=bpy.context.evaluated_depsgraph_get()
    evaluated_player=player.evaluated_get(deps) if player else None
    spawn=native(evaluated_player.matrix_world.translation) if player else Vector((0,1,0))
    yaw=player_yaw(evaluated_player) if player else 0
    visual=[o for o in scene.objects if o.type=='MESH' and o.get('nd_type') in ('visual','sky') and o.get('nd_export',True)]
    if scope=='SELECTED': visual=[o for o in visual if o.select_get()]
    if scope=='VISIBLE': visual=[o for o in visual if not o.hide_get() and not o.hide_viewport]
    if not visual: raise ValueError('No tagged visual meshes in chosen scope')
    import importlib.util
    from types import SimpleNamespace
    sky_path=Path(__file__).with_name('blender_vita_sky.py')
    sky_spec=importlib.util.spec_from_file_location('nd_export_sky',sky_path)
    sky_module=importlib.util.module_from_spec(sky_spec);sky_spec.loader.exec_module(sky_module)
    sky_visual=[o for o in visual if sky_module.is_sky_object(o)]
    visual=[o for o in visual if not sky_module.is_sky_object(o)]
    if bpy.data.filepath:sky_module.apply_native_bindings(sky_visual,Path(bpy.data.filepath).parent)
    owners={str(o.get('nd_level_id') or 'level') for o in visual}
    # Scenes made before the opacity preview still contain native material identities.
    # Attach their separate masks automatically; keep existing user alpha settings.
    alpha_manifest = Path(bpy.data.filepath).parent / 'transparency.json' if bpy.data.filepath else None
    if alpha_manifest and alpha_manifest.is_file():
        import importlib.util
        alpha_spec = importlib.util.spec_from_file_location('nd_export_alpha', Path(__file__).with_name('blender_material_alpha.py'))
        alpha_module = importlib.util.module_from_spec(alpha_spec)
        alpha_spec.loader.exec_module(alpha_module)
        alpha_report = alpha_module.apply_manifest(alpha_manifest, missing_only=True)
        if alpha_report['missing_images']:
            raise ValueError('Native opacity could not be resolved: ' + str(alpha_report))
        print('NATIVE OPACITY', alpha_report['materials'], 'materials restored;',
              len(alpha_report['ambiguous']), 'ambiguous materials left unchanged', flush=True)
    prop_lighting = None
    if color_layer == 'ND_StaticIrradiance':
        prop_lighting = repair_missing_prop_lighting([
            obj for obj in scene.objects if obj.get('nd_type') == 'visual'])
        print('PROP LIGHTING', len(prop_lighting['repaired']), 'repaired,',
              len(prop_lighting['unresolved']), 'unresolved (port approximation)', flush=True)
    collision=[o for o in scene.objects if o.type=='MESH' and (o.get('nd_type')=='collision' or o.get('collision'))
               and str(o.get('nd_level_id') or 'level') in owners and o.get('nd_export',True)]
    report={'output_directory':str(root),'vertex_stride':16,'color_layer':color_layer,'gain':gain,'levels':{},'unlit_objects':set(),
            'spawn':{'object':player.name if player else None,'position':list(spawn),'yaw':yaw,'fallback':player is None},
            'batch_mode':batch_mode,'max_polys':max_polys,'max_size':max_size,'min_size':min_size,'max_texture_size':max_texture_size,
            'clipped_color_corners':0,'alpha_materials':[],'material_settings':{},'texture_dimensions':{},'coordinate_system':'native Y up, metres',
            'position_quantization':{'step_metres':0.01,'grid':'shared_world','rounding':'nearest_even_before_origin_subtraction'}}
    sky_api=SimpleNamespace(native=native,albedo=albedo,uv_layer=uv_layer,export_texture=export_texture,safe_name=safe_name)
    report['sky']=sky_module.export_skies(root,sky_visual,deps,sky_api,report,max_sky_texture_size,str(scene.get('nd_vita_sky','')))
    print('SKY EXPORT',json.dumps(report['sky'],ensure_ascii=False),flush=True)
    report['prop_lighting'] = prop_lighting
    import importlib.util
    door_path=Path(__file__).with_name('blender_doors.py')
    if not door_path.exists():door_path=Path(r'D:\TLOUPS4\fervent-pascal\tlou_extractor\blender_doors.py')
    door_spec=importlib.util.spec_from_file_location('nd_export_doors',door_path)
    import sys
    package_root=door_path.parent.parent if (door_path.parent/'__init__.py').exists() else Path(r'D:\TLOUPS4\fervent-pascal')
    if str(package_root) not in sys.path:sys.path.insert(0,str(package_root))
    door_module=importlib.util.module_from_spec(door_spec)
    door_module.__package__='tlou_extractor'  # Its profile writer uses package-relative imports.
    door_spec.loader.exec_module(door_module)
    door_defs=door_module.definitions(scene);door_bindings={}
    cache={}; textures={}; level_files={}
    for owner in sorted(owners):
        instances=[]; triangles=bytearray(); col_objects=0;pending={};door_refs={}
        for obj in sorted([o for o in collision if str(o.get('nd_level_id') or 'level')==owner],key=lambda o:o.name):
            # Original collision topology: no decimation, hulls, or visual-mesh fallback.
            mesh=obj.data; mesh.calc_loop_triangles(); mirrored=obj.matrix_world.determinant()<0
            for tri in mesh.loop_triangles:
                verts=list(tri.vertices)
                if mirrored: verts[1],verts[2]=verts[2],verts[1]
                points=[native(obj.matrix_world@mesh.vertices[i].co) for i in verts]
                if (points[1]-points[0]).cross(points[2]-points[0]).length_squared<1e-20: continue
                triangles.extend(struct.pack('<9f',*(c for p in points for c in p)))
            col_objects+=1
        for obj in sorted([o for o in visual if str(o.get('nd_level_id') or 'level')==owner],key=lambda o:o.name):
            if obj.modifiers and any(m.type=='ARMATURE' for m in obj.modifiers):
                raise ValueError('Skinned object cannot be exported as static: '+obj.name)
            door_id=str(obj.get('nd_door_id',''))
            if door_id and door_id not in door_defs:raise ValueError('Missing door definition: '+door_id)
            evaluated=obj.evaluated_get(deps)
            mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=deps)
            try:
                mesh.calc_loop_triangles(); world=evaluated.matrix_world
                normals=world.to_3x3().inverted().transposed(); mirrored=world.determinant()<0
                groups={}
                for tri in mesh.loop_triangles: groups.setdefault(tri.material_index,[]).append(tri)
                for slot,tris in groups.items():
                    mat=evaluated.material_slots[slot].material if slot<len(evaluated.material_slots) else (mesh.materials[slot] if slot<len(mesh.materials) else None)
                    # Custom material properties may be stale on the evaluated ID.
                    mat=mat.original if mat else None
                    uv=uv_layer(mesh,mat); texture=export_texture(mat,root,cache,textures,report,max_texture_size)
                    corners=[]; low=None; high=None
                    def flush():
                        if not corners: return
                        data=np.array([(*p,*n,*t,*color) for p,n,t,color in corners],dtype=np.float32)
                        if batch_mode=='KD' and not obj.get('nd_batch_exempt',False) and not door_id: pending.setdefault(texture,[]).append(data)
                        else:
                            first=len(instances)
                            write_batch(data,texture,root,instances,gain,report)
                            if door_id:door_refs.setdefault(door_id,[]).extend(instances[first:])
                    for tri in tris:
                        loops=list(tri.loops)
                        if mirrored: loops[1],loops[2]=loops[2],loops[1]
                        points=[native(world@mesh.vertices[mesh.loops[i].vertex_index].co) for i in loops]
                        tl=Vector(tuple(min(p[i] for p in points) for i in range(3)))
                        th=Vector(tuple(max(p[i] for p in points) for i in range(3)))
                        if max(th-tl)>655: raise ValueError('Single triangle exceeds 655m: '+obj.name)
                        nl=tl if low is None else Vector(tuple(min(low[i],tl[i]) for i in range(3)))
                        nh=th if high is None else Vector(tuple(max(high[i],th[i]) for i in range(3)))
                        if corners and (max(nh-nl)>655 or len(corners)>=(max_polys*3 if batch_mode=='OBJECT' or obj.get('nd_batch_exempt',False) else 60000)):
                            flush(); corners=[]; nl,nh=tl,th
                        low,high=nl,nh
                        for index,p in zip(loops,points):
                            n=native((normals@mesh.corner_normals[index].vector).normalized())
                            tex=tuple(uv.data[index].uv) if uv else (0,0)
                            corners.append((p,n,tex,lighting(mesh,index,mat,obj,color_layer,cache,report)))
                    flush()
            finally: evaluated.to_mesh_clear()
        source_groups=sum(len(v) for v in pending.values())+len(instances)
        for texture in sorted(pending):
            blocks=pending[texture]
            data=np.concatenate(blocks).reshape(-1,3,12);blocks.clear()
            for batch in kd_batches(data,max_polys,max_size,min_size):
                write_batch(batch.reshape(-1,12),texture,root,instances,gain,report)
        pending.clear()
        instances.sort(key=lambda i:(i[4],i[3]))
        indices={id(instance):index for index,instance in enumerate(instances)}
        door_bindings[owner]={key:[indices[id(instance)] for instance in refs] for key,refs in door_refs.items()}
        filename='assets/levels/'+safe_name(owner)+'.bin'; destination=root/filename
        with destination.open('wb') as out:
            out.write(struct.pack('<4sIII4f',b'LVL5',len(instances),len(triangles)//36,0,*spawn,yaw)); out.write(triangles)
            for matrix,lo,hi,model,texture in instances:
                out.write(struct.pack('<22f',*matrix,*lo,*hi))
                for value in (model,texture):
                    raw=value.encode('utf-8'); out.write(struct.pack('<H',len(raw))); out.write(raw)
        level_files[owner]=filename
        report['levels'][owner]={'file':filename,'instances':len(instances),'source_groups':source_groups,'collision_objects':col_objects,'collision_triangles':len(triangles)//36}
        cache.clear()  # release full-resolution image float arrays between chunks
    if level_files:report['main_level']=combine_levels(root,level_files)
    else:
        (root/'level.bin').write_bytes(struct.pack('<4sIII4f',b'LVL5',0,0,0,*spawn,yaw))
        report['main_level']={'file':'level.bin','instances':0,'collision_triangles':0}
    report['doors']=door_module.write_sidecars(root,level_files,door_defs,door_bindings,{obj.name for obj in visual})
    report['unlit_objects']=sorted(report['unlit_objects'])
    (root/'assets/metadata/level_files.json').write_text(json.dumps(level_files,indent=2),encoding='utf-8')
    report['streaming']=export_native_streaming(root,level_files)
    write_material_settings(root,report['material_settings'])
    (root/'assets/metadata/vita_export_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('[Vita export]',json.dumps({'output_directory':str(root),'spawn':report['spawn'],'main_level':report['main_level'],'levels':report['levels'],'unlit_objects':len(report['unlit_objects']),
                                     'clipped_color_corners':report['clipped_color_corners']},ensure_ascii=False),flush=True)
    return report


class VITA_OT_export(bpy.types.Operator):
    bl_idname='nd.export_vita'; bl_label='Экспорт в TLOU Vita (LVL5 / 16 байт)'
    directory: StringProperty(subtype='DIR_PATH',default=EXPORT_BASE_DIR)
    scope: EnumProperty(items=[('ALL','Все чанки',''),('VISIBLE','Видимые чанки',''),('SELECTED','Выделенные объекты','')],default='ALL')
    color_layer: StringProperty(default='ND_StaticIrradiance',name='Атрибут света')
    gain: FloatProperty(default=1,min=0,max=16,name='Множитель света')
    batch_mode: EnumProperty(items=[('KD','Адаптивный KD-батчинг','Объединить геометрию с одной текстурой внутри чанка'),('OBJECT','По объектам','Сохранить границы объектов')],default='KD',name='Батчинг')
    max_polys: IntProperty(default=4500,min=1,max=20000,name='Треугольников на батч')
    max_size: FloatProperty(default=170,min=.1,max=655,name='Размер батча, м')
    min_size: FloatProperty(default=5,min=0,max=655,name='Минимальный разнос центров, м')
    max_texture_size: IntProperty(default=0,min=0,max=16384,name='Размер текстур (0 = исходный)')
    max_sky_texture_size: IntProperty(default=1024,min=64,max=4096,name='Размер текстур неба')
    def invoke(self,context,event):
        self.directory=EXPORT_BASE_DIR
        context.window_manager.fileselect_add(self); return {'RUNNING_MODAL'}
    def execute(self,context):
        try:
            if not self.directory: raise ValueError('Choose output folder')
            build=new_build_folder(self.directory)
            report=export_vita(build,self.scope,self.color_layer,self.gain,self.batch_mode,self.max_polys,self.max_size,self.min_size,self.max_texture_size,require_spawn=True,max_sky_texture_size=self.max_sky_texture_size)
            point=report['spawn']
            self.report({'INFO'},f"Сборка: {build}; PlayerStart: {point['object']} → {tuple(round(v,3) for v in point['position'])}")
            return {'FINISHED'}
        except Exception as error:
            import traceback
            traceback.print_exc(); self.report({'ERROR'},str(error)); return {'CANCELLED'}


class VITA_PT_export(bpy.types.Panel):
    bl_label='Экспорт уровня в движок'; bl_idname='VITA_PT_export'
    bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category='Vita'
    def draw(self,context):
        self.layout.prop(context.scene,'nd_vita_spawn',text='Маркер спавна')
        try:
            marker=resolve_spawn(context.scene)
            if marker:
                p=native(marker.matrix_world.translation)
                self.layout.label(text=f'{marker.name}: X {p.x:.2f}, Y {p.y:.2f}, Z {p.z:.2f}')
            else:self.layout.label(text='Маркер не найден',icon='ERROR')
        except ValueError as error:self.layout.label(text=str(error),icon='ERROR')
        self.layout.operator('nd.vita_player_start')
        self.layout.operator('nd.vita_mark_sky')
        self.layout.operator('nd.export_vita')
        self.layout.label(text='Свет в RGBA; оригинальная коллизия')


class VITA_OT_player_start(bpy.types.Operator):
    bl_idname='nd.vita_player_start';bl_label='Создать PlayerStart'
    def execute(self,context):
        if any(spawn_candidate(o) for o in context.scene.objects):
            self.report({'INFO'},'PlayerStart уже существует');return {'CANCELLED'}
        bpy.ops.object.empty_add(type='SINGLE_ARROW',location=context.scene.cursor.location)
        obj=context.object;obj.name='PlayerStart';obj['nd_type']='player_start';obj['nd_export']=False
        context.scene.nd_vita_spawn=obj
        obj.rotation_euler=(math.radians(-90),0,0)
        return {'FINISHED'}


class VITA_OT_mark_sky(bpy.types.Operator):
    bl_idname='nd.vita_mark_sky';bl_label='Выделенные меши → небо'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        meshes=[o for o in context.selected_objects if o.type=='MESH']
        if not meshes:return {'CANCELLED'}
        group=context.active_object.name if context.active_object else 'sky'
        for obj in meshes:
            obj['nd_type']='sky';obj['nd_render_pass']='SKY';obj['nd_sky_group']=group;obj['nd_export']=True
        self.report({'INFO'},f'Небо: {len(meshes)} мешей → один draw call; без KD-разбиения')
        return {'FINISHED'}

CLASSES=(VITA_OT_export,VITA_OT_player_start,VITA_OT_mark_sky,VITA_PT_export)

def register():
    saved_obj=bpy.context.scene.get('nd_vita_spawn_object')
    saved=bpy.context.scene.get('nd_vita_spawn_name','')
    bpy.types.Scene.nd_vita_spawn=PointerProperty(type=bpy.types.Object,name='Маркер спавна',update=spawn_changed)
    if saved_obj and saved_obj.name in bpy.context.scene.objects:bpy.context.scene.nd_vita_spawn=saved_obj
    elif saved and bpy.context.scene.objects.get(saved):bpy.context.scene.nd_vita_spawn=bpy.context.scene.objects[saved]
    elif not saved:
        candidates=[o for o in bpy.context.scene.objects if spawn_candidate(o)]
        if len(candidates)==1:bpy.context.scene.nd_vita_spawn=candidates[0]
    for cls in CLASSES:
        old=getattr(bpy.types,cls.__name__,None)
        if issubclass(cls,bpy.types.Operator):
            category,operation=cls.bl_idname.split('.')
            old=getattr(bpy.types,category.upper()+'_OT_'+operation,None) or old
        if old: bpy.utils.unregister_class(old)
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        if getattr(cls,'is_registered',False): bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene,'nd_vita_spawn'):del bpy.types.Scene.nd_vita_spawn


if __name__=='__main__': register()
