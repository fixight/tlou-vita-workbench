"""Re-export the installed visual set with current exporter; do not save source blend."""
import json,sys,struct
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor.blender_vita_export import export_vita,new_build_folder
installed=Path('//wsl.localhost/Ubuntu/home/TLOU_Vita/assets')
old=json.loads((installed/'assets/metadata/vita_export_report.json').read_text(encoding='utf-8'))
header=struct.unpack_from('<4sIII4f',(installed/'level.bin').read_bytes())
owners=set(old['levels'])
found={str(o.get('nd_level_id') or 'level') for o in bpy.context.scene.objects if o.type=='MESH' and o.get('nd_type')=='visual'}
assert owners<=found, 'Source scene is missing installed levels: '+str(owners-found)
for obj in bpy.context.scene.objects:
    if obj.type=='MESH' and obj.get('nd_type')=='visual':
        obj['nd_export']=str(obj.get('nd_level_id') or 'level') in owners and obj.get('nd_export',True)
# Preserve the spawn from the actual installed level, regardless of saved editor preview state.
spawn=bpy.data.objects.new('VitaRebuildSpawn',None)
bpy.context.scene.collection.objects.link(spawn)
spawn.location=(header[4],-header[6],header[5]);spawn['nd_type']='player_start';spawn['spawn_yaw']=header[7]
bpy.context.scene['nd_vita_spawn_object']=spawn
bpy.context.scene['nd_vita_spawn_name']=spawn.name
bpy.context.view_layer.update()
output=new_build_folder()
print('REBUILD_START',str(output),'owners',sorted(owners),'spawn',header[4:8],flush=True)
report=export_vita(output,scope='ALL',color_layer=old['color_layer'],gain=old['gain'],
    batch_mode=old['batch_mode'],max_polys=old['max_polys'],max_size=old['max_size'],
    min_size=old['min_size'],max_texture_size=old['max_texture_size'],require_spawn=True)
assert set(report['levels'])==owners
assert report['position_quantization']['grid']=='shared_world'
new_header=struct.unpack_from('<4sIII4f',(output/'level.bin').read_bytes())
assert new_header[4:8]==header[4:8],(new_header,header)
comparison={}
for owner,new in report['levels'].items():
    original=old['levels'][owner]
    assert new['collision_triangles']==original['collision_triangles'],owner
    old_bin=(installed/original['file']).read_bytes();new_bin=(output/new['file']).read_bytes()
    end=32+original['collision_triangles']*36
    assert old_bin[32:end]==new_bin[32:end], 'Collision data changed: '+owner
    comparison[owner]={'old_instances':original['instances'],'new_instances':new['instances'],
                      'collision_bytes_unchanged':True}
(output/'assets/metadata/rebuild_comparison.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
Path('D:/TLOUPS4/vita_latest_quantized_build.txt').write_text(str(output),encoding='utf-8')
print('REBUILD_EXPORT_PASS',str(output),json.dumps(comparison),flush=True)
