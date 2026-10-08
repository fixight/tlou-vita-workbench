"""VTGR v1 diagnostic triggers: little endian, native Y-up metres.

Header: magic, u32 version, u32 records. Each record: u32+UTF8 id,
u32+UTF8 display name, u32 box count, then six float32 per box (min/max).
Multiple volumes are ORed. These bounds do not execute original callbacks,
conditions, native activation flags or task logic.
"""
import math
import struct
from .trigger_catalog import classify


def encode_aabb_triggers(document, level_files=None):
    # Restrict to exported chapter families, not every shared chapter's regions.
    # Keep logic/audio companion PAK areas even if they do not have a mesh chunk.
    levels = level_files if level_files is not None else document.get('levels', {})
    families = {name.split('-', 1)[0] for name in levels if not name.startswith('sky-')}
    records = []
    for region in document['regions']:
        if families and region['source_level'].split('-', 1)[0] not in families:
            continue
        category, _ = classify(region)
        authored = bool(region.get('port_binding'))
        if not authored and (not region.get('callbacks') or category not in ('gameplay', 'dialogue', 'effects')):
            continue
        boxes = []
        for shape in region.get('shapes', []):
            lower, upper = shape['bounds_min'], shape['bounds_max']
            if len(lower) != 3 or len(upper) != 3 or any(
                not math.isfinite(v) for v in [*lower, *upper]
            ) or any(a > b for a, b in zip(lower, upper)):
                raise ValueError('Invalid trigger bounds: ' + region['id'])
            boxes.append((*lower, *upper))
        if boxes:
            records.append((region['id'], region.get('name') or region['id'], boxes))
    if len(records) > 4096 or sum(len(r[2]) for r in records) > 65536:
        raise ValueError('Too many diagnostic trigger records/volumes')
    output = bytearray(struct.pack('<4sII', b'VTGR', 1, len(records)))
    for identity, name, boxes in records:
        if len(boxes) > 1024:
            raise ValueError('Too many volumes: ' + identity)
        for value in (identity, name):
            raw = value.encode('utf-8')
            if len(raw) > 4096 or '\0' in value:
                raise ValueError('Invalid trigger text: ' + identity)
            output.extend(struct.pack('<I', len(raw)))
            output.extend(raw)
        output.extend(struct.pack('<I', len(boxes)))
        for box in boxes:
            output.extend(struct.pack('<6f', *box))
    return bytes(output)
