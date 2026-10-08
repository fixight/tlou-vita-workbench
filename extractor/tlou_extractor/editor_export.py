"""Background FBX jobs for the local viewer; inputs are snapshots, not scripts."""
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import uuid
import zipfile
from threading import RLock

from PIL import Image
from .pak_reader import PakFile
from .collision_reader import extract_collisions
from .streaming_export import prepare_streaming, level_id

ROOT = Path(__file__).resolve().parents[1] / 'editor_exports'
JOBS = {}
SOURCES = {}
MESH_UPLOADS = {}
UPLOAD_LOCK = RLock()
POOL = ThreadPoolExecutor(max_workers=1)


def begin_mesh_upload():
    token = uuid.uuid4().hex
    folder = ROOT/'mesh_uploads'/token
    folder.mkdir(parents=True)
    with UPLOAD_LOCK:
        MESH_UPLOADS[token] = []
    return token


def append_mesh_upload(token, mesh):
    if not isinstance(mesh, dict) or not isinstance(mesh.get('positions'), list) or not isinstance(mesh.get('indices'), list):
        raise ValueError('Expected one mesh snapshot')
    with UPLOAD_LOCK:
        paths = MESH_UPLOADS[token]
        path = ROOT/'mesh_uploads'/token/f'{len(paths):06d}.json'
        with path.open('w',encoding='utf-8') as stream:
            json.dump(mesh,stream,ensure_ascii=False)
        paths.append(path)
        return len(paths)


def input_meshes(payload):
    if payload.get('_mesh_paths'):
        for path in payload['_mesh_paths']:
            with path.open(encoding='utf-8') as stream:
                yield json.load(stream)
    else:
        yield from payload.get('meshes', [])


