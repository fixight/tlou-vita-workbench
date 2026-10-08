"""Extract level-set selection from REGION_TREE, following PS4 executable code.

No game scripts are executed. A caller must supply the selector's integer result;
unknown conditions remain explicit in the export rather than defaulting to 1.
"""
import json
import struct
from pathlib import Path

from tlou_extractor.pak_reader import PakFile


def string_id(text):
    """MSB-first CRC32, polynomial 04c11db7, initial 0, no final xor.

    Recovered from eboot file offset 0xc73440 and table 0x11a1880.
    """
    value = 0
    for char in text.encode('ascii'):
        value ^= char << 24
        for _ in range(8):
            value = ((value << 1) ^ (0x04c11db7 if value & 0x80000000 else 0)) & 0xffffffff
    return value


COMMON_DISPLAY_KEY = 0x4f807b48  # Behavior verified; original spelling unknown.
SELECTOR_EVENT_KEY = 0xf131b5e1  # Callback returning integer set index.


def select_levels(properties, selector_result):
    """Select one region's direct levels; does not evaluate spatial/script gates.

    Duplicate no-display entries clear the display flag, matching 0x79e6b2.
    This is not an inter-region merge policy or an unloading scheduler.
    """
    if not isinstance(selector_result, int):
        raise ValueError('An explicit integer selector result is required')
    if selector_result <= 0:
        return {'display': [], 'resident_only': []}
    display_keys = {COMMON_DISPLAY_KEY, string_id(f'level-{selector_result}')}
    resident_keys = {string_id(f'level-no-display-{selector_result}')}
    if selector_result == 1:
        display_keys.add(string_id('level'))
        resident_keys.add(string_id('level-no-display'))
    selected = {}
    for prop in properties:
        key = int(prop['key_raw'], 16)
        if key not in display_keys | resident_keys:
            continue
        if prop['value_type'] != 3:
            raise ValueError('Level property must contain a string')
        name = prop['value']
        display = key in display_keys
        selected[name] = selected.get(name, True) and display
    return {'display': [name for name, display in selected.items() if display],
            'resident_only': [name for name, display in selected.items() if not display]}


def selector_description(pak, events):
    event = next((e for e in events if int(e['key_raw'], 16) == SELECTOR_EVENT_KEY), None)
    if event is None:
        return {'kind': 'constant', 'value': 1, 'reason': 'No selector callback; executable default'}
    payload = event['payload_offset']
    code, constants = pak.read_ptr(payload), pak.read_ptr(payload + 8)
    # In these files the two pointer targets bound a contiguous instruction array.
    # Refuse alternate layout; do not guess a code length from unrelated fields.
    if not 0 < code <= constants <= pak.size or (constants - code) % 4:
        raise ValueError('Unsupported selector instruction layout')
    instructions = []
    for offset in range(code, constants, 4):
        op, a, b, c = struct.unpack_from('4B', pak.data, offset)
        inst = {'pc': (offset - code) // 4, 'offset': offset,
                'opcode': f'0x{op:02x}', 'raw_operands': [a, b, c]}
        if op in (0x15, 0x44):
            value = struct.unpack_from('<I', pak.data, constants + b * 8)[0]
            inst.update(operation='resolve_symbol' if op == 0x15 else 'symbol_id',
                        destination=a, symbol_id=f'0x{value:08x}')
        elif op == 0x0c:
            inst.update(operation='integer', destination=a, value=b | c << 8)
        elif op == 0x43:
            inst.update(operation='copy_register', destination=a, source=b)
        elif op in (0x1b, 0x1c):
            inst.update(operation='call_script' if op == 0x1b else 'call_native',
                        destination=a, function_register=b, argument_count=c,
                        first_argument_register=24)
        elif op in (0x2d, 0x2e, 0x2f):
            inst.update(operation={0x2d: 'jump', 0x2e: 'jump_if_nonzero',
                                   0x2f: 'jump_if_zero'}[op],
                        target=a | c << 8, condition_register=b)
        elif op == 0:
            inst.update(operation='return', source=b)
        else:
            inst['operation'] = 'unknown'
        instructions.append(inst)
    if len(instructions) == 2 and instructions[0]['operation'] == 'integer' and instructions[1]['operation'] == 'return' and instructions[0]['destination'] == instructions[1]['source']:
        return {'kind': 'constant', 'value': instructions[0]['value'],
                'payload_offset': payload, 'instructions': instructions}
    return {'kind': 'script_requires_game_state', 'payload_offset': payload,
            'instructions': instructions,
            'note': 'Calls are decoded structurally but are not evaluated or assigned invented names.'}


