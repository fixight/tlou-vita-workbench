import bpy,sys,importlib.util,json
from pathlib import Path
from mathutils import Vector
root=Path(sys.argv[sys.argv.index('--')+1]);out=Path('D:/TLOUPS4/AustinStaticLighting')
spec=importlib.util.spec_from_file_location('nd_alpha',root/'tlou_extractor/blender_material_alpha.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add(size=2)
obj=bpy.context.object;mat=bpy.data.materials.new('test_baked_leaf');mat.use_nodes=True;obj.data.materials.append(mat)
nodes=mat.node_tree.nodes;links=mat.node_tree.links
output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
emission=nodes.new('ShaderNodeEmission');emission.inputs['Color'].default_value=(1,0,0,1)
links.new(emission.outputs[0],output.inputs['Surface'])
# Use real BC4 map, not color texture's constant alpha.
assert m.attach(mat,out/'opacity_masks/opacity_a1d0d8e29dc316ac.png','a1d0d8e29dc316ac')
count=len(nodes);assert m.configure(mat) and len(nodes)==count
mix=next(n for n in nodes if n.get('nd_opacity_role')=='mix')
assert mix.inputs[2].links[0].from_node==emission
assert mix.inputs[0].links[0].from_node.get('nd_opacity_role')=='scale'
assert m.configure(mat,False) and not mix.inputs[0].links and mix.inputs[0].default_value==1
mat['nd_alpha_mode']='MASK';assert m.configure(mat,True)
assert mix.inputs[0].links[0].from_node.get('nd_opacity_role')=='cutoff'
mat['nd_alpha_mode']='BLEND';m.configure(mat)
# A lighting rebuild must keep the new baked shader behind the opacity mix.
emission2=nodes.new('ShaderNodeEmission');emission2.inputs['Color'].default_value=(1,0,0,1)
links.new(emission2.outputs[0],output.inputs['Surface']);m.configure(mat)
assert mix.inputs[2].links[0].from_node==emission2
s=bpy.context.scene;s.world.use_nodes=True
background=s.world.node_tree.nodes.get('Background');background.inputs['Color'].default_value=(0,0,1,1)
s.render.engine='CYCLES';s.cycles.samples=1;s.cycles.max_bounces=0;s.cycles.transparent_max_bounces=16
bpy.ops.object.camera_add(location=(0,0,3));camera=bpy.context.object;camera.data.type='ORTHO';camera.data.ortho_scale=2
s.camera=camera;s.render.resolution_x=128;s.render.resolution_y=128;s.render.resolution_percentage=100
s.view_settings.view_transform='Standard';s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGBA'
s.render.filepath=str(out/'leaf_opacity_render_test.png');bpy.ops.render.render(write_still=True)
print('ALPHA NODE TESTS AND RENDER PASSED',flush=True)

meta=bpy.data.objects.new('TLOU_STREAMING_DATA',None);s.collection.objects.link(meta)
meta['nd_type']='streaming_metadata';meta['nd_streaming_json']=json.dumps({'regions':[]})
obj['nd_type']='visual';obj['nd_level_id']='hom-house-interior'
text=bpy.data.texts.new('blender_material_alpha.py');text.write((root/'tlou_extractor/blender_material_alpha.py').read_text(encoding='utf-8'))
namespace={'__name__':'nd_editor_test'}
exec(compile((root/'tlou_extractor/blender_streaming_tools.py').read_text(encoding='utf-8'),'blender_streaming_tools.py','exec'),namespace)
namespace['register']()
s.nd_alpha_preview=False;assert not mix.inputs[0].links
s.nd_alpha_preview=True;assert mix.inputs[0].links
bpy.context.view_layer.objects.active=obj
bpy.ops.nd.alpha_mode(mode='MASK');assert mat['nd_alpha_mode']=='MASK'
assert mix.inputs[0].links[0].from_node.get('nd_opacity_role')=='cutoff'
mat['nd_alpha_strength']=.75;bpy.ops.nd.alpha_mode(mode='KEEP')
scale=next(n for n in nodes if n.get('nd_opacity_role')=='scale')
assert scale.inputs[1].default_value==.75
namespace['register']()
print('EMBEDDED UI TOGGLE AND MATERIAL CONTROLS PASSED',flush=True)
