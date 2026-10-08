"""Read every byte of the exported SK16 package and emulate GPU skinning."""
import struct,json,sys
from pathlib import Path
import numpy as np
p=Path(sys.argv[1]);data=p.read_bytes();offset=0

def read(fmt):
    global offset
    v=struct.unpack_from(fmt,data,offset);offset+=struct.calcsize(fmt);return v

def blob(n):
    global offset
    b=data[offset:offset+n];assert len(b)==n;offset+=n;return b
magic,version,nb,nj,nc=read('<4s4I');assert magic==b'SK16' and version in (1,2)
if version==2:
    pivots=np.frombuffer(blob(nj*12),dtype='<f4').reshape(nj,3);assert np.all(np.isfinite(pivots))
batches=[];triangles=0
for i in range(nb):
    nv,ni,npal,npath,x,y,z,step=read('<4I4f');path=blob(npath).decode();palette=np.frombuffer(blob(npal*2),'<u2');assert npal<=24 and max(palette)<nj
    v=np.frombuffer(blob(nv*16),dtype=[('p','<i2',3),('uv','<f2',2),('n','i1',2),('j','u1',2),('w','u1'),('pad','u1')]);indices=np.frombuffer(blob(ni*2),'<u2');assert ni%3==0 and indices.max()<nv and v['j'].max()<npal and np.all(v['pad']==0)
    assert np.all(np.isfinite(v['uv']));pos=v['p'].astype(float)*step+np.array([x,y,z]);batches.append((pos,palette[v['j']],v['w'].astype(float)/255));triangles+=ni//3
    texture=p.parent/path.rsplit('/',1)[-1];raw=texture.read_bytes();w,h,size=struct.unpack_from('<III',raw);assert size==w*h*4==len(raw)-12 and max(w,h)<=512
clips=[];bounds={}
for c in range(nc):
    nn,nf,duration=read('<IIf');name=blob(nn).decode();mats=np.frombuffer(blob(nf*nj*64),'<f4').reshape(nf,nj,4,4).transpose(0,1,3,2);assert np.all(np.isfinite(mats)) and nf>1 and duration>0
    lo=np.ones(3)*np.inf;hi=-lo;max_edge_movement=0
    for frame in range(nf):
        for pos,j,w in batches:
            hp=np.c_[pos,np.ones(len(pos))];posed=np.einsum('nij,nj->ni',mats[frame,j[:,0]],hp)*w[:,None]+np.einsum('nij,nj->ni',mats[frame,j[:,1]],hp)*(1-w[:,None]);assert np.all(np.isfinite(posed));assert np.max(np.abs(posed[:,3]-1))<1e-5
            lo=np.minimum(lo,posed[:,:3].min(0));hi=np.maximum(hi,posed[:,:3].max(0))
    assert hi[1]-lo[1]<2 and np.max(hi-lo)<3 and lo[1]>-.25,(name,lo,hi)
    bounds[name]={'min':lo.tolist(),'max':hi.tolist()};clips.append(name)
assert clips[:3]==['sar-p-relaxed-idle','sar-p-walk-fw','sar-p-run-fw']
assert nc==3 or clips[3]=='sar-p-open-pull-l--sarah'
if nc==5:assert clips[4]=='hom1-house-door-push--sarah'
assert offset==len(data) and triangles==33505 and nc in (3,4,5)
print('PASS SK16: 16-byte stride, palettes, all indices/textures/frames, homogeneous skinning, metre scale, feet bounds, complete file')
print(json.dumps({'batches':nb,'triangles':triangles,'skin_matrices':nj,'bounds':bounds},indent=2))
