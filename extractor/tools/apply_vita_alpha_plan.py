"""Prepare corrected assets from a reviewed Blender opacity plan; never edit input."""
import hashlib,json,struct,sys
from pathlib import Path
import numpy as np

def read_level(data):
    assert data[:4]==b'LVL5'
    count,triangles=struct.unpack_from('<II',data,4)
    offset=32+triangles*36
    prefix=data[:offset]; objects=[]
    for _ in range(count):
        transform=data[offset:offset+88];offset+=88
        paths=[]
        for _ in range(2):
            size=struct.unpack_from('<H',data,offset)[0];offset+=2
            paths.append(data[offset:offset+size].decode());offset+=size
        objects.append((transform,*paths))
    return prefix,objects,data[offset:]

def triangle_key(vertices,matrix):
    parts=[]
    for vertex in vertices:
        xyz=struct.unpack_from('<3h',vertex,4)
        world=matrix@np.array([*(v*.01 for v in xyz),1.])
        position=np.rint(world[:3]*100).astype(np.int64)
        uv=struct.unpack_from('<2H',vertex,10)
        parts.append(struct.pack('<3i2H',*position,*uv))
    return b''.join(sorted(parts)).hex()

def prepare(root,stage):
    plan=json.loads((stage/'repair_plan.json').read_text())
    lookup=json.loads((stage/'triangle_materials.json').read_text())
    destination=stage/'corrected';(destination/'assets/models').mkdir(parents=True,exist_ok=True)
    (destination/'assets/textures').mkdir(parents=True,exist_ok=True)
    (destination/'assets/metadata').mkdir(parents=True,exist_ok=True)
    used=set();unresolved=[];summary=[]
    paths=[root/'level.bin',*sorted((root/'assets/levels').glob('*.bin'))]
    for path in paths:
        data=path.read_bytes();prefix,objects,tail=read_level(data)
        replacement=[];extra=[];old_triangles=0;new_triangles=0
        for index,(transform,mesh,texture) in enumerate(objects):
            variants=plan['variants'].get(texture,[])
            if len(variants)<=1:
                target=variants[0] if variants else texture
                replacement.append((transform,mesh,target));used.add(target);continue
            raw=(root/mesh.removeprefix('app0:/')).read_bytes()
            count=struct.unpack_from('<I',raw)[0];assert len(raw)==4+count*16 and count%3==0
            vertices=[raw[pos:pos+16] for pos in range(4,len(raw),16)]
            matrix=np.array(struct.unpack_from('<16f',transform)).reshape(4,4,order='F')
            groups={}
            for begin in range(0,count,3):
                key=triangle_key(vertices[begin:begin+3],matrix)
                candidates=lookup.get(texture,{}).get(key,[])
                if len(candidates)!=1:
                    unresolved.append((str(path.relative_to(root)),index,begin//3,len(candidates)))
                    continue
                groups.setdefault(candidates[0],bytearray()).extend(b''.join(vertices[begin:begin+3]))
            if sum(len(v) for v in groups.values())!=count*16: continue
            # Keep every original instance index; append additional material subsets.
            first=True
            for target,vertex_bytes in sorted(groups.items(),key=lambda entry:-len(entry[1])):
                payload=struct.pack('<I',len(vertex_bytes)//16)+vertex_bytes
                model='app0:/assets/models/'+hashlib.sha256(payload).hexdigest()[:24]+'.bin'
                (destination/model.removeprefix('app0:/')).write_bytes(payload)
                record=(transform,model,target)
                (replacement if first else extra).append(record);first=False;used.add(target)
            old_triangles+=count//3;new_triangles+=sum(len(v)//48 for v in groups.values())
        if unresolved:continue
        replacement.extend(extra)
        output=bytearray(prefix);struct.pack_into('<I',output,4,len(replacement))
        for transform,mesh,texture in replacement:
            output.extend(transform)
            for value in (mesh,texture):
                encoded=value.encode();output.extend(struct.pack('<H',len(encoded))+encoded)
        output.extend(tail)
        assert old_triangles==new_triangles
        assert output[8:len(prefix)]==data[8:len(prefix)] # spawn, lights count, collision untouched
        result=destination/path.relative_to(root);result.parent.mkdir(parents=True,exist_ok=True);result.write_bytes(output)
        summary.append(dict(level=str(path.relative_to(root)),original_instances=len(objects),instances=len(replacement),split_triangles=old_triangles))
    (stage/'unresolved_triangles.json').write_text(json.dumps(unresolved))
    if unresolved:raise ValueError(f'{len(unresolved)} triangles lack an unambiguous source material; no deployment')
    settings={}
    for texture in used:
        relative=texture.removeprefix('app0:/');source=stage/relative
        if not source.exists():continue
        payload=source.read_bytes();(destination/relative).write_bytes(payload)
        material=plan['materials'][texture].copy()
        # Preserve the old runtime treatment of intrinsic albedo alpha.
        if material['alpha_mode']=='OPAQUE':
            alpha=np.frombuffer(payload[12:],dtype=np.uint8)[3::4]
            if np.any(alpha<250):
                zero=np.sum(alpha<=5);opaque=np.sum(alpha>=250);count=len(alpha)
                mask=count-zero-opaque<=count//20 or(zero>=(count+9)//10 and opaque>=(count+9)//10)
                material.update(alpha_mode='MASK' if mask else 'BLEND',double_sided=True)
        settings[texture]=material
    with (destination/'assets/metadata/materials.bin').open('wb') as out:
        out.write(struct.pack('<4sI',b'MAT1',len(settings)))
        for texture,material in sorted(settings.items()):
            encoded=texture.encode();out.write(struct.pack('<H',len(encoded))+encoded)
            out.write(struct.pack('<BBf',{'OPAQUE':0,'MASK':1,'BLEND':2}[material['alpha_mode']],int(material['double_sided']),material['alpha_cutoff']))
    report=dict(levels=summary,textures=len(settings),modes={mode:sum(m['alpha_mode']==mode for m in settings.values()) for mode in ('OPAQUE','MASK','BLEND')})
    (destination/'alpha_repair_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    return destination
if __name__=='__main__':prepare(*map(Path,sys.argv[1:3]))
