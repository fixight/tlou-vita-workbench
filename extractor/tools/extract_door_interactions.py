"""Export native placements, hand anchors and paired animation curves to JSON.

Example:
 python tools/extract_door_interactions.py --level LEVEL.pak --bank BANK.pak
   --character-rig SARAH.pak --door-rig DOOR.pak
   --character-clip NAME --door-clip NAME --script CONTROLLER.bin --output out.json

This is evidence for authoring interactions, not an executable gameplay binding.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tlou_extractor.door_interaction_data import (spawner_records, rig_anchors,
                                               paired_clips, symbol_references)
from tlou_extractor.pak_reader import PakFile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level', required=True)
    parser.add_argument('--bank', required=True)
    parser.add_argument('--character-rig', required=True)
    parser.add_argument('--door-rig', required=True)
    parser.add_argument('--character-clip', required=True)
    parser.add_argument('--door-clip', required=True)
    parser.add_argument('--script', action='append', default=[])
    parser.add_argument('--door-actor', help='Exact native door spawner name')
    parser.add_argument('--locator', help='Exact native shared animation locator, if scripted')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    records = spawner_records(PakFile(args.level))
    names = [r['name'] for r in records] + [args.character_clip, args.door_clip]
    # Keep all placements so symbol IDs can be resolved without proximity guesses.
    document = {'schema': 'tlou_native_door_interaction_evidence', 'version': 1,
        'coordinates': 'native_y_up_metres', 'level_source': args.level,
        'spawners': records, 'door_rig': rig_anchors(args.door_rig),
        'paired_animation': paired_clips(args.bank, args.character_rig, args.door_rig,
                                       args.character_clip, args.door_clip),
        'scripts': [{'source': p, 'symbol_references': symbol_references(Path(p).read_bytes(), names)}
                    for p in args.script],
        'limitations': ['A hand IK target is not a player feet position.',
            'Script symbol occurrences do not reconstruct argument semantics or execution order.',
            'Animation entry is decoded at time zero; approach speed and motion warping are not implemented.',
            'Secondary animation streams are not decoded.']}
    if args.door_actor:
        from tlou_extractor.door_interaction_data import compose_rigid
        by_name = {r['name']:r for r in records}
        door = by_name[args.door_actor]
        clips = document['paired_animation']['clips']
        if not all(c['animation_entry'] for c in clips):
            raise ValueError('Paired clip has no apReference')
        if args.locator:
            locator = by_name[args.locator]
            shared = {'position':locator['position'], 'rotation_xyzw':locator['rotation_xyzw']}
            source = {'kind':'native_spawner_locator', 'name':locator['name'],
                      'source_offset':locator['source_offset']}
        else:
            shared = compose_rigid({'position':door['position'], 'rotation_xyzw':door['rotation_xyzw']},
                                   clips[1]['animation_entry']['ap_reference'])
            source = {'kind':'derived_from_native_door_actor_and_apReference',
                      'name':door['name'], 'source_offset':door['source_offset']}
        document['binding'] = {'door_actor':args.door_actor, 'shared_locator':source,
            'shared_locator_transform':shared,
            'character_entry_world':compose_rigid(shared, clips[0]['animation_entry']['relative_to_shared_locator']),
            'door_entry_world':compose_rigid(shared, clips[1]['animation_entry']['relative_to_shared_locator'])}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(str(output.resolve()))


if __name__ == '__main__':
    main()
