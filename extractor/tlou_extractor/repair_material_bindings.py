"""Recover exact per-mesh albedo bindings without rebuilding editor geometry."""
import hashlib
import json
from pathlib import Path
import re
import struct
import numpy as np
from .pak_reader import PakFile
from .mesh_builder import MeshBuilder
from .streaming_export import asset_folders
from .texture_quality import indexed_texture


def position_digest(values):
    return hashlib.sha256(np.rint(np.asarray(values,dtype=np.float64)*10000).astype('<i8').tobytes()).hexdigest()


def build(folder):
    scene=json.loads((folder/'scene.json').read_text(encoding='utf-8'))
    files={}
    for directory in asset_folders():
        for path in directory.glob('*.pak'):
            files.setdefault(path.name,path)
    actors=sorted([name[:-10] for name,p in files.items() if name.endswith('-tstrm.pak') and p.parent.name=='actor50'],key=len,reverse=True)
    cache={}
    def source_materials(filename):
        if filename not in cache:
            path=files.get(filename)
            result={}
            if path:
                for model in MeshBuilder(PakFile(str(path))).models:
                    for mesh in model.submeshes:
                        binding={'diffuse_hash':mesh.diffuse_hash,'normal_hash':mesh.normal_hash,
                                 'material_name':mesh.material_name,'source':str(path),
                                 'uv_arrays':(mesh.uv0,mesh.uv1,mesh.uv12)}
                        result.setdefault(mesh.name,[]).append(binding)
            cache[filename]=result
        return cache[filename]
    records=[]; unmatched=[]; uv_blob=bytearray()
    for entry in scene['level_glbs']:
        path=Path(entry['path']); raw=path.read_bytes()
        size=struct.unpack_from('<I',raw,12)[0]; doc=json.loads(raw[20:20+size])
        binary=memoryview(raw)[28+size:]
        materials=doc.get('materials',[])
        for node in doc['nodes']:
            if 'mesh' not in node: continue
            mesh=doc['meshes'][node['mesh']]
            primitive=mesh['primitives'][0]
            material=materials[primitive['material']]
            match=re.match(r'^(.+?-tstrm)_',node.get('name',''))
            filename=match[1]+'.pak' if match else None
            if not filename:
                actor=next((a for a in actors if material['name'].startswith(a+'_')),None)
                if actor: filename=actor+'-tstrm.pak'
            candidates=source_materials(filename).get(mesh['name'],[]) if filename else []
            unique={(v['diffuse_hash'],v['normal_hash']) for v in candidates}
            if len(unique)!=1:
                unmatched.append({'level':entry['level_id'],'mesh':mesh['name'],'material':material['name'],'candidates':len(unique)})
                continue
            binding=candidates[0]
            uv_streams=[]
            for channel,values in enumerate(binding['uv_arrays']):
                if values:
                    array=np.asarray(values,dtype='<f4')
                    uv_streams.append({'channel':channel,'offset':len(uv_blob),'count':len(values)})
                    uv_blob.extend(array.tobytes())
            accessor=doc['accessors'][primitive['attributes']['POSITION']]
            view=doc['bufferViews'][accessor['bufferView']]
            assert accessor['componentType']==5126 and not view.get('byteStride')
            offset=view.get('byteOffset',0)+accessor.get('byteOffset',0)
            positions=np.frombuffer(binary[offset:offset+accessor['count']*12],dtype='<f4').reshape(-1,3)
            rotated=positions[:,[0,2,1]].copy(); rotated[:,1]*=-1
            record_binding={k:v for k,v in binding.items() if k!='uv_arrays'}
            records.append(dict(record_binding,uv_streams=uv_streams,level=entry['level_id'],old_material=material['name'],mesh=mesh['name'],
                vertex_count=accessor['count'],position_hashes=[position_digest(positions),position_digest(rotated)]))
        print('Material bindings',entry['level_id'],len(records),flush=True)
    payload={'records':records,'unmatched':unmatched,'position_quantization':0.0001}
    (folder/'material_repair_bindings.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    (folder/'material_repair_uv.bin').write_bytes(uv_blob)
    needed={h for r in records for h in (r['diffuse_hash'],r['normal_hash']) if h}
    output=folder/'texture_sources_hq'
    manifest=json.loads((folder/'texture_hq_manifest.json').read_text(encoding='utf-8'))
    from PIL import Image
    import io
    from .texture_dds import build_dds
    missing=[]
    for h in sorted(needed):
        texture=indexed_texture(h)
        if not texture:
            missing.append(h); continue
        png=output/(h+'.png')
        if not png.exists():
            with Image.open(io.BytesIO(build_dds(texture.raw_bytes,texture.width,texture.height,texture.fmt_id,texture.is_pc))) as image:
                image.save(png)
        manifest[h]={'png':str(png.resolve()),'hash':h,'name':texture.name,'w':texture.width,'h':texture.height}
    (folder/'texture_hq_bindings_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    print('MATERIAL BINDINGS DONE',len(records),'unmatched',len(unmatched),'missing textures',missing,flush=True)


if __name__=='__main__':
    import sys
    build(Path(sys.argv[1]).resolve())
