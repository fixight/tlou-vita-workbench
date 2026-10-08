import sys, struct, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from tlou_extractor.blender_vita_export import export_vita, register, unregister, lighting, kd_batches, resize_rgba
import numpy as np
from mathutils import Vector

bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
mesh=bpy.data.meshes.new('tri')
mesh.from_pydata([(0,0,0),(2,0,0),(0,2,0)],[],[(0,1,2)])
uv=mesh.uv_layers.new(name='UVMap')
for entry,coord in zip(uv.data,[(0,0),(2,0),(0,2)]): entry.uv=coord
attr=mesh.color_attributes.new(name='ND_StaticIrradiance',type='FLOAT_COLOR',domain='CORNER')
for entry in attr.data: entry.color=(.25,.5,1,1)
obj=bpy.data.objects.new('visual',mesh); bpy.context.scene.collection.objects.link(obj)
obj['nd_type']='visual'; obj['nd_level_id']='test'
obj.location=(10000,3,4); obj.scale=(-1,2,1)
bpy.context.view_layer.update()
col=bpy.data.objects.new('native collision',mesh.copy()); bpy.context.scene.collection.objects.link(col)
col['nd_type']='collision';col['nd_level_id']='test';col.matrix_world=obj.matrix_world.copy();col.hide_set(True)
bpy.context.view_layer.update()
folder=Path(tempfile.mkdtemp(prefix='vita-export-test-'))
report=export_vita(folder)
assert report['levels']['test']['collision_triangles']==1
assert report['levels']['test']['collision_objects']==1
data=(folder/'level.bin').read_bytes()
magic,instances,triangles,lights,*spawn=struct.unpack_from('<4sIII4f',data)
assert (magic,instances,triangles,lights)==(b'LVL5',1,1,0)
offset=32+triangles*36
matrix=struct.unpack_from('<16f',data,offset); offset+=88
length=struct.unpack_from('<H',data,offset)[0];offset+=2
model=data[offset:offset+length].decode();offset+=length
length=struct.unpack_from('<H',data,offset)[0];offset+=2+length
assert offset==len(data)
raw=(folder/model.replace('app0:/','')).read_bytes()
assert struct.unpack_from('<I',raw)[0]==3 and len(raw)==4+3*16
corners=[struct.unpack_from('<4B3h2e2b',raw,4+i*16) for i in range(3)]
assert corners[0][:4]==(64,128,255,255)
assert {tuple(c[7:9]) for c in corners}=={(0,0),(2,0),(0,2)}
world=[tuple(c[4+i]*.01+matrix[12+i] for i in range(3)) for c in corners]
assert set(world)=={(10000.,4.,-3.),(9998.,4.,-3.),(10000.,4.,-7.)}, world
assert all(c[9:]==(0,127) for c in corners), corners
collision=struct.unpack_from('<9f',data,32)
assert all(any(max(abs(collision[i+k]-p[k]) for k in range(3))<1e-5 for p in world) for i in (0,3,6))
# Atlas lighting must replace (not multiply by) the fallback vertex attribute.
mat=bpy.data.materials.new('native atlas');mat.use_nodes=True
for key,value in [('g_tLmBaseColor',(.1,.2,.3,1)),('g_tLmLightColor',(.2,.3,.4,1)),('g_tLmLightDir',(0,0,1,1))]:
    image=bpy.data.images.new(key,width=1,height=1,float_buffer=True)
    image.colorspace_settings.name='Non-Color';image.pixels[:]=value
    node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=image;node.label=key
obj['nd_static_lighting_mode']='directional_atlas_candidate'
lm=mesh.uv_layers.new(name='ND_LightingUV')
for entry in lm.data:entry.uv=(.5,.5)
result=lighting(mesh,0,mat,obj,'ND_StaticIrradiance',{}, {'unlit_objects':set()})
# Native +Z converts to Blender -Y, perpendicular to the plane, so only base remains.
assert all(abs(a-b)<1e-6 for a,b in zip(result,(.1,.2,.3,1))), result
for node in mat.node_tree.nodes:
    if node.label=='g_tLmLightDir':node.image.pixels[:]=(0,1,0,1)
