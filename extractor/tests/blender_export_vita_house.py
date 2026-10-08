import sys, json
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor.blender_vita_export import export_vita,new_build_folder
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath='D:/TLOUPS4/fervent-pascal/editor_exports/austin_editor/levels/hom-house-interior/hom-house-interior.glb')
for obj in bpy.context.scene.objects:
    obj['nd_type']='visual';obj['nd_level_id']='hom-house-interior'
document=json.loads(Path('D:/TLOUPS4/fervent-pascal/editor_exports/austin_editor/scene.json').read_text(encoding='utf-8'))
for record in document['collisions']:
    if record.get('level_id')!='hom-house-interior': continue
    mesh=bpy.data.meshes.new(record['name'])
    mesh.from_pydata([(p[0],-p[2],p[1]) for p in record['vertices']],[],record['faces'])
    obj=bpy.data.objects.new(record['name'],mesh);bpy.context.scene.collection.objects.link(obj)
    obj['nd_type']='collision';obj['nd_level_id']='hom-house-interior';obj.hide_set(True)
del document
from tlou_extractor.blender_static_lighting import apply_lighting
apply_lighting('D:/TLOUPS4/AustinStaticLighting/static_lighting/hom-house-interior/lighting.json',configure_view=False)
build=new_build_folder()
report=export_vita(build,scope='ALL')
Path('D:/TLOUPS4/vita_latest_test_build.txt').write_text(str(build),encoding='utf-8')
assert report['levels']['hom-house-interior']['collision_triangles']>0
assert report['levels']['hom-house-interior']['instances']>0
print('NATIVE HOUSE EXPORT PASS',flush=True)
