"""Export PS4 static-lighting inputs, preserving unverified shader semantics.

python -m tlou_extractor.static_lighting level-tstrm.pak --output lighting
The sidecar is independent of Blender and contains exact per-instance streams.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

import numpy as np

from .pak_reader import PakFile
from .mesh_builder import MeshBuilder
from .texture_quality import indexed_texture
from .texture_dds import build_dds


LIGHT_SLOTS = {'g_tLmLightColor', 'g_tLmLightDir', 'g_tLmBaseColor', 'g_tLightMap'}


def position_digest(values):
    return hashlib.sha256(np.rint(np.asarray(values, dtype=np.float64) * 10000)
                          .astype('<i8').tobytes()).hexdigest()


def read_streams(pak, table, count, vertices):
    """Read instance overrides, never the prototype's placeholder streams."""
    data = pak.data
    if not 0 <= count <= 32 or (count and not 0 < table <= len(data)-count*24):
        raise ValueError('Invalid instance lighting stream table')
    result = {}
    for i in range(count):
        address = table + i*24
        stride, size = struct.unpack_from('<HI', data, address+2)
        component, buffer = pak.read_ptr(address+8), pak.read_ptr(address+16)
        if not 0 < component < len(data):
            raise ValueError('Invalid lighting attribute descriptor')
        attribute = data[component]
        if attribute not in (5, 8, 9, 10):
            continue
        expected = {5:8, 8:16, 9:12, 10:12}[attribute]
        if stride != expected or size != vertices*stride or not 0 < buffer <= len(data)-size:
            raise ValueError(f'Unsupported/truncated lighting stream {attribute}')
        array = np.frombuffer(data, dtype='<f4', count=size//4, offset=buffer).reshape(vertices, stride//4)
        if not np.isfinite(array).all():
            raise ValueError(f'Non-finite lighting stream {attribute}')
        result[attribute] = array.copy()
    return result


def extract(pak):
    if pak.magic not in (2681, 68217):
        raise ValueError('Static lighting layout currently supports PS4 PAKs only')
    meshes = {s.name:s for m in MeshBuilder(pak).models for s in m.submeshes}
    records, warnings = [], []
    data = pak.data
    for geometry in pak.get_items('GEOMETRY_1'):
        root = geometry.abs_offset
        material_slots = {}
        count = struct.unpack_from('<I', data, root+0x68)[0]
        shaders = pak.read_ptr(root+0x70)
        if count > 100000 or not 0 < shaders <= len(data)-count*72:
            raise ValueError('Invalid shader table')
        for i in range(count):
            address = shaders+i*72
            name = pak.read_str_at(pak.read_ptr(address))
            table = pak.read_ptr(address+0x28)
            size = struct.unpack_from('<I', data, address+0x38)[0]
            if size > 64 or (size and not 0 < table <= len(data)-size*40):
                raise ValueError('Invalid material texture table')
            slots = {}
            for j in range(size):
                slot = pak.read_str_at(pak.read_ptr(table+j*40))
                path = pak.read_str_at(pak.read_ptr(table+j*40+16))
                match = re.search(r'([0-9a-fA-F]{16})(?:\.ndb)?$', path)
                if slot in LIGHT_SLOTS and match:
                    slots[slot] = match[1].lower()
            material_slots[name] = slots
        raw = {}
        table = pak.read_ptr(root+0x30)
        count = struct.unpack_from('<I', data, root+0x28)[0]
        if count > 100000 or not 0 < table <= len(data)-count*136:
            raise ValueError('Invalid geometry table')
        for i in range(count):
            address = table+i*136
            name = pak.read_str_at(pak.read_ptr(address+8))
            raw[name] = (struct.unpack_from('<I',data,address+0x1c)[0],
                         pak.read_str_at(pak.read_ptr(address+0x48)))
        table = pak.read_ptr(root+0x50)
        count = struct.unpack_from('<I', data, root+0x48)[0]
        if count > 100000 or (count and not 0 < table <= len(data)-count*8):
            raise ValueError('Invalid instance table')
        for i in range(count):
            instance = pak.read_ptr(table+i*8)
            if not 0 < instance <= len(data)-192:
                raise ValueError('Invalid instance')
            proto = pak.read_str_at(pak.read_ptr(instance+8))
            prefix = proto.replace('\\','/').split('/')[-1].replace('.ma','')
            entries = pak.read_ptr(instance+0x30)
            entry_count = struct.unpack_from('<I',data,instance+0x20)[0]
            if entry_count > 100000 or (entry_count and not 0 < entries <= len(data)-entry_count*80):
                raise ValueError('Invalid instance submesh table')
            for j in range(entry_count):
                entry = entries+j*80
                name = pak.read_str_at(pak.read_ptr(entry))
                full_name = f'{prefix}_{name}' + (f'#{i}' if i else '')
                mesh = meshes.get(full_name)
                if name not in raw or mesh is None:
                    warnings.append({'mesh':full_name,'reason':'No matching geometry'})
                    continue
                vertices, material = raw[name]
                streams = read_streams(pak, pak.read_ptr(entry+24),
                                       struct.unpack_from('<I',data,entry+16)[0], vertices)
                # Match the float32 positions written to glTF before hashing.
                positions = np.asarray(mesh.positions,dtype=np.float32)
                converted = positions[:,[0,2,1]].copy(); converted[:,1] *= -1
                records.append({'mesh':full_name,'material':material,'vertex_count':vertices,
                                'position_hashes':[position_digest(positions),position_digest(converted)],
                                'slots':material_slots.get(material,{}),'arrays':streams})
    return records, warnings


def export(pak_paths, output, source_names=None, owner_level=None):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    manifest = {'version':1,'platform':'PS4','shader_reconstruction':'experimental',
                'notes':['Streams 8/9/10 are preserved verbatim; their basis interpretation is provisional.',
                         'Stream 5 can contain non-normalized values; never wrap these into an atlas automatically.',
                         'HDR DDS files are lossless wrappers of the highest indexed native mip.',
                         'No dynamic light sources are exported.'],
                'records':[],'textures':{},'warnings':[]}
    blob = bytearray()
    for source_index, path in enumerate(pak_paths):
        pak = PakFile(str(path))
        source_name = source_names[source_index] if source_names else Path(path).name
        try:
            records, warnings = extract(pak)
        except ValueError as exc:
            manifest['warnings'].append({'source':source_name,'reason':str(exc)})
            continue
        manifest['warnings'].extend(dict(source=str(path),**w) for w in warnings)
        for record in records:
            record['source'] = str(Path(path).resolve())
            record['level'] = Path(source_name).stem.removesuffix('-tstrm')
            record['source_level'] = record['level']
            if owner_level:
                record['level'] = owner_level
            record['streams'] = {}
            for attribute, array in record.pop('arrays').items():
                record['streams'][str(attribute)] = {'offset':len(blob),'count':len(array),'components':array.shape[1]}
                blob.extend(array.astype('<f4').tobytes())
            manifest['records'].append(record)
    from .texture_handler import TextureHandler
    local = None
    for h in sorted({h for r in manifest['records'] for h in r['slots'].values()}):
        texture = indexed_texture(h)
        if texture is None:
            if local is None:
                local = {}
                for path in pak_paths:
                    handler = TextureHandler(PakFile(str(path)))
                    for t in handler.textures_by_hex.values():
                        previous = local.get(t.hex_hash)
                        if previous is None or t.width*t.height > previous.width*previous.height:
                            local[t.hex_hash] = t
            texture = local.get(h)
        if texture is None:
            manifest['warnings'].append({'hash':h,'reason':'Texture unavailable'})
            continue
        filename = h+'.dds'
        (output/filename).write_bytes(build_dds(texture.raw_bytes,texture.width,texture.height,texture.fmt_id,texture.is_pc))
        manifest['textures'][h] = {'file':filename,'name':texture.name,'width':texture.width,
                                  'height':texture.height,'format':texture.fmt_id}
    (output/'streams.bin').write_bytes(blob)
    (output/'lighting.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paks', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = export(args.paks,args.output)
    print('Static lighting:',len(result['records']),'meshes,',len(result['textures']),'textures,',len(result['warnings']),'warnings')
