"""One sky mesh + one RGBA atlas, independent of the world's centimetre grid.

Native sky meshes are recognized by their source path. Custom meshes can use
nd_render_pass='SKY', nd_sky_group and an optional native-Y-up nd_sky_origin.
The descriptor is SKY1: step, two uint16 UTF-8 paths, legacy mesh count/paths.
"""
import hashlib,json,math,struct
from pathlib import Path
import numpy as np


def is_sky_object(obj):
    if obj.get('nd_render_pass')=='WORLD':return False
    return obj.get('nd_type')=='sky' or obj.get('nd_render_pass')=='SKY' or '/levels/sky/domes/' in obj.name.replace('\\','/').lower()


def pack_positions(points):
    points=np.asarray(points,dtype=np.float64)
    if not np.isfinite(points).all():raise ValueError('Non-finite sky position')
    extent=float(np.abs(points).max())
    if extent<=0:raise ValueError('Sky has no extent')
    step=extent/32760.0
    packed=np.rint(points/step).astype('<i2')
    return packed,step


def split_uv_seam(points,uv):
    """Split generated longitude UVs at the panorama seam without extra draws."""
    vertices=[np.array((*p,*t),dtype=np.float64) for p,t in zip(points,uv)]
    if max(v[3] for v in vertices)-min(v[3] for v in vertices)<=.5:
        return [(points,uv)]
    for v in vertices:
        if v[3]<.5:v[3]+=1
    def clip(keep_left):
        result=[]
        for a,b in zip(vertices,vertices[1:]+vertices[:1]):
            inside_a=a[3]<=1 if keep_left else a[3]>=1
            inside_b=b[3]<=1 if keep_left else b[3]>=1
            if inside_a:result.append(a.copy())
            if inside_a!=inside_b:
                crossing=a+(b-a)*((1-a[3])/(b[3]-a[3]));crossing[3]=1;result.append(crossing)
        if not keep_left:
            for v in result:v[3]-=1
        return [(np.array([result[0][:3],result[i][:3],result[i+1][:3]]),
                 np.array([result[0][3:],result[i][3:],result[i+1][3:]])) for i in range(1,len(result)-1)]
    return clip(True)+clip(False)


def make_atlas(images):
    """Vertical shelf, repeated two-pixel borders; preserve alpha for sky overlays."""
    padding=2
    def power2(v):return 1<<(v-1).bit_length()
    width=power2(max(a.shape[1]+2*padding for a in images))
    height=power2(sum(a.shape[0]+2*padding for a in images))
    if max(width,height)>8192:raise ValueError('Sky atlas exceeds 8192 pixels; reduce sky texture size')
    atlas=np.zeros((height,width,4),dtype=np.uint8);rects=[];y=0
    for a in images:
        h,w=a.shape[:2];border=np.pad(a,((padding,padding),(padding,padding),(0,0)),mode='edge')
        atlas[y:y+h+2*padding,:w+2*padding]=border
        # UV 0/1 samples the boundary between the edge texel and its repeated border.
        rects.append((padding/width,(y+padding)/height,w/width,h/height));y+=h+2*padding
    return atlas,rects


def descriptor(step,mesh,texture,legacy=()):
    result=bytearray(struct.pack('<4sf',b'SKY1',step))
    for value in (mesh,texture):
        raw=value.encode('utf-8');result+=struct.pack('<H',len(raw))+raw
    result+=struct.pack('<I',len(legacy))
    for value in legacy:
        raw=value.encode('utf-8');result+=struct.pack('<H',len(raw))+raw
    return bytes(result)


def apply_native_bindings(objects,folder):
    """Only explicit native roles; never treat an unconnected normal/noise node as albedo."""
    import bpy
    manifest=Path(folder)/'sky_materials.json'
    if not manifest.exists():return []
    bindings=json.loads(manifest.read_text(encoding='utf-8'));restored=[]
    for obj in objects:
        if not is_sky_object(obj):continue
        for slot in obj.material_slots:
            mat=slot.material
            if not mat or not mat.use_nodes:continue
            shader=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
            if not shader or shader.inputs['Base Color'].is_linked:continue
            source=Path(mat.get('nd_material_source','').replace('\\','/')).name
            entry=bindings.get(source,{})
            role='moon' if 'moon' in mat.name.lower() else 'dome'
            if not entry.get(role):continue
            image=bpy.data.images.load(entry[role],check_existing=True)
            node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
            mat.node_tree.links.new(node.outputs['Color'],shader.inputs['Base Color'])
            if role=='moon' and entry.get('moon_mask'):
                mask=bpy.data.images.load(entry['moon_mask'],check_existing=True)
                mask.colorspace_settings.name='Non-Color'
                mat['nd_transparency_image']=mask.name;mat['nd_alpha_mode']='BLEND'
            mat.update_tag()
            restored.append(mat.name)
    return restored


