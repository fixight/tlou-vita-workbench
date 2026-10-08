"""Decode highest available exact-name images for an existing Blender export.

Preserves the previous export; writes a separate texture folder and manifest.
Names are recovered from existing images, never fuzzy matched.
"""
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import re
import sys
from PIL import Image
from .texture_dds import build_dds
from .texture_quality import texture_index


def upgrade(folder):
    diagnostic = json.loads((folder/'texture_material_diagnostic.json').read_text(encoding='utf-8'))
    names = sorted({re.sub(r'\.\d{3}$', '', i['name']).removesuffix('.png')
                    for m in diagnostic['materials'] for i in m['images']})
    output = folder/'texture_sources_hq'
    output.mkdir(exist_ok=True)
    index = texture_index()
    def decode(name):
        info = index.get(name.lower())
        if not info:
            return name, {'error':'No exact texture name in index'}
        try:
            destination = output/(name+'.png')
            if destination.exists():
                with Image.open(destination) as image:
                    if image.size == (info['w'],info['h']):
                        return name, dict(info, png=str(destination.resolve()))
            with open(info['pak'],'rb') as source:
                if info.get('is_direct_dds'):
                    data = source.read()
                else:
                    source.seek(info['offset'])
                    data = build_dds(source.read(info['size']),info['w'],info['h'],info['fmtId'],info.get('is_pc',False))
            with Image.open(io.BytesIO(data)) as image:
                assert image.size == (info['w'],info['h'])
                image.save(destination,format='PNG')
            return name, dict(info, png=str(destination.resolve()))
        except Exception as exc:
            return name, {'error':str(exc), 'source':info}
    manifest={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,(name,entry) in enumerate(pool.map(decode,names),1):
            manifest[name]=entry
            if i % 50 == 0:
                print('HQ textures',i,'/',len(names),flush=True)
    (folder/'texture_hq_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    errors={k:v for k,v in manifest.items() if 'error' in v}
    print('Decoded',len(manifest)-len(errors),'errors',errors,flush=True)


if __name__ == '__main__':
    upgrade(Path(sys.argv[1]).resolve())
