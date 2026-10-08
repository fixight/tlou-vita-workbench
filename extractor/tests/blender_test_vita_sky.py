import bpy,sys,tempfile,struct,zlib
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor import blender_vita_export as ex
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_cube_add(location=(1,2,3));cube=bpy.context.object
cube['nd_type']='visual';cube['nd_level_id']='test'
bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=10000)
dome=bpy.context.object;dome['nd_type']='sky';dome['nd_level_id']='test-sky'
with tempfile.TemporaryDirectory() as temp:
 def png(path,pixels):
  def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
  payload=bytes([0])+pixels[:8]+bytes([0])+pixels[8:]
  path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',2,2,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(payload))+chunk(b'IEND',b''))
 color=Path(temp)/'color.png';mask=Path(temp)/'mask.png'
 png(color,bytes([16,32,64,255])*4)
 png(mask,bytes([0,0,0,255,255,255,255,255])*2)
 mat=bpy.data.materials.new('sky test');mat.use_nodes=True
 image=bpy.data.images.load(str(color));node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
 mat.node_tree.links.new(node.outputs['Color'],mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
 dome.data.materials.append(mat)
 # Populate evaluated material before adding native metadata: reads must use the original ID.
 deps=bpy.context.evaluated_depsgraph_get();dome.evaluated_get(deps)
 opacity=bpy.data.images.load(str(mask));opacity.colorspace_settings.name='Non-Color'
 mat['nd_alpha_mode']='BLEND';mat['nd_transparency_image']=opacity.name
 report=ex.export_vita(temp,color_layer='Col',max_polys=1,max_size=1)
 sky=report['sky']['variants']['test-sky']
 texture=sky['material_textures'][0];payload=(Path(temp)/texture.removeprefix('app0:/')).read_bytes()
 w,h,size=struct.unpack_from('<III',payload);pixels=np.frombuffer(payload,np.uint8,offset=12).reshape(h,w,4)
 assert np.all(pixels[:,:,:3]==[16,32,64]),pixels
 assert pixels[:,:,3].min()==0 and pixels[:,:,3].max()==255
 assert report['material_settings'][texture]['alpha_mode']=='BLEND'
 assert sky['draw_calls']==1 and sky['triangles']>1
 assert report['main_level']['instances']>=1
 assert sum(r['source_groups'] for r in report['levels'].values())==1
 assert sky['position_step_metres']>.01
 bpy.ops.object.select_all(action='DESELECT');dome.select_set(True)
 report=ex.export_vita(Path(temp)/'only_sky',scope='SELECTED',color_layer='Col')
 assert report['main_level']['instances']==0 and report['sky']['default']=='test-sky'
print('BLENDER SKY INTEGRATION PASSED',flush=True)
