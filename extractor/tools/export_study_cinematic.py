"""Build an independent study-cinematic test from native animations and APs.

No original assets are overwritten. Stages are individually selectable: their
relative script timing and audio are unresolved. Native camera transforms are
exported separately from the skeletal poses; lens metadata is not interpreted.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.streaming.psarc import Psarc
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.anim_reader import AnimationReader
from tlou_extractor.anim_stream_reader import read_streamed_clip
from tlou_extractor.animation_binding import skeleton_library, clip_rig_id
from tlou_extractor.door_interaction_data import animation_entry, compose_rigid, spawner_records, symbol_references
from tlou_extractor.gltf_writer import GLTFWriter
from tlou_extractor.animation_placement import placement_motion
from tlou_extractor.cinematic_camera import extract_camera
from tlou_extractor.cinematic_control import control_track


def glb_parts(path):
    raw = path.read_bytes()
    size = struct.unpack_from('<I', raw, 12)[0]
    document = json.loads(raw[20:20+size])
    length = struct.unpack_from('<I', raw, 20+size)[0]
    return document, raw[28+size:28+size+length]


def write_glb(path, document, binary):
    encoded = json.dumps(document, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    encoded += b' ' * (-len(encoded) % 4)
    binary = bytes(binary)
    binary += b'\0' * (-len(binary) % 4)
    path.write_bytes(struct.pack('<4sII', b'glTF', 2, 28+len(encoded)+len(binary)) +
                     struct.pack('<I4s', len(encoded), b'JSON') + encoded +
                     struct.pack('<I4s', len(binary), b'BIN\0') + binary)


def export_actor(source, output, clips, skeleton):
    document, binary = glb_parts(source)
    joint_names = {document['nodes'][i]['name']: i for i in document['skins'][0]['joints']}
    if set(joint_names) != set(skeleton.bone_by_name):
        raise ValueError('Geometry skeleton does not match native animation layout')
    old = {s[k] for a in document.get('animations', []) for s in a['samplers'] for k in ('input', 'output')}
    first = min(old) if old else len(document['accessors'])
    geometry = {i for m in document['meshes'] for p in m['primitives'] for i in
                list(p.get('attributes', {}).values()) + ([p['indices']] if 'indices' in p else [])}
    geometry.update(s['inverseBindMatrices'] for s in document['skins'] if 'inverseBindMatrices' in s)
    if max(geometry) >= first or any('bufferView' in i for i in document.get('images', [])):
        raise ValueError('Unsupported GLB geometry/animation buffer layout')
    first_view = min(document['accessors'][i]['bufferView'] for i in old) if old else len(document['bufferViews'])
    prefix = min(v.get('byteOffset', 0) for v in document['bufferViews'][first_view:]) if old else len(binary)
    if any(v.get('byteOffset', 0)+v['byteLength'] > prefix for v in document['bufferViews'][:first_view]):
        raise ValueError('Animation buffer overlaps geometry')
    writer = GLTFWriter(source.stem)
    writer.bin_buffer = bytearray(binary[:prefix])
    writer.accessors = copy.deepcopy(document['accessors'][:first])
    writer.buffer_views = copy.deepcopy(document['bufferViews'][:first_view])
    for clip in clips:
        writer.add_animation(clip, [joint_names[b.name] for b in skeleton.bones])
    document.update(animations=writer.animations, accessors=writer.accessors,
                    bufferViews=writer.buffer_views, buffers=[{'byteLength': len(writer.bin_buffer)}])
    for image in document.get('images', []):
        uri = image.get('uri')
        if uri and not uri.startswith('data:'):
            src = source.parent / uri
            dest = output.parent / uri
            if not src.exists():
                raise FileNotFoundError(src)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_glb(output, document, writer.bin_buffer)
    assert writer.bin_buffer[:prefix] == binary[:prefix]
    return {'geometry_bytes_unchanged': prefix, 'clips': len(clips)}


def build(workspace, extracted, game_main, output, house):
    output.mkdir(parents=True, exist_ok=True)
    actor = extracted / 'actor50'
    banks = {n: PakFile(str(actor / (n+'-tstrm.pak'))) for n in
             ['hom1-house-study', 'hom1-house-study-and-escape']}
    rigs = skeleton_library(actor)
    archive = Psarc(game_main / 'core.psarc')
    scripts = Psarc(game_main / 'bin.psarc')
    spawners = spawner_records(PakFile(str(extracted / 'pak32/hom-house-interior-ingame14.pak')))
    locator = next(s for s in spawners if s['name'] == 'hom-hs-ap-study-1')
    stages = [
        ('study', 'Кабинет: Джоэл входит и ищет оружие', 'hom1-house-study', 'hom1-house-study',
         {'joel': 'hom1-house-study--joel', 'sarah': 'hom1-house-study-enter--sarah'}),
        ('backup', 'Перед нападением: Джоэл зовёт Сару — встречный ракурс',
         'hom1-house-study', 'hom1-house-study-backup',
         {a: 'hom1-house-study-backup--'+a for a in ['joel','sarah']}),
        ('reveal', 'Появление Джимми — фрагмент из дополнительного банка', 'hom1-house-study-and-escape',
         'hom1-house-study-and-escape-05-inf-reveal',
         {a: 'hom1-house-study-and-escape-05-inf-reveal--'+a for a in ['joel','sarah','infected']}),
        ('outro', 'Джимми врывается; продолжение и выход из дома', 'hom1-house-study-and-escape',
         'hom1-house-study-and-escape-outro',
         {a: 'hom1-house-study-and-escape-outro--'+a for a in ['joel','sarah','infected','tommy']})]
    models = {'sarah': 'sarah', 'joel': 'young-joel', 'infected': 'hom-study-infected', 'tommy': 'young-tommy'}
    actor_clips, actor_rigs, evidence = {}, {}, []
    manifest = {'coordinate_system': 'native Y-up metres', 'locator': locator,
                'timing': 'Selectable native fragments; cross-stage timing and gameplay waits are not reconstructed',
                'camera': 'Native animated transform channel; FOV is a preview default',
                'limitations': ['No original audio', 'No secondary facial/corrective streams',
                                'Animated props and glass destruction not restored',
                                'Sarah holds entry pose after her short clip in study stage'],
                'stages': [], 'actors': {}}
    for stage_id, label, bank_name, stream_name, names in stages:
        bank = banks[bank_name]
        stream = None
        stage = {'id': stage_id, 'label': label, 'actors': [], 'duration': 0}
        for actor_id, name in names.items():
            item = next(i for i in bank.get_items('ANIM') if i.name == name)
            skeleton = rigs[clip_rig_id(bank, item)]
            ac = bank.read_ptr(item.abs_offset+0x28)
            if struct.unpack_from('<I', bank.data, ac+8)[0] == 64:
                if stream is None:
                    stream = archive.read('animstream14/igc-stream-'+stream_name+'.stm')
                clip = read_streamed_clip(bank, item, skeleton, stream)
            else:
                clip = AnimationReader._parse_clip(bank, item, skeleton)
            if not clip.tracks or clip.unsupported_opcodes:
                raise ValueError(f'Incomplete primary animation: {name}')
            entry = animation_entry(bank, item)
            if not entry:
                raise ValueError(f'Missing native alignment: {name}')
            world = compose_rigid(locator, entry['relative_to_shared_locator'])
            motion = placement_motion(bank,item,locator,clip.fps,round(clip.duration*clip.fps)+1)
            stage['actors'].append({'id': actor_id, 'clip': name, 'world': world,
                                   'motion': motion, 'duration': clip.duration})
            if actor_id=='joel':
                stage['camera']=extract_camera(bank,item,locator,clip.fps,round(clip.duration*clip.fps)+1)
            stage['duration'] = max(stage['duration'], clip.duration)
            actor_clips.setdefault(actor_id, []).append(clip)
            if actor_id in actor_rigs and actor_rigs[actor_id].native_rig_id != skeleton.native_rig_id:
                raise ValueError('Actor changes skeleton between fragments')
            actor_rigs[actor_id] = skeleton
            evidence.append({'name': name, 'bank': bank.filepath, 'offset': item.abs_offset,
                             'duration': clip.duration, 'frames': round(clip.duration*clip.fps)+1,
                             'rig': f'0x{clip.source_rig_id:08x}', 'entry': entry,
                             'stream_chunks': getattr(clip, 'stream_chunks', []),
                             'stream_overlap_max_error': getattr(clip, 'stream_overlap_max_error', None)})
        stage['control'] = control_track(stage['duration'])
        manifest['stages'].append(stage)
    validation = {}
    for actor_id, clips in actor_clips.items():
        model = models[actor_id]
        source = workspace / f'extracted_models/{model}/{model}.glb'
        relative = f'{actor_id}/{actor_id}.glb'
        validation[actor_id] = export_actor(source, output / relative, clips, actor_rigs[actor_id])
        manifest['actors'][actor_id] = {'glb': relative, 'label':
                                      {'sarah':'Сара','joel':'Джоэл','infected':'Джимми','tommy':'Томми'}[actor_id]}
    # Copy the existing house geometry and its exact external textures.
    house_out = output / 'house'
    house_out.mkdir(exist_ok=True)
    document, _ = glb_parts(house)
    shutil.copy2(house, house_out / 'house.glb')
    for image in document.get('images', []):
        if 'uri' in image and not image['uri'].startswith('data:'):
            dest = house_out / image['uri']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(house.parent / image['uri'], dest)
    manifest['house'] = 'house/house.glb'
    references = []
    names = [e['name'] for e in evidence] + [locator['name'], 'get-spawner-locator','wait-animate','animate']
    for script in ['ss-hom-house-study', 'ss-hom-house-escape']:
        path = 'dc1/ss-home/'+script+'.bin'
        data = scripts.read(path)
        references.append({'script': path, 'crc_references_not_call_timing': symbol_references(data, names),
                           'states': [m.decode('ascii') for m in re.findall(rb'ss-hom-[a-z-]+ [a-z-]+ \(on \([a-z]+\)\)', data)]})
    for filename, data in [('scene.json', manifest), ('evidence.json', {'clips': evidence, 'scripts': references}),
                           ('validation.json', validation)]:
        (output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(output), 'stages': len(stages), 'actors': validation}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--extracted', type=Path, default=Path('D:/TLOUPS4/Extracted'))
    parser.add_argument('--game-main', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path('output_study_cinematic'))
    parser.add_argument('--house', type=Path, default=Path('D:/TLOUPS4/AutomaticLightingHouse/hom-house-interior.glb'))
    args = parser.parse_args()
    build(args.workspace, args.extracted, args.game_main, args.output, args.house)
