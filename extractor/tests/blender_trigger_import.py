"""Analytic source volumes must import with their actual triangle/quad faces."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from mathutils import Vector
from tlou_extractor.blender_export import add_streaming

doc=json.loads(Path(r'D:\TLOUPS4\AustinStreaming\streaming_runtime.json').read_text(encoding='utf-8'))
records=[]
for kind in ('sphere','cylinder'):
    records.append(next(r for r in doc['regions'] if any(s.get('analytic',{}).get('kind')==kind for s in r['shapes'])))
doc['regions']=records
folder=Path(r'D:\TLOUPS4\fervent-pascal\tests_temp_out\trigger_import');folder.mkdir(parents=True,exist_ok=True)
add_streaming(doc,folder)
bpy.context.view_layer.update()
for region in records:
    parent=next(o for o in bpy.context.scene.objects if o.get('nd_region_id')==region['id'] and o.get('nd_type')==region['type'])
    assert parent.get('nd_trigger_info_json') and not parent['nd_cpp_enabled']
    for index,shape in enumerate(region['shapes']):
        obj=next(o for o in parent.children if o.name.startswith(region['name']+'__volume_'+str(index)))
        assert len(obj.data.polygons)==len(shape['faces'])
        for polygon,face in zip(obj.data.polygons,shape['faces']):
            assert len(polygon.vertices)==len(face['world_vertices'])
            for vertex,original in zip(polygon.vertices,face['world_vertices']):
                expected=Vector((original[0],-original[2],original[1]))
                assert ((obj.matrix_world @ obj.data.vertices[vertex].co)-expected).length<.0001
print('PASS: sphere/cylinder faces, source world coordinates and region cards survive Blender import',flush=True)
