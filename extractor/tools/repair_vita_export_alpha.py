"""Repair opacity in an existing export without changing geometry, spawn or collision.
Run in Blender with the source scene open; -- export_root staging_root.
"""
import bpy,sys,json,hashlib,struct
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor.blender_vita_export import export_texture,write_material_settings,uv_layer,native
from tlou_extractor.blender_material_alpha import apply_manifest
args=sys.argv[sys.argv.index('--')+1:]
root,stage=map(Path,args[:2])
report=json.loads((root/'assets/metadata/vita_export_report.json').read_text())
(stage/'assets/textures').mkdir(parents=True,exist_ok=True)
(stage/'assets/metadata').mkdir(parents=True,exist_ok=True)
names=set(report['texture_dimensions'])
mats=[m for m in bpy.data.materials if m.name in names]
assert len(mats)==len(names), (len(mats),len(names))
# Reconstruct the legacy texture IDs before adding the masks.
legacy={}; oldreport={'alpha_materials':[],'material_settings':{},'texture_dimensions':{}}
for mat in mats:
 path=export_texture(mat,stage,{}, {},oldreport,report['max_texture_size'])
 payload=(stage/path.removeprefix('app0:/')).read_bytes()
 legacy[mat.name]='app0:/assets/textures/'+hashlib.sha256(payload).hexdigest()[:24]+'.bin'
mask_report=apply_manifest(Path(bpy.data.filepath).parent/'transparency.json',missing_only=True)
print('MASKS RESTORED', mask_report['materials'], 'ambiguous',len(mask_report['ambiguous']),flush=True)
(stage/'mask_report.json').write_text(json.dumps(mask_report,indent=2))
assert not mask_report['missing_images']
newreport={'alpha_materials':[],'material_settings':{},'texture_dimensions':{}}
variants={}; matches=0
for mat in mats:
 old=legacy[mat.name]
 if not (root/old.removeprefix('app0:/')).exists(): continue
 matches+=1
 new=export_texture(mat,stage,{}, {},newreport,report['max_texture_size'])
 variants.setdefault(old,set()).add(new)
conflicts={k:sorted(v) for k,v in variants.items() if len(v)>1}
print('MATCHES',matches,'TEXTURES',len(variants),'CONFLICTS',len(conflicts),flush=True)
(stage/'repair_plan.json').write_text(json.dumps({'variants':{k:sorted(v) for k,v in variants.items()},'conflicts':conflicts,'materials':newreport['material_settings'],'alpha_materials':newreport['alpha_materials']},indent=2))
write_material_settings(stage,newreport['material_settings'])
# A legacy KD batch could merge the same albedo with different opacity masks.
# Identify its original triangles by world centimetres and half-float UVs.
lookup={}
deps=bpy.context.evaluated_depsgraph_get()
for obj in bpy.context.scene.objects:
    if obj.type!='MESH': continue
    if not any(slot.material and legacy.get(slot.material.name) in conflicts for slot in obj.material_slots): continue
    evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=deps)
    try:
        mesh.calc_loop_triangles()
        for tri in mesh.loop_triangles:
            mat=evaluated.material_slots[tri.material_index].material
            if not mat or legacy.get(mat.name) not in conflicts:continue
            old=legacy[mat.name];target=export_texture(mat,stage,{}, {},newreport,report['max_texture_size'])
            uv=uv_layer(mesh,mat);parts=[]
            for loop in tri.loops:
                point=np.asarray(native(evaluated.matrix_world@mesh.vertices[mesh.loops[loop].vertex_index].co),dtype=np.float32).astype(np.float64)
                xyz=np.rint(point*100).astype(np.int64)
                tex=np.asarray(uv.data[loop].uv if uv else (0,0),dtype=np.float16).view(np.uint16)
                parts.append(struct.pack('<3i2H',*xyz,*tex))
            key=b''.join(sorted(parts)).hex()
            lookup.setdefault(old,{}).setdefault(key,set()).add(target)
    finally:evaluated.to_mesh_clear()
(stage/'triangle_materials.json').write_text(json.dumps({old:{key:sorted(values) for key,values in triangles.items()} for old,triangles in lookup.items()}))
print('CONFLICT TRIANGLES',sum(len(v) for v in lookup.values()),flush=True)