def export_skies(root,objects,deps,exporter,report,texture_limit=1024,default_group=''):
    """Keep sky triangles outside KD batching, collision, lighting and world culling."""
    from mathutils import Vector
    objects=[o for o in objects if is_sky_object(o)]
    if not objects:return {'variants':{},'default':None,'warnings':[]}
    groups={};warnings=[]
    for obj in objects:
        group=str(obj.get('nd_sky_group') or obj.get('nd_level_id') or 'sky')
        groups.setdefault(group,[]).append(obj)
    variants={}
    for group,members in sorted(groups.items()):
        # Largest mesh defines the dome centre. Planes retain their position relative to it.
        dome=max(members,key=lambda o:len(o.data.vertices))
        bounds=np.array([tuple(exporter.native(dome.matrix_world@Vector(c))) for c in dome.bound_box])
        lo,hi=bounds.min(axis=0),bounds.max(axis=0);origin=(lo+hi)*.5
        hemisphere=hi[1]-lo[1]<.75*max(hi[0]-lo[0],hi[2]-lo[2])
        if hemisphere:origin[1]=lo[1]
        if dome.get('nd_sky_origin') is not None:origin=np.array(dome['nd_sky_origin'],dtype=np.float64)
        if len(dome.data.vertices)<8 and not dome.get('nd_sky_origin'):
            warnings.append({'group':group,'reason':'Standalone sky plane has no dome or explicit origin; native runtime placement is required'})
            continue
        images=[];image_indices={};corners=[];material_paths=[]
        # Background first; overlay planes follow in the same draw call.
        for obj in sorted(members,key=lambda o:(o!=dome,int(o.get('nd_sky_order',0)),o.name)):
            evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=deps)
            try:
                mesh.calc_loop_triangles()
                for tri in mesh.loop_triangles:
                    slot=tri.material_index;mat=evaluated.material_slots[slot].material if slot<len(evaluated.material_slots) else None
                    # Nodes are evaluated for geometry; alpha metadata belongs to the original ID.
                    mat=mat.original if mat else None
                    if not exporter.albedo(mat):
                        warnings.append({'object':obj.name,'reason':'Sky material has no albedo binding; export uses its explicit base color'})
                    texture=exporter.export_texture(mat,root,{}, {},report,texture_limit)
                    if texture not in image_indices:
                        payload=(root/texture.removeprefix('app0:/')).read_bytes();w,h,size=struct.unpack_from('<III',payload)
                        assert size==w*h*4 and len(payload)==12+size
                        image_indices[texture]=len(images);images.append(np.frombuffer(payload,dtype=np.uint8,offset=12).reshape(h,w,4).copy());material_paths.append(texture)
                    uv=exporter.uv_layer(mesh,mat)
                    points=np.array([tuple(exporter.native(evaluated.matrix_world@mesh.vertices[mesh.loops[i].vertex_index].co)) for i in tri.loops])-origin
                    if uv:tex=np.array([tuple(uv.data[i].uv) for i in tri.loops]);parts=[(points,tex)]
                    else:
                        length=np.linalg.norm(points,axis=1)
                        if min(length)<1e-6:raise ValueError('Sky vertex lies at the camera origin: '+obj.name)
                        direction=points/length[:,None]
                        u=np.arctan2(direction[:,0],-direction[:,2])/(2*math.pi)+.5
                        pole=np.abs(direction[:,1])>.999999
                        for i in np.flatnonzero(pole):
                            other=u[~pole].copy()
                            if len(other) and np.ptp(other)>.5:other[other<.5]+=1
                            u[i]=np.mean(other)%1 if len(other) else .5
                        v=np.arcsin(np.clip(direction[:,1],-1,1))/(math.pi/2 if hemisphere else math.pi)+(0 if hemisphere else .5)
                        parts=split_uv_seam(points,np.column_stack((u,v)))
                    for p,t in parts:
                        if not np.isfinite(t).all() or t.min()<-1e-5 or t.max()>1.00001:
                            raise ValueError('Sky atlas requires UV in [0,1]: '+obj.name)
                        for point,texcoord in zip(p,t):corners.append((point,np.clip(texcoord,0,1),image_indices[texture]))
            finally:evaluated.to_mesh_clear()
        atlas,rects=make_atlas(images)
        positions,step=pack_positions([c[0] for c in corners])
        mesh_payload=bytearray(struct.pack('<I',len(corners)))
        for xyz,(_,uv,index) in zip(positions,corners):
            x,y,w,h=rects[index];mesh_payload+=struct.pack('<4B3h2e2b',255,255,255,255,*xyz,x+uv[0]*w,y+uv[1]*h,0,0)
        tex_payload=struct.pack('<III',atlas.shape[1],atlas.shape[0],atlas.nbytes)+atlas.tobytes()
        mesh_name=hashlib.sha256(mesh_payload).hexdigest()[:24]+'.bin';tex_name=hashlib.sha256(tex_payload).hexdigest()[:24]+'.bin'
        (root/'assets/models'/mesh_name).write_bytes(mesh_payload);(root/'assets/textures'/tex_name).write_bytes(tex_payload)
        mesh_path='app0:/assets/models/'+mesh_name;texture_path='app0:/assets/textures/'+tex_name
        filename='assets/metadata/sky_'+exporter.safe_name(group)+'.bin'
        (root/filename).write_bytes(descriptor(step,mesh_path,texture_path))
        variants[group]={'file':filename,'mesh':mesh_path,'texture':texture_path,'objects':[o.name for o in members],
                         'triangles':len(corners)//3,'draw_calls':1,'position_step_metres':step,'max_position_error_metres':step*.5,
                         'atlas_dimensions':[atlas.shape[1],atlas.shape[0]],'atlas_bytes':atlas.nbytes,'origin_native':origin.tolist(),
                         'material_textures':material_paths}
    if default_group and default_group not in variants:raise ValueError('Selected sky variant is not exported: '+default_group)
    chosen=default_group or next(iter(variants),'')
    if chosen:(root/'assets/metadata/sky.bin').write_bytes((root/variants[chosen]['file']).read_bytes())
    return {'variants':variants,'default':chosen or None,'warnings':list({json.dumps(w,sort_keys=True):w for w in warnings}.values())}