result=lighting(mesh,0,mat,obj,'ND_StaticIrradiance',{}, {'unlit_objects':set()})
assert all(abs(a-b)<1e-6 for a,b in zip(result,(.3,.5,.7,1))), result
obj['nd_static_lighting_mode']='vertex_basis_candidate'
mesh.color_attributes.remove(attr)
legacy=mesh.color_attributes.new(name='Col',type='FLOAT_COLOR',domain='POINT')
for entry in legacy.data:entry.color=(.2,.4,.6,1)
assert tuple(round(x,4) for x in lighting(mesh,0,None,obj,'ND_StaticIrradiance',{}, {'unlit_objects':set()}))==(.2,.4,.6,1)
coincident=np.zeros((11,3,12),dtype=np.float32)
leaves=list(kd_batches(coincident,max_polys=4))
assert sum(len(b) for b in leaves)==11 and max(len(b) for b in leaves)<=4
large=np.zeros((2,3,12),dtype=np.float32);large[1,:,:3]=1000
assert len(list(kd_batches(large)))==2
image=np.zeros((128,64,4),dtype=np.float32);image[:,:,:3]=(.2,.4,.6);image[:,:,3]=1
scaled=resize_rgba(image,64)
assert scaled.shape==(64,32,4) and np.allclose(scaled[0,0],(.2,.4,.6,1))
# Separate small triangles at opposite ends of a kilometre must split into safe local meshes.
wide=bpy.data.meshes.new('wide')
wide.from_pydata([(0,0,0),(1,0,0),(0,1,0),(1000,0,0),(1001,0,0),(1000,1,0)],[],[(0,1,2),(3,4,5)])
wide_obj=bpy.data.objects.new('wide',wide);bpy.context.scene.collection.objects.link(wide_obj)
wide_obj['nd_type']='visual';wide_obj['nd_level_id']='wide'
report=export_vita(folder/'wide')
assert report['levels']['wide']['instances']==2
main=struct.unpack_from('<4sIII4f',(folder/'wide'/'level.bin').read_bytes())
assert main[:4]==(b'LVL5',3,1,0)
assert report['main_level']['instances']==3
assert {p.name for p in (folder/'wide').iterdir()}=={'level.bin','assets'}
assert (folder/'wide'/'assets/models').is_dir() and (folder/'wide'/'assets/textures').is_dir()
props=[]
for name,location,scale,angle in [('prop A',(0,0,0),(1,1,1),0),('prop B',(20,0,0),(2,1,1),1.5707963267948966)]:
    prop=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(prop)
    prop['nd_type']='visual';prop['nd_level_id']='props';prop.location=location;prop.scale=scale;prop.rotation_euler.z=angle
    props.append(prop)
for candidate in bpy.context.scene.objects:candidate.select_set(candidate in props)
bpy.context.view_layer.update()
report=export_vita(folder/'props',scope='SELECTED')
assert report['levels']['props']['instances']==1
data=(folder/'props'/'level.bin').read_bytes()
matrix=struct.unpack_from('<16f',data,32)
offset=32+88;length=struct.unpack_from('<H',data,offset)[0];offset+=2
path=data[offset:offset+length].decode().replace('app0:/','')
raw=(folder/'props'/path).read_bytes()
assert struct.unpack_from('<I',raw)[0]==6
reconstructed=set()
for i in range(6):
    v=struct.unpack_from('<4B3h2e2b',raw,4+i*16)
    reconstructed.add(tuple(round(v[4+k]*.01+matrix[12+k],4) for k in range(3)))
assert reconstructed=={(0.,0.,0.),(2.,0.,0.),(0.,0.,-2.),(20.,0.,0.),(20.,0.,-4.),(18.,0.,0.)}, reconstructed
register();register()
assert bpy.ops.nd.vita_player_start()=={'FINISHED'}
start=bpy.context.object;start.location=(1,2,3);start.rotation_euler.z=.5
props[1]['nd_batch_exempt']=True
for candidate in bpy.context.scene.objects:candidate.select_set(candidate in props)
bpy.context.view_layer.update()
report=export_vita(folder/'exempt',scope='SELECTED')
assert report['levels']['props']['instances']==2
header=struct.unpack_from('<4sIII4f',(folder/'exempt'/'level.bin').read_bytes())
assert header[4:7]==(1,3,-2) and abs(header[7]-28.64788975)<1e-4,header
start.name='My custom spawn'
register()
assert bpy.context.scene.nd_vita_spawn==start
parent=bpy.data.objects.new('Spawn parent',None);bpy.context.scene.collection.objects.link(parent)
parent.location=(10,20,30);start.parent=parent
report=export_vita(folder/'parented',scope='SELECTED',require_spawn=True)
assert report['spawn']['position']==[11,33,-22], report['spawn']
assert report['spawn']['object']=='My custom spawn' and not report['spawn']['fallback']
header=struct.unpack_from('<4sIII4f',(folder/'parented'/'level.bin').read_bytes())
assert header[4:7]==(11,33,-22)
start.name='PlayerStart';del start['nd_type']
bpy.context.scene.nd_vita_spawn=None
register()
assert bpy.context.scene.nd_vita_spawn==start, 'Old untagged PlayerStart must auto-bind'
report=export_vita(folder/'untagged',scope='SELECTED',require_spawn=True)
assert report['spawn']['position']==[11,33,-22] and report['spawn']['object']=='PlayerStart'
unregister();register()
print('VITA ABI, world transform, UV seams, corner/atlas/Col light, mirrored normal, hidden collision, strict KD budgets, linked props, texture resize, registration: PASS',folder)
