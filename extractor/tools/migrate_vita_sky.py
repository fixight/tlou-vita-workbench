"""Remove only native sky triangles from an old LVL5 export, preserving instance indices.
Whole-sky meshes stay as index placeholders and are excluded by the sky descriptor.
Mixed meshes retain all other vertex bytes. No collision, spawn or door data changes.
"""
import hashlib,json,struct,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor.blender_vita_sky import descriptor
root,stage=map(Path,sys.argv[1:3]);out=stage/'corrected';(out/'assets/models').mkdir(parents=True,exist_ok=True)
keys=set(json.loads((stage/'legacy_sky_triangles.json').read_text()));excluded=set();report=[]
paths=[root/'level.bin',*sorted((root/'assets/levels').glob('*.bin'))]
for path in paths:
 data=path.read_bytes();magic,count,col,lights,*spawn=struct.unpack_from('<4sIII4f',data)
 assert magic==b'LVL5' and lights==0
 offset=32+col*36;result=bytearray(data[:offset]);removed=0;full=0;changed=0
 for i in range(count):
  fixed=data[offset:offset+88];offset+=88;names=[]
  for _ in range(2):
   length=struct.unpack_from('<H',data,offset)[0];offset+=2
   names.append(data[offset:offset+length].decode());offset+=length
  mesh_path=root/names[0].removeprefix('app0:/');payload=mesh_path.read_bytes();n=struct.unpack_from('<I',payload)[0]
  assert n%3==0 and len(payload)==4+n*16
  dtype=np.dtype({'names':['pos'],'formats':[('<i2',3)],'offsets':[4],'itemsize':16})
  positions=np.frombuffer(payload,dtype=dtype,offset=4)['pos'].astype(np.float64)*.01
  matrix=np.array(struct.unpack_from('<16f',fixed)).reshape(4,4).T
  world=positions@matrix[:3,:3].T+matrix[:3,3];quant=np.rint(world*100).astype(np.int64).reshape(-1,3,3)
  mask=np.array([b''.join(sorted(struct.pack('<3q',*p) for p in tri)).hex() in keys for tri in quant])
  found=int(mask.sum());removed+=found
  if found:
   if found==len(mask):excluded.add(names[0]);full+=1
   else:
    raw=np.frombuffer(payload,dtype=np.uint8,offset=4).reshape(-1,3,16)[~mask].tobytes()
    new=struct.pack('<I',len(raw)//16)+raw;filename=hashlib.sha256(new).hexdigest()[:24]+'.bin'
    (out/'assets/models'/filename).write_bytes(new);names[0]='app0:/assets/models/'+filename;changed+=1
  result+=fixed
  for name in names:
   encoded=name.encode();result+=struct.pack('<H',len(encoded))+encoded
 result+=data[offset:]
 relative=path.relative_to(root);target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(result)
 assert result[:32+col*36]==data[:32+col*36]
 report.append({'file':str(relative),'removed_sky_triangles':removed,'excluded_instances':full,'mixed_meshes_rewritten':changed,'instance_count':count})
 assert path.name!='level.bin' or removed==len(keys),(removed,len(keys))
sky=json.loads((stage/'sky_export_report.json').read_text())['sky'];variant=sky['variants'][sky['default']]
(out/'assets/metadata').mkdir(parents=True,exist_ok=True)
for file in ('sky.bin',Path(variant['file']).name):
 (out/'assets/metadata'/file).write_bytes(descriptor(variant['position_step_metres'],variant['mesh'],variant['texture'],sorted(excluded)))
for name in (variant['mesh'],variant['texture']):
 relative=Path(name.removeprefix('app0:/'));target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((stage/relative).read_bytes())
(out/'assets/metadata/sky_export_report.json').write_text(json.dumps({'sky':sky,'legacy_migration':report,'legacy_meshes':sorted(excluded)},indent=2))
print(json.dumps(report,indent=2));print('EXCLUDED MESHES',len(excluded))
