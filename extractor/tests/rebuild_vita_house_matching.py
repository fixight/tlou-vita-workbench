import sys,json,struct
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor.blender_vita_export import export_vita,combine_levels
installed=Path('//wsl.localhost/Ubuntu/home/TLOU_Vita/assets')
output=Path('D:/VitaEngine/app0/exports/build_2026-10-03_00-27-27_636699')
old=json.loads((installed/'assets/metadata/vita_export_report.json').read_text(encoding='utf-8'))
combined=json.loads((output/'assets/metadata/vita_export_report.json').read_text(encoding='utf-8'))
extras=set(combined['unlit_objects'])-set(old['unlit_objects'])
assert len(extras)==12 and all('door' in name for name in extras),extras
header=struct.unpack_from('<4sIII4f',(installed/'level.bin').read_bytes())
for obj in bpy.context.scene.objects:
    if obj.type=='MESH' and obj.get('nd_type')=='visual':
        obj['nd_export']=obj.get('nd_level_id')=='hom-house-interior' and obj.name not in extras and obj.get('nd_export',True)
spawn=bpy.data.objects.new('VitaRebuildSpawn',None);bpy.context.scene.collection.objects.link(spawn)
spawn.location=(header[4],-header[6],header[5]);spawn['nd_type']='player_start';spawn['spawn_yaw']=header[7]
bpy.context.scene['nd_vita_spawn_object']=spawn;bpy.context.scene['nd_vita_spawn_name']=spawn.name
bpy.context.view_layer.update()
partial=output/'house_matching_source'
report=export_vita(partial,scope='ALL',color_layer=old['color_layer'],gain=old['gain'],
    batch_mode=old['batch_mode'],max_polys=old['max_polys'],max_size=old['max_size'],
    min_size=old['min_size'],max_texture_size=old['max_texture_size'],require_spawn=True)
assert report['levels']['hom-house-interior']['instances']==old['levels']['hom-house-interior']['instances']
import shutil
for folder in ('models','textures','levels'):
    for source in (partial/'assets'/folder).glob('*'):
        shutil.copy2(source,output/'assets'/folder/source.name)
combined['levels']['hom-house-interior']=report['levels']['hom-house-interior']
combined['unlit_objects']=sorted(set(combined['unlit_objects'])-extras)
combined['main_level']=combine_levels(output,json.loads((output/'assets/metadata/level_files.json').read_text()))
combined['rebuild_source_excluded_objects']=sorted(extras)
(output/'assets/metadata/vita_export_report.json').write_text(json.dumps(combined,ensure_ascii=False,indent=2),encoding='utf-8')
comparison=json.loads((output/'assets/metadata/rebuild_comparison.json').read_text())
comparison['hom-house-interior']['new_instances']=report['levels']['hom-house-interior']['instances']
source=installed/old['levels']['hom-house-interior']['file'];target=output/report['levels']['hom-house-interior']['file']
end=32+old['levels']['hom-house-interior']['collision_triangles']*36
assert source.read_bytes()[32:end]==target.read_bytes()[32:end]
assert (output/'level.bin').read_bytes()[:32]==(installed/'level.bin').read_bytes()[:32]
(output/'assets/metadata/rebuild_comparison.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
print('EXACT_INSTALLED_GEOMETRY_SET_PASS',combined['main_level'],flush=True)
