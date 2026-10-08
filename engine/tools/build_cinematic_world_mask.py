"""Remove only exact source-prop triangles from merged static batches.
The original level and meshes are never modified. VCM1 binds to the level hash.
"""
import json,struct,hashlib
from pathlib import Path
import numpy as np
import export_vita_character as skin


def fnv(data):
    value=14695981039346656037
    for b in data: value=((value^b)*1099511628211)&0xffffffffffffffff
    return value


def key(points):
    return tuple(sorted(tuple(row) for row in np.rint(points*100).astype(np.int64)))


def build(manifest, level, output, runtime_root='app0:/assets/cinematics/bedroom/mask'):
    manifest,level,output=Path(manifest),Path(level),Path(output)
    scene=json.loads(manifest.read_text(encoding='utf-8'))
    doc,read=skin.load_glb(manifest.parent/'house/house.glb')
    worlds=skin.evaluate_world_transforms(doc,read,None,0)
    triangles=set()
    for index,node in enumerate(doc['nodes']):
        if not node.get('name','').startswith(tuple(scene['hide_static_prefixes'])) or 'mesh' not in node: continue
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            xyz=read(primitive['attributes']['POSITION'])
            xyz=(worlds[index] @ np.c_[xyz,np.ones(len(xyz))].T).T[:,:3]
            indices=read(primitive['indices']).ravel().reshape(-1,3)
            triangles.update(key(xyz[t]) for t in indices)
    data=level.read_bytes();magic,count,collision,lights=struct.unpack_from('<4sIII',data)
    if magic!=b'LVL5': raise ValueError('Expected LVL5')
    cursor=32+collision*36
    patches=[];removed=0
    output.mkdir(parents=True,exist_ok=True)
    for index in range(count):
        matrix=np.array(struct.unpack_from('<16f',data,cursor)).reshape(4,4).T;cursor+=88
        paths=[]
        for _ in range(2):
            n=struct.unpack_from('<H',data,cursor)[0];cursor+=2
            paths.append(data[cursor:cursor+n].decode());cursor+=n
        raw=(level.parent/paths[0].removeprefix('app0:/')).read_bytes()
        vertices=struct.unpack_from('<I',raw)[0]
        if len(raw)!=4+vertices*16 or vertices%3: raise ValueError('Invalid static mesh')
        local=np.ndarray((vertices,3),'<i2',raw,offset=8,strides=(16,2)).astype(np.float64)*.01
        world=(matrix @ np.c_[local,np.ones(vertices)].T).T[:,:3].reshape(-1,3,3)
        keep=[i for i,t in enumerate(world) if key(t) not in triangles]
        if len(keep)==len(world): continue
        removed+=len(world)-len(keep)
        if keep:
            payload=struct.pack('<I',len(keep)*3)+b''.join(raw[4+i*48:4+(i+1)*48] for i in keep)
            name=hashlib.sha256(payload).hexdigest()[:24]+'.bin';(output/name).write_bytes(payload)
            path=runtime_root+'/'+name
        else: path=''
        patches.append((index,path))
    result=struct.pack('<4sIQII',b'VCM1',1,fnv(data),count,len(patches))
    for index,path in patches:
        encoded=path.encode(); result+=struct.pack('<II',index,len(encoded))+encoded
    (output/'world.vcm').write_bytes(result)
    report={'matched_prop_triangles':removed,'reference_triangles':len(triangles),'patched_instances':len(patches)}
    (output/'world.vcm.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(report)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest');p.add_argument('level');p.add_argument('output')
    a=p.parse_args();build(a.manifest,a.level,a.output)
