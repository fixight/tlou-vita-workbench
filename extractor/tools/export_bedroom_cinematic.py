"""Extract the native Sarah wake-up/bedroom-phone scene for independent inspection.
Reuses the existing stream decoder and world placement/camera exporters.
"""
import argparse
import json
import shutil
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.streaming.psarc import Psarc
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.skeleton_reader import SkeletonReader
from tlou_extractor.animation_binding import skeleton_library, clip_rig_id
from tlou_extractor.anim_stream_reader import read_streamed_clip
from tlou_extractor.animation_placement import placement_motion
from tlou_extractor.door_interaction_data import animation_entry, compose_rigid, spawner_records, symbol_references
from tlou_extractor.cinematic_camera import extract_camera
from tlou_extractor.cinematic_control import control_track
from tlou_extractor.cli import extract_single_pak
from tools.export_study_cinematic import export_actor, glb_parts


def build(workspace, extracted, image_main, output, house):
    output.mkdir(parents=True, exist_ok=True)
    bank = PakFile(str(extracted / 'actor50/hom1-tstrm.pak'))
    core = Psarc(image_main / 'core.psarc')
    stream_name = 'animstream14/igc-stream-hom1-house-sarah-bedroom-phone.stm'
    stream = core.read(stream_name)
    spawners = spawner_records(PakFile(str(extracted / 'pak32/hom-house-interior-ingame14.pak')))
    locator = next(s for s in spawners if s['name'] == 'ap-hom-hdr-bedroom-phone-1')
    rigs = skeleton_library(extracted / 'actor50')
    manifest = {'title': 'Пробуждение Сары · звонок телефона',
        'description': 'Исходные анимации Сары, телефона, кровати и подушки. Размещение и траектория камеры извлечены из PS4-данных.',
        'coordinate_system': 'native Y-up metres', 'locator': locator,
        'limitations': ['Диалоги, звонок и сценарные события пока не подключены',
            'Вторичные лицевые и корректирующие потоки не восстановлены'],
        'hide_static_prefixes': ['hom-hdr-bed-1_', 'hom-hdr-pillow-1_', 'hom-hdr-phone-1_'],
        'cutaway_height': 33.9, 'actors': {}, 'stages': []}
    stage = {'id': 'wake-phone', 'label': 'Сара просыпается и отвечает на звонок', 'duration': 0, 'actors': []}
    evidence, validation = [], {}
    models = {'sarah': 'sarah', 'phone': 'hom-cordless-phone', 'bed': 'hom-twin-bed', 'pillow': 'hom-twin-pillow'}
    labels = {'sarah': 'Сара', 'phone': 'Телефон', 'bed': 'Кровать', 'pillow': 'Подушка'}
    for actor_id, model in models.items():
        name = 'hom1-house-sarah-bedroom-phone--' + actor_id
        item = next(i for i in bank.get_items('ANIM') if i.name == name)
        if actor_id == 'sarah':
            skeleton = rigs[clip_rig_id(bank, item)]
            source = workspace / 'extracted_models/sarah/sarah.glb'
        else:
            source_pak = extracted / f'actor50/{model}-tstrm.pak'
            skeleton = SkeletonReader.read_skeleton(PakFile(str(source_pak)))
            source = output / f'source_props/{model}/{model}.glb'
            if not source.is_file():
                if not extract_single_pak(str(source_pak), str(output / 'source_props'),
                    root_dir=str(extracted), export_gltf=False, export_dds=False, all_lods=False):
                    raise ValueError('Prop geometry export failed: ' + model)
        if not skeleton or skeleton.native_rig_id != clip_rig_id(bank, item):
            raise ValueError('Native rig mismatch: ' + name)
        clip = read_streamed_clip(bank, item, skeleton, stream)
        if not clip.tracks or clip.unsupported_opcodes:
            raise ValueError('Incomplete animation: ' + name)
        frames = round(clip.duration * clip.fps) + 1
        entry = animation_entry(bank, item)
        motion = placement_motion(bank, item, locator, clip.fps, frames)
        stage['actors'].append({'id': actor_id, 'clip': name, 'duration': clip.duration,
            'world': compose_rigid(locator, entry['relative_to_shared_locator']), 'motion': motion})
        if actor_id == 'sarah':
            stage['camera'] = extract_camera(bank, item, locator, clip.fps, frames)
        stage['duration'] = max(stage['duration'], clip.duration)
        relative = f'{actor_id}/{actor_id}.glb'
        validation[actor_id] = export_actor(source, output / relative, [clip], skeleton)
        manifest['actors'][actor_id] = {'glb': relative, 'label': labels[actor_id]}
        evidence.append({'clip': name, 'bank': bank.filepath, 'offset': item.abs_offset,
            'rig_id': f'0x{skeleton.native_rig_id:08x}', 'frames': frames, 'fps': clip.fps,
            'stream': stream_name, 'stream_chunks': clip.stream_chunks,
            'stream_overlap_max_error': clip.stream_overlap_max_error, 'placement': entry})
    stage['control'] = control_track(stage['duration'])
    manifest['stages'].append(stage)
    # Use the already extracted house, copied for a self-contained scene folder.
    document, _ = glb_parts(house)
    destination = output / 'house'
    destination.mkdir(exist_ok=True)
    shutil.copy2(house, destination / 'house.glb')
    for image in document.get('images', []):
        uri = image.get('uri')
        if uri and not uri.startswith('data:'):
            target = destination / uri
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(house.parent / uri, target)
    manifest['house'] = 'house/house.glb'
    script_name = 'dc1/ss-home/ss-hom-house-bedroom-phone.bin'
    script = Psarc(image_main / 'bin.psarc').read(script_name)
    names = [e['clip'] for e in evidence] + [locator['name'], 'animate', 'wait-animate']
    references = symbol_references(script, names)
    script_states = [match.decode('ascii') for match in re.findall(
        rb'ss-hom-house-bedroom-phone [a-z-]+ \(on \([a-z]+\)\)', script)]
    # Retain original audio resources without inventing start offsets, localized
    # speech bindings, or pretending that file names describe their contents.
    audio_directory = output / 'audio'
    audio_directory.mkdir(exist_ok=True)
    audio_resources = []
    for name in ('sarah-bedroom-phone-call', 'hom-house-bedroom-phone-dead'):
        source = f'sound1/streams/sfx/{name}.xvag'
        relative = f'audio/{name}.xvag'
        (output / relative).write_bytes(core.read(source))
        audio_resources.append({'source': source, 'file': relative, 'start_time': None,
            'status': 'native_resource; script timing not decoded'})
    manifest['audio_resources'] = audio_resources
    manifest['completion'] = {'control': 'restore_previous',
        'character_pose': 'retain_final_evaluated_world_pose',
        'note': 'Root-joint world pose includes skeletal root and apReference; locator alone is not a spawn point.'}
    for filename, data in [('scene.json', manifest), ('validation.json', validation),
        ('evidence.json', {'clips': evidence, 'script': script_name,
            'symbol_references_not_call_timing': references, 'script_state_labels': script_states})]:
        (output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(output), 'duration': stage['duration'], 'actors': validation}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    workspace = Path(__file__).resolve().parents[1]
    parser.add_argument('--workspace', type=Path, default=workspace)
    parser.add_argument('--extracted', type=Path, default=Path('D:/TLOUPS4/Extracted'))
    parser.add_argument('--game-main', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=workspace / 'output_bedroom_cinematic')
    parser.add_argument('--house', type=Path, default=workspace / 'output_study_cinematic/house/house.glb')
    args = parser.parse_args()
    build(args.workspace, args.extracted, args.game_main, args.output, args.house)
