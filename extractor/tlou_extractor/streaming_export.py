"""Blender streaming metadata with explicit unresolved runtime conditions."""
import os
import re
import json
from pathlib import Path

from research.streaming.inspect_regions import inspect
from research.streaming.visibility_base import selector_description, select_levels, string_id
from .pak_reader import PakFile


def task_graphs(game_main=None):
    """Read the original archive when available; cached graphs allow offline export."""
    from research.streaming.psarc import Psarc
    from research.streaming.task_graph import read_task_graphs
    main = game_main or os.environ.get('TLOU_GAME_MAIN')
    if main:
        return read_task_graphs(Psarc(Path(main)/'bin.psarc').read('dc1/tasks.bin'))
    cached = Path(__file__).resolve().parents[1]/'research/streaming/output/task_graphs.json'
    return json.loads(cached.read_text(encoding='utf-8')) if cached.exists() else {}


def level_id(name):
    return re.sub(r'-(?:tstrm|ingame\d*|render)$', '', Path(name).stem)


def asset_folders():
    root = Path(os.environ.get('TLOU_ASSET_ROOT', r'D:\TLOUPS4'))
    roots = [root] + (sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else [])
    return [r / sub for r in roots for sub in ('pak32', 'actor50', 'texturedict1') if (r / sub).is_dir()]


def prepare_streaming(sources, exported_levels=(), folders=None, game_main=None):
    folders = asset_folders() if folders is None else list(map(Path, folders))
    index = {}
    for folder in folders:
        for path in sorted(folder.glob('*')):
            if path.is_file():
                index.setdefault(path.name, path)
    candidates = {name: Path(path) for path, name in sources}
    graphs = task_graphs(game_main)
    # Pair visual PAKs with their gameplay data. Austin association is explicit;
    # do not guess another chapter's world from an abbreviation.
    for name in list(candidates):
        companion = level_id(name) + '-ingame14.pak'
        if companion in index:
            candidates.setdefault(companion, index[companion])
    if any(level_id(name).startswith(('hom-', 'world-home')) for name in candidates):
        if 'world-home-ingame14.pak' in index:
            candidates.setdefault('world-home-ingame14.pak', index['world-home-ingame14.pak'])
    document = {'schema': 'tlou.streaming', 'version': 1, 'coordinate_system': 'native_y_up',
                'regions': [], 'levels': {}, 'warnings': [], 'native_grids': {}, 'task_graphs': graphs,
                'runtime_ready': False,
                'limitations': ['Game-state query implementations and inter-region overrides remain unresolved.',
                               'Cache dependencies are not automatically display targets.',
                               'Geometry export does not reproduce scripted actors, traffic or cinematics.']}
    variant_keys = {string_id(prefix + str(n)): n for n in range(1, 257)
                    for prefix in ('level-', 'level-no-display-')}
    for name, path in candidates.items():
        pak = PakFile(str(path))
        if not pak.get_first_item('REGION_TREE'):
            continue
        try:
            parsed = inspect(path)
        except (ValueError, IndexError) as exc:
            document['warnings'].append(f'{name}: region geometry unsupported: {exc}')
            continue
        document['native_grids'][level_id(name)] = parsed['native_grid']
        for region in parsed['regions']:
            region['id'] = level_id(name) + ':' + region['name']
            region['source_level'] = level_id(name)
            region['source_file'] = name
            region['combination_rule'] = 'union'
            region['callbacks'] = []
            for event in region['events_raw']:
                decoded = selector_description(pak,[dict(event,key_raw='0xf131b5e1')])
                region['callbacks'].append({'event_key':event['key_raw'],
                    'phase':{'0x1157c38c':'enter','0xf131b5e1':'inside','0x5b4bfb24':'exit'}.get(event['key_raw'],'unknown'),
                    'program':decoded})
            props = region['properties']
            level_keys=set(variant_keys)|{0x4f807b48,string_id('level'),string_id('level-no-display')}
            is_streaming = any(int(p['key_raw'], 16) in level_keys for p in props)
            region['type'] = 'streaming_region' if is_streaming else 'gameplay_region'
            if is_streaming:
                variants = {1} | {variant_keys[int(p['key_raw'], 16)] for p in props if int(p['key_raw'], 16) in variant_keys}
                region['selector'] = selector_description(pak, region['events_raw'])
                region['sets'] = {str(n): select_levels(props, n) for n in sorted(variants)}
                for state in region['sets'].values():
                    for target in state['display'] + state['resident_only']:
                        document['levels'].setdefault(target, {})
            document['regions'].append(region)
    pending = list(document['levels'])
    while pending:
        target = pending.pop()
        record = document['levels'][target]
        manifest = index.get(target + '.txt')
        tags = {}
        if manifest:
            for line in manifest.read_text(encoding='utf-8', errors='replace').splitlines():
                key, _, value = line.strip().partition(' ')
                if value:
                    tags.setdefault(key, []).append(value)
        record.update(id=target, manifest=tags, manifest_found=bool(manifest),
                      geometry_exported=target in exported_levels,
                      local_paks=[str(index[n]) for n in (target+'-tstrm.pak', target+'-ingame14.pak') if n in index],
                      cache_dependencies=tags.get('cache', []))
        for dep in record['cache_dependencies']:
            if dep not in document['levels']:
                document['levels'][dep] = {}
                pending.append(dep)
    document['coverage'] = {
        'referenced_levels': len(document['levels']),
        'exported_levels': sorted(exported_levels),
        'levels_without_exported_geometry': sorted(k for k, v in document['levels'].items() if not v['geometry_exported']),
        'missing_manifests': sorted(k for k, v in document['levels'].items() if not v['manifest_found']),
        'conditional_regions': [r['id'] for r in document['regions'] if r.get('selector', {}).get('kind') == 'script_requires_game_state'],
    }
    document['native_contract'] = {
        'position': 'camera world position, native Y-up metres',
        'region_selection': 'first containing, enabled region with positive selector, in original grid order',
        'shape_combination': 'union; signed face planes',
        'task_before': 'not task-complete and not task-active; not a numeric task-index comparison',
        'state_inputs': ['task pending/active/complete','object-spawned?','get-boolean(property,object)'],
        'port_policy': 'load dependencies, wait for readiness, commit display, release unreferenced resources',
        'story_events': 'Enter/inside/exit callbacks are exported; game scripts and cutscenes require host handlers',
    }
    from .trigger_catalog import build_catalog
    document['trigger_catalog']=build_catalog(document)
    return document