def find_blender():
    candidates = [os.environ.get('BLENDER_PATH'), shutil.which('blender'),
                  r'D:\SteamLibrary\steamapps\common\Blender\blender.exe']
    candidates += [str(p) for p in Path('C:/Program Files/Blender Foundation').glob('Blender*/blender.exe')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise ValueError('Blender not found; set BLENDER_PATH and restart the server')


def save_source(data, name):
    suffix = Path(name).suffix.lower()
    if suffix not in ('.pak', '.glb', '.gltf'):
        raise ValueError('Source must be a PAK, GLB, or GLTF file')
    if suffix == '.pak':
        pak = PakFile(data)  # Validate before saving.
        file_bytes = pak.data
    else:
        file_bytes = data
    token = uuid.uuid4().hex
    folder = ROOT / 'sources'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (token + suffix)
    path.write_bytes(file_bytes)
    SOURCES[token] = (path, Path(name).name)
    return token


def start_job(payload, texture_loader):
    blender = find_blender()
    # Never accept client-provided filesystem paths.
    payload = dict(payload)
    payload.pop('_mesh_paths', None)
    if payload.get('meshUpload'):
        with UPLOAD_LOCK:
            paths = MESH_UPLOADS.get(payload['meshUpload'])
            if not paths:
                raise ValueError('Empty or unknown mesh upload')
            payload['_mesh_paths'] = tuple(paths)
            del MESH_UPLOADS[payload['meshUpload']]
    
    char = payload.get('character') or payload.get('charName') or payload.get('modelName')
    sources = [SOURCES[token] for token in payload.get('sources', [])]
    has_glb = bool(char) or any(Path(name).suffix.lower() in ('.glb', '.gltf') for _, name in sources)

    if not has_glb and not payload.get('_mesh_paths') and (not isinstance(payload.get('meshes'), list) or not payload['meshes']):
        raise ValueError('No geometry to export')
    token = uuid.uuid4().hex
    JOBS[token] = {'state': 'queued', 'message': 'Ожидание экспорта'}
    POOL.submit(_run, token, payload, sources, blender, texture_loader)
    return token


def _run(token, payload, sources, blender, texture_loader):
    folder = ROOT / token
    folder.mkdir(parents=True)
    report = {'warnings': [], 'sources': [], 'collision_meshes': 0, 'collision_triangles': 0,
              'scope': 'Static geometry, native collision and tagged regions with conditional level sets. Game-state bindings and runtime streaming are not fully reconstructed.'}
    try:
        JOBS[token].update(state='running', message='Подготовка геометрии и коллизий')
        scene = {'meshes': [], 'collisions': []}
        texture_cache = {}
        for i,item in enumerate(input_meshes(payload)):
            positions = item['positions']
            indices = item['indices']
            if len(positions)%3 or len(indices)%3 or not all(math.isfinite(v) for v in positions):
                raise ValueError('Invalid mesh vertices or indices')
            vertices = [positions[k:k+3] for k in range(0,len(positions),3)]
            if any(not isinstance(k,int) or k<0 or k>=len(vertices) for k in indices):
                raise ValueError('Mesh index out of bounds')
            mesh = dict(name=str(item.get('name',f'Mesh_{i}'))[:180], vertices=vertices,
                        faces=[indices[k:k+3] for k in range(0,len(indices),3)],
                        material=item.get('texName','Material'))
            mesh['source_mesh'] = str(item.get('name',f'Mesh_{i}'))
            mesh['level_id'] = level_id(item['sourceFile']) if item.get('sourceFile') else ''
            if not mesh['level_id'] and len({level_id(name) for _,name in sources}) == 1:
                mesh['level_id'] = level_id(sources[0][1])
            for src,dst,width in [('normals','normals',3),('uvs','uvs',2)]:
                values = item.get(src, [])
                if len(values)==len(vertices)*width and all(math.isfinite(v) for v in values):
                    mesh[dst] = [values[k:k+width] for k in range(0,len(values),width)]
            key = item.get('texHash') or item.get('texName') or item.get('texture')
            if key and key not in texture_cache:
                png = None
                try:
                    png = texture_loader(item.get('texHash',''),item.get('texName',''))
                except Exception as exc:
                    report['warnings'].append(f'Texture: {exc}')
                if png is None and item.get('texture','').startswith('data:image/'):
                    encoded = item['texture'].split(',',1)[1]
                    image = Image.open(io.BytesIO(base64.b64decode(encoded,validate=True)))
                    stream=io.BytesIO(); image.save(stream,format='PNG'); png=stream.getvalue()
                texture_cache[key] = None
                if png:
                    relative = f'textures/texture_{len(texture_cache):04d}.png'
                    (folder/'textures').mkdir(exist_ok=True)
                    (folder/relative).write_bytes(png)
                    texture_cache[key] = relative
                else:
                    report['warnings'].append(f'No exact texture: {item.get("texName", "")} {item.get("texHash", "")}')
            mesh['texture_path'] = texture_cache.get(key)
            scene['meshes'].append(mesh)
        char = payload.get('character') or payload.get('charName') or payload.get('modelName')
        glb_source = next((path for path, name in sources if Path(name).suffix.lower() in ('.glb', '.gltf')), None)
        glb_path = None
        char_name = char or (Path(glb_source).stem if glb_source else 'model')
        if char:
            cand = Path(__file__).resolve().parents[1] / 'extracted_models' / char / f'{char}.glb'
            if cand.is_file():
                glb_path = cand
        if not glb_path and glb_source and Path(glb_source).is_file():
            glb_path = glb_source

        if glb_path:
            scene['character_glb'] = str(glb_path)
            scene['character_name'] = char_name
            report['character'] = char_name
            report['character_glb'] = str(glb_path)

        for source_index,(path,name) in enumerate(sources):
            if not Path(name).suffix.lower().endswith('.pak'):
                continue
            meshes, raw, warnings = extract_collisions(PakFile(str(path)))
            report['sources'].append({'file':name,'collision_meshes':len(meshes)})
            report['warnings'].extend(f'{name}: {w}' for w in warnings)
            for filename,data in raw:
                (folder/'original_collision').mkdir(exist_ok=True)
                (folder/'original_collision'/f'{source_index}_{filename}').write_bytes(data)
            for mesh in meshes:
                mesh['name'] = f'COLLISION_{source_index}_{len(scene["collisions"])}'
                mesh['collision'] = True
                mesh['level_id'] = level_id(name)
                scene['collisions'].append(mesh)
                report['collision_triangles'] += len(mesh['faces'])
        report['collision_meshes'] = len(scene['collisions'])
        pak_sources = [(p, n) for p, n in sources if Path(n).suffix.lower().endswith('.pak')]
        if pak_sources:
            from .static_lighting import export as export_lighting
            lighting = export_lighting([p for p,n in pak_sources],folder/'static_lighting',
                                       source_names=[n for p,n in pak_sources])
            scene['static_lighting'] = ['static_lighting/lighting.json']
            report['static_lighting_records'] = len(lighting['records'])
            report['static_lighting_warnings'] = lighting['warnings']
            scene['streaming'] = prepare_streaming(pak_sources, {m['level_id'] for m in scene['meshes'] if m['level_id']})
            (folder/'streaming.json').write_text(json.dumps(scene['streaming'],ensure_ascii=False,indent=2),encoding='utf-8')
            report['streaming_regions'] = len(scene['streaming']['regions'])
            report['streaming_coverage'] = scene['streaming']['coverage']
            report['warnings'].extend(scene['streaming']['warnings'])
            if scene['streaming']['coverage']['conditional_regions']:
                report['warnings'].append('Streaming selectors require game-state query bindings; this is not a complete original runtime.')
        if not scene['collisions'] and not glb_path:
            report['warnings'].append('No supported original collision in supplied PAKs. No replacement collision generated.')
        scene_path = folder/'scene.json'
        with scene_path.open('w',encoding='utf-8') as stream:
            json.dump(scene,stream,ensure_ascii=False)
        JOBS[token].update(message='Blender записывает сцену, FBX и анимации')
        with (folder/'blender.log').open('w',encoding='utf-8') as log:
            result = subprocess.run([blender,'--background','--factory-startup','--python-exit-code','1','--python',
                                     str(Path(__file__).with_name('blender_export.py')),'--',str(scene_path)],
                                    stdout=log,stderr=subprocess.STDOUT,timeout=600,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not (folder/'scene.fbx').is_file():
            raise RuntimeError('Blender export failed; see '+str(folder/'blender.log'))
        lighting_report=folder/'static_lighting_report.json'
        if lighting_report.is_file():
            lighting_reports=json.loads(lighting_report.read_text(encoding='utf-8'))
            report['static_lighting_applied']=sum(
                sum(count for mode,count in r['modes'].items() if mode!='no_baked_stream')
                for r in lighting_reports)
            report['static_lighting_experimental']=True
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        with zipfile.ZipFile(folder/'export.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for path in folder.rglob('*'):
                if path.is_file() and path.name not in ('export.zip','scene.json'):
                    archive.write(path,path.relative_to(folder))
        done_msg = f'Готово: персонаж {char_name} (скелет + анимации)' if glb_path else f'Готово: коллизий {len(scene["collisions"])}'
        if report.get('static_lighting_applied'):
            done_msg += f'; статический свет: {report["static_lighting_applied"]} мешей'
        JOBS[token].update(state='done', message=done_msg,
                           url=f'/editor_exports/{token}/export.zip',report=report)
    except Exception as exc:
        JOBS[token].update(state='error',message=str(exc))
