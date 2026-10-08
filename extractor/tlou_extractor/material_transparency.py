"""Native PS4 transparency-slot recovery; separate from color/specular textures."""
import io
import re
import struct
from pathlib import Path

from .texture_dds import build_dds
from .texture_quality import indexed_texture


def shader_masks(pak):
    result = {}
    for geometry in pak.get_items('GEOMETRY_1'):
        root = geometry.abs_offset
        count = struct.unpack_from('<I', pak.data, root + 0x68)[0]
        shaders = pak.read_ptr(root + 0x70)
        if count > 100000 or (count and not 0 < shaders <= len(pak.data)-count*72):
            raise ValueError('Invalid native shader table')
        for i in range(count):
            address = shaders + i*72
            name = pak.read_str_at(pak.read_ptr(address))
            table = pak.read_ptr(address + 0x28)
            size = struct.unpack_from('<I', pak.data, address + 0x38)[0]
            if size > 64 or (size and not 0 < table <= len(pak.data)-size*40):
                raise ValueError('Invalid native texture table')
            slots = {}
            for j in range(size):
                key = pak.read_str_at(pak.read_ptr(table+j*40)).lower()
                path = pak.read_str_at(pak.read_ptr(table+j*40+16))
                match = re.search(r'([0-9a-fA-F]{16})(?:\.ndb)?$', path)
                if match:
                    slots[key] = match[1].lower()
            opacity = slots.get('g_tndfetchtransparencymap')
            if opacity:
                result[name] = dict(transparency_hash=opacity,
                                   diffuse_hash=slots.get('g_tndfetchcolor1map', ''),
                                   normal_hash=slots.get('g_tndfetchnormal1map', ''),
                                   material_name=name.split(':')[0].split(',')[0].replace('\\','/').split('/')[-1])
    return result


def export_mask(key, folder, handler=None):
    folder = Path(folder)
    path = folder / ('opacity_' + key + '.png')
    if not path.is_file():
        texture = indexed_texture(key) or (handler.get_texture_by_hash(key) if handler else None)
        if not texture or not texture.raw_bytes:
            return None
        folder.mkdir(parents=True, exist_ok=True)
        dds = build_dds(texture.raw_bytes, texture.width, texture.height, texture.fmt_id, texture.is_pc)
        from PIL import Image
        with Image.open(io.BytesIO(dds)) as image:
            # Native opacity maps inspected here are BC4 (single red channel).
            # Never take PNG's synthesized alpha=1 as the mask.
            red = image.convert('RGB').getchannel('R')
            red.save(path)
    return path


def transparency_extras(mesh, folder, handler=None, export_png=True):
    key = getattr(mesh, 'transparency_hash', '')
    if not key:
        return {}
    if not export_png:
        return {'nd_transparency_hash':key}
    path = export_mask(key, folder, handler)
    return {'nd_transparency_hash': key,
            'nd_transparency_uri': ('textures/'+path.name) if path else '',
            'nd_transparency_missing': path is None}


def export_bindings(bindings_path, folder):
    """Upgrade a previously exported scene using its exact material bindings."""
    import json
    from .pak_reader import PakFile
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    bindings=json.loads(Path(bindings_path).read_text(encoding='utf-8'))['records']
    sources={}; records=[]; missing=[]; ambiguous=[]
    for record in bindings:
        source=record['source']
        if source not in sources:
            table={}
            for value in shader_masks(PakFile(source)).values():
                key=(value['material_name'],value['diffuse_hash'],value['normal_hash'])
                table.setdefault(key,set()).add(value['transparency_hash'])
            sources[source]=table
        masks=sources[source].get((record['material_name'],record['diffuse_hash'],record['normal_hash']),set())
        if not masks: continue
        if len(masks)!=1:
            ambiguous.append(record['old_material']);continue
        key=next(iter(masks)); path=export_mask(key,folder/'opacity_masks')
        if path is None:
            missing.append({'material':record['old_material'],'hash':key});continue
        records.append({k:record[k] for k in ('old_material','material_name','diffuse_hash','normal_hash','source')} |
                       {'transparency_hash':key,'image':'opacity_masks/'+path.name})
    result={'records':records,'missing':missing,'ambiguous':ambiguous,
            'source_slot':'g_tNdFetchTransparencyMap','channel':'R','default_mode':'BLEND'}
    (folder/'transparency.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Native opacity:',len(records),'bindings;',len({r['transparency_hash'] for r in records}),'masks;',len(missing),'missing',flush=True)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('bindings');parser.add_argument('output')
    args=parser.parse_args();export_bindings(args.bindings,args.output)
