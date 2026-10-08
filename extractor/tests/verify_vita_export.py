"""Independent structural and geometric validation of actual Vita export files."""
import json, math, struct, sys
from pathlib import Path
root=Path(sys.argv[1]); metadata=root/'assets/metadata' if (root/'assets/metadata').is_dir() else root
report=json.loads((metadata/'vita_export_report.json').read_text(encoding='utf-8'))
models=set();textures=set();corners=0
entries=list(report['levels'].values())
if report.get('main_level'):entries.append(report['main_level'])
for level in entries:
    data=(root/level['file']).read_bytes()
    magic,instances,triangles,lights,*spawn=struct.unpack_from('<4sIII4f',data)
    assert magic==b'LVL5' and lights==0
    assert instances==level['instances'] and triangles==level['collision_triangles']
    offset=32
    for i in range(triangles):
        assert all(math.isfinite(x) for x in struct.unpack_from('<9f',data,offset))
        offset+=36
    for i in range(instances):
        values=struct.unpack_from('<22f',data,offset);offset+=88
        matrix,lo,hi=values[:16],values[16:19],values[19:22]
        paths=[]
        for j in range(2):
            length=struct.unpack_from('<H',data,offset)[0];offset+=2
            name=data[offset:offset+length].decode('utf-8');offset+=length
            assert name.startswith('app0:/assets/')
            paths.append(root/name.removeprefix('app0:/'))
        mesh=paths[0].read_bytes();count=struct.unpack_from('<I',mesh)[0]
        assert count%3==0 and len(mesh)==4+count*16
        if report.get('batch_mode')=='KD': assert count//3<=report['max_polys']
        for j in range(count):
            v=struct.unpack_from('<4B3h2e2b',mesh,4+j*16)
            assert all(math.isfinite(t) for t in v[7:9])
            p=[matrix[12+k]+v[4+k]*.01 for k in range(3)]
            assert all(lo[k]-1e-4<=p[k]<=hi[k]+1e-4 for k in range(3))
        tex=paths[1].read_bytes();w,h,size=struct.unpack_from('<III',tex)
        assert size==w*h*4 and len(tex)==12+size and w>0 and h>0
        models.add(paths[0]);textures.add(paths[1])
        if level['file']!='level.bin':corners+=count
    assert offset==len(data)
result={'levels':len(report['levels']),'unique_models':len(models),'unique_textures':len(textures),'draw_corners':corners,'all_buffers_exact':True,'quantized_vertices_inside_AABB':True}
(metadata/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(result)
