import sys,json,hashlib
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,r'D:\TLOUPS4\fervent-pascal')
from tlou_extractor.blender_prop_lighting import repair_prop_lighting
scene=bpy.context.scene
before={o.name:(len(o.data.vertices),len(o.data.polygons),o.hide_get(),o.hide_render) for o in scene.objects if o.type=='MESH'}
def hashes():
 result={}
 for o in scene.objects:
  if o.type=='MESH' and o.data.color_attributes.get('ND_StaticIrradiance'):
   a=o.data.color_attributes['ND_StaticIrradiance'];v=np.empty(len(a.data)*4,dtype='f4');a.data.foreach_get('color',v);result[o.name]=hashlib.sha256(v.tobytes()).hexdigest()
 return result
native_hashes=hashes()
report=repair_prop_lighting()
assert before=={o.name:(len(o.data.vertices),len(o.data.polygons),o.hide_get(),o.hide_render) for o in scene.objects if o.type=='MESH'}
after_hashes=hashes()
assert all(after_hashes[name]==digest for name,digest in native_hashes.items())
sofa=next(o for o in scene.objects if o.name.startswith('simple-actor-3167_hom-couch|'))
assert sofa.get('nd_static_lighting_mode')=='surface_sampled_port_approximation'
colors=np.array([tuple(v.color) for v in sofa.data.color_attributes['ND_StaticIrradiance'].data]);assert colors[:,:3].mean()<.2
report['sofa_rgb_mean']=colors[:,:3].mean(0).tolist();report['geometry_visibility_native_colors_preserved']=True
# Fresh add-on source embedded for next Text Editor Run Script.
for name in ['blender_vita_export.py','blender_prop_lighting.py']:
 text=bpy.data.texts.get(name) or bpy.data.texts.new(name);text.clear();text.write((Path(r'D:\TLOUPS4\fervent-pascal\tlou_extractor')/name).read_text(encoding='utf-8'));text.use_fake_user=True
from tlou_extractor.blender_material_alpha import toggle
toggle(scene)
output=Path(r'D:\TLOUPS4\AustinStaticLighting\scene_props_lighting.blend')
for image in bpy.data.images:
 if image.filepath: image.filepath=bpy.path.abspath(image.filepath)
bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=True,relative_remap=False)
(output.parent/'props_lighting_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('PROP_LIGHTING_PASS',len(report['repaired']),'repaired',len(report['unresolved']),'unresolved','SOFA',report['sofa_rgb_mean'],flush=True)
