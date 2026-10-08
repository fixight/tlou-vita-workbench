"""Build an Austin Blender workspace and per-level GLBs from extracted PAKs.

python -m tlou_extractor.export_austin_editor --output editor_exports/austin_editor
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import io
import struct

from .collision_reader import extract_collisions
from .editor_export import find_blender
from .level_assembler import LevelAssembler
from .pak_reader import PakFile
from .streaming_export import asset_folders, prepare_streaming


def fill_external_textures(entries, output):
    """Resolve GLB external image references by exact name in the local index."""
    from PIL import Image
    from serve import resolve_texture, build_dds
    index_path = Path(__file__).resolve().parents[1]/'texture_index.json'
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    report = {'resolved': [], 'missing': []}
    cache = {}
    for entry in entries:
        path = Path(entry['path'])
        with path.open('rb') as f:
            f.seek(12)
            size, _ = struct.unpack('<II',f.read(8))
            document = json.loads(f.read(size))
        for image in document.get('images',[]):
            if not image.get('uri') or (path.parent/image['uri']).exists():
                continue
            name = Path(image['uri']).stem
            if name not in cache:
                info = resolve_texture(index, tex_name=name)
                cache[name] = None
                if info:
                    try:
                        with open(info['pak'],'rb') as source:
                            if info.get('is_direct_dds'):
                                data = source.read()
                            else:
                                source.seek(info['offset'])
                                data = build_dds(source.read(info['size']),info['w'],info['h'],info['fmtId'],info.get('is_pc',False))
                        stream = io.BytesIO()
                        Image.open(io.BytesIO(data)).save(stream,format='PNG')
                        cache[name] = stream.getvalue()
                    except Exception as exc:
                        report['missing'].append({'name':name,'error':str(exc)})
            destination = path.parent/image['uri']
            if cache[name]:
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(cache[name])
                report['resolved'].append(str(destination))
            else:
                report['missing'].append({'name':name,'file':str(destination)})
    (output/'texture_completion.json').write_text(json.dumps(report,indent=2))
    return report


def build(output):
    output = output.resolve()
    if (output/'scene.blend').exists():
        raise ValueError('scene.blend already exists. Choose a new --output directory to preserve editor changes.')
    output.mkdir(parents=True, exist_ok=True)
    folders = asset_folders()
    world = next((f/'world-home-ingame14.pak' for f in folders if (f/'world-home-ingame14.pak').exists()), None)
    if world is None:
        raise ValueError('Extract world-home-ingame14.pak first')
    document = prepare_streaming([(world,world.name)], folders=folders)
    assembler = LevelAssembler(str(world.parent.parent))
    scene = {'meshes': [], 'collisions': [], 'level_glbs': [], 'streaming': document}
    report = {'levels': {}, 'warnings': [], 'scope': 'Static Austin geometry, native collision, regions and conditional level sets. No gameplay simulation.'}
    index = {}
    for folder in folders:
        for p in sorted(folder.glob('*.pak')):
            index.setdefault(p.name, p)
    sources = [(world,world.name)]
    for name in sorted(document['levels']):
        # Avoid assembling characters or cached chapter containers as duplicate
        # scenery. Their references remain in the streaming manifest.
        path = index.get(name+'-tstrm.pak')
        if path is None or path.parent.name != 'pak32':
            report['levels'][name] = {'status': 'no_static_level_pak'}
            continue
        pak = PakFile(str(path))
        sources.append((path,path.name))
        meshes, _, warnings = extract_collisions(pak)
        report['warnings'].extend(f'{name}: {w}' for w in warnings)
        for i, mesh in enumerate(meshes):
            mesh.update(name=f'COLLISION_{name}_{i}', collision=True, level_id=name)
            scene['collisions'].append(mesh)
        if not any('GEOMETRY' in i.item_type for i in pak.all_items):
            report['levels'][name] = {'status': 'no_static_geometry_resource'}
            continue
        print('ASSEMBLING', name, flush=True)
        folder = output/'levels'/name
        try:
            stats = assembler.assemble_chunk(name, str(folder), export_glb=True, export_gltf=False,
                                             include_actors=True, all_lods=False)
            scene['level_glbs'].append({'level_id':name,'path':stats['output_glb']})
            if stats.get('static_lighting'):
                scene.setdefault('static_lighting',[]).append(stats['static_lighting'])
            report['levels'][name] = {'status':'exported', 'stats':stats}
        except Exception as exc:
            report['levels'][name] = {'status':'error','message':str(exc)}
            print('LEVEL ERROR',name,str(exc),flush=True)
        (output/'build_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    exported = {entry['level_id'] for entry in scene['level_glbs']}
    (output/'build_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    fill_external_textures(scene['level_glbs'], output)
    scene['streaming'] = prepare_streaming(sources, exported, folders)
    scene['streaming']['asset_bindings'] = {name: f'levels/{name}/{name}.glb' for name in sorted(exported)}
    scene['streaming']['asset_status'] = {name: record['status'] for name,record in report['levels'].items()}
    (output/'streaming.json').write_text(json.dumps(scene['streaming'],indent=2),encoding='utf-8')
    (output/'scene.json').write_text(json.dumps(scene),encoding='utf-8')
    print('BLENDER',len(exported),'levels',flush=True)
    with (output/'blender.log').open('w',encoding='utf-8') as log:
        subprocess.run([find_blender(),'--background','--factory-startup','--python-exit-code','1',
                        '--python',str(Path(__file__).with_name('blender_export.py')),'--',str(output/'scene.json')],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print('DONE',output/'scene.blend',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('editor_exports/austin_editor'))
    build(parser.parse_args().output)