def evaluate_selector(selector, queries):
    """Evaluate decoded control flow with explicitly supplied game-state queries.

    queries maps (call_script/call_native, hex symbol ID) to Python callbacks.
    Missing queries fail; game state is never guessed. This is a deliberately
    restricted evaluator for these selectors, not the game's general script VM.
    """
    if selector['kind'] == 'constant':
        return selector['value']
    code = selector['instructions']
    registers = [0] * 40
    pc = 0
    for _ in range(2048):
        if not 0 <= pc < len(code):
            raise ValueError('Selector jumped outside its instruction array')
        inst = code[pc]
        op = inst['operation']
        if op in ('resolve_symbol', 'symbol_id'):
            registers[inst['destination']] = inst['symbol_id']
        elif op == 'integer':
            registers[inst['destination']] = inst['value']
        elif op == 'copy_register':
            registers[inst['destination']] = registers[inst['source']]
        elif op in ('call_script', 'call_native'):
            key = (op, registers[inst['function_register']])
            if key not in queries:
                raise ValueError(f'Unresolved game-state query: {key}')
            count = inst['argument_count']
            if count > 16:
                raise ValueError('Unsupported query argument count')
            registers[inst['destination']] = queries[key](*registers[24:24 + count])
        elif op == 'return':
            value = registers[inst['source']]
            if not isinstance(value, int):
                raise ValueError('Selector did not return an integer')
            return value
        elif op == 'jump' or (op == 'jump_if_zero' and not registers[inst['condition_register']]) or (op == 'jump_if_nonzero' and registers[inst['condition_register']]):
            pc = inst['target']
            continue
        elif op not in ('jump_if_zero', 'jump_if_nonzero'):
            raise ValueError(f'Unsupported selector operation: {op}')
        pc += 1
    raise ValueError('Selector instruction budget exceeded')


def build(report_path, dependencies_path):
    report = json.loads(report_path.read_text(encoding='utf-8'))
    manifests = json.loads(dependencies_path.read_text(encoding='utf-8'))['matched']
    pak = PakFile(report['source'])
    labels = {string_id('comment'): 'comment', COMMON_DISPLAY_KEY: 'common_display__original_name_unknown',
              string_id('level'): 'level', string_id('level-no-display'): 'level-no-display'}
    variants_by_key = {}
    for n in range(1, 257):
        for prefix in ('level-', 'level-no-display-'):
            key = string_id(prefix + str(n))
            labels[key] = prefix + str(n)
            variants_by_key[key] = n
    result = {'source': report['source'],
              'basis': 'Static analysis of original eboot.bin; see eboot_region_selection.asm and README.',
              'limitations': ['Selector callbacks depending on game state are not executed.',
                              'Inter-region priority, level-set overrides, and unload scheduling are not implemented.',
                              'No-display is not asserted to disable scripts, audio or collision.'],
              'regions': []}
    for region in report['regions']:
        if string_id(region['name']) != int(region['name_id_raw'], 16):
            raise ValueError('Region name hash does not match recovered algorithm')
        properties = region['properties']
        variants = {1} | {variants_by_key[int(p['key_raw'], 16)] for p in properties if int(p['key_raw'], 16) in variants_by_key}
        selector = selector_description(pak, region['events_raw'])
        sets = {str(n): select_levels(properties, n) for n in sorted(variants)}
        unclassified = [p for p in properties if p['value_type'] == 3 and int(p['key_raw'], 16) not in labels]
        resource_names = {name for state in sets.values() for names in state.values() for name in names}
        result['regions'].append({
            'name': region['name'], 'offset': region['offset'],
            'geometry_report': report_path.name,
            'selector': selector, 'sets': sets,
            'direct_resource_manifests': {name: manifests.get(name) for name in sorted(resource_names)},
            'unclassified_string_properties': unclassified,
            'property_labels': {p['key_raw']: labels.get(int(p['key_raw'], 16), 'unknown') for p in properties},
        })
    return result


if __name__ == '__main__':
    root = Path(__file__).parent / 'output'
    result = build(root / 'world-home-ingame14.json', root / 'manifest_dependencies.json')
    symbol_file = root / 'selector_symbol_matches.json'
    if symbol_file.exists():
        result['symbol_evidence'] = json.loads(symbol_file.read_text(encoding='utf-8'))
    destination = root / 'world-home-visibility.json'
    destination.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(destination)
    for region in result['regions']:
        print(region['name'], region['selector']['kind'],
              {n: (len(s['display']), len(s['resident_only'])) for n, s in region['sets'].items()})
