"""Build only sky resources from an existing scene; leave the .blend untouched."""
import bpy,json,sys,struct
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor import blender_vita_export as exporter
from tlou_extractor import blender_vita_sky as sky
args=sys.argv[sys.argv.index('--')+1:];root=Path(args[0])
for name in ('models','textures','metadata'):(root/'assets'/name).mkdir(parents=True,exist_ok=True)
objects=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.get('nd_export',True) and sky.is_sky_object(o)]
restored=sky.apply_native_bindings(objects,Path(bpy.data.filepath).parent)
report={'alpha_materials':[],'material_settings':{},'texture_dimensions':{}}
report['sky']=sky.export_skies(root,objects,bpy.context.evaluated_depsgraph_get(),exporter,report)
keys=set()
for obj in objects:
 mesh=obj.data;mesh.calc_loop_triangles()
 for tri in mesh.loop_triangles:
  points=np.array([tuple(exporter.native(obj.matrix_world@mesh.vertices[i].co)) for i in tri.vertices],dtype=np.float32)
  xyz=np.rint(points.astype(np.float64)*100).astype(np.int64)
  keys.add(b''.join(sorted(struct.pack('<3q',*p) for p in xyz)).hex())
(root/'legacy_sky_triangles.json').write_text(json.dumps(sorted(keys)))
(root/'sky_export_report.json').write_text(json.dumps(report,indent=2))
print('SKY BUILT',json.dumps(report['sky']), 'LEGACY TRIANGLES',len(keys),'RESTORED',restored,flush=True)
