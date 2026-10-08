"""Validate every door sidecar against its LVL5 and readable binding metadata."""
import struct,json,sys
from pathlib import Path
import numpy as np
root=Path(sys.argv[1]);meta=root/'assets/metadata'
def fnv(data):
 h=14695981039346656037
 for b in data:h=((h^b)*1099511628211)&0xffffffffffffffff
 return h
def verify(path,level):
 raw=path.read_bytes();offset=0
 def read(fmt):
  nonlocal offset
  result=struct.unpack_from(fmt,raw,offset);offset+=struct.calcsize(fmt);return result
 def text():
  nonlocal offset
  n,=read('<I');result=raw[offset:offset+n].decode();offset+=n;return result
 leveldata=level.read_bytes();_,ni,nc,_,*_=struct.unpack_from('<4sIII4f',leveldata)
 magic,version,ei,ec,h,count=read('<4sIIIQI')
 assert (magic,version,ei,ec,h)==(b'VDOR',1,ni,nc,fnv(leveldata))
 parts=set();claimed=set();ids=[];total_tri=0
 original=np.frombuffer(leveldata,dtype='<f4',count=nc*9,offset=32).reshape(-1,3,3)
 for _ in range(count):
  key,label=text(),text();assert key not in ids;ids.append(key)
  motion=read('<6f');assert np.isfinite(motion).all() and 0<motion[4]<30
  nv,=read('<I');assert nv>0
  for _ in range(nv):
   v=read('<6f');assert np.all(np.array(v[:3])<=v[3:])
  lists=[]
  for target,limit in [(parts,ni),(claimed,nc)]:
   n,=read('<I');indices=list(read('<'+'I'*n));assert all(i<limit for i in indices)
   assert not target.intersection(indices);assert len(set(indices))==len(indices);target.update(indices);lists.append(indices)
  n,=read('<I');assert n>0;total_tri+=n
  geometry=np.array(read('<'+'f'*(n*9)),dtype=np.float32).reshape(-1,3,3)
  assert np.isfinite(geometry).all()
  assert np.all(np.linalg.norm(np.cross(geometry[:,1]-geometry[:,0],geometry[:,2]-geometry[:,0]),axis=1)>1e-8)
  if lists[1]:assert np.array_equal(geometry,original[lists[1]])
 assert offset==len(raw)
 return count,len(parts),len(claimed),total_tri
files=json.loads((meta/'level_files.json').read_text())
for owner,filename in files.items():verify(meta/('doors_'+Path(filename).stem+'.bin'),root/filename)
result=verify(meta/'doors.bin',root/'level.bin')
doc=json.loads((meta/'doors.json').read_text());assert result[0]==len(doc['doors'])==4
assert result[2]==12 and result[3]==48,result
assert all(d['owner']=='hom-house-interior' for d in doc['doors'])
print('PASS VDOR: main and all chunks match LVL5 hashes, binding indices, finite nondegenerate colliders; native leaf geometry preserved',result)
