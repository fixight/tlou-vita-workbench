"""Evidence-only PS4 REGION_TREE inspection; does not assign opcode semantics.

Run from the repository root with: python -m research.streaming.inspect_regions
The OBJ preserves native Y-up world coordinates. JSON offsets are absolute PAK
offsets, so each interpretation can be checked against the source bytes.
"""
import argparse
import json
import struct
from collections import Counter
from pathlib import Path

import numpy as np

from tlou_extractor.pak_reader import PakFile


def inspect(path):
    pak = PakFile(str(path))
    resource = pak.get_first_item('REGION_TREE')
    if resource is None:
        raise ValueError('No REGION_TREE resource')
    data = pak.data

    def unpack(fmt, offset):
        return struct.unpack_from('<' + fmt, data, offset)

    def string(pointer_field):
        target = pak.read_ptr(pointer_field)
        if pointer_field not in pak.pointer_page_ids or not 0 < target < pak.size:
            raise ValueError(f'Invalid string relocation at {pointer_field:#x}')
        return pak.read_str_at(target)

    regions = []
    table = resource.abs_offset + 0x28
    while table in pak.pointer_page_ids:
        address = pak.read_ptr(table)
        table += 8
        count, event_count = unpack('HH', address + 0x30)
        props_address = pak.read_ptr(address + 0x40)
        region = {
            'name': string(address), 'offset': address,
            'name_id_raw': f'0x{unpack("I", address + 8)[0]:08x}',
            'properties': [], 'events_raw': [], 'shapes': [],
            'native_flags': unpack('H', address + 0xe)[0],
        }
        for i in range(count):
            offset = props_address + i * 16
            key, value_type = unpack('II', offset)
            prop = {'offset': offset, 'key_raw': f'0x{key:08x}',
                    'value_type': value_type}
            if value_type == 3:
                prop['value'] = string(offset + 8)
            else:
                prop['value_raw_hex'] = data[offset + 8:offset + 16].hex()
            region['properties'].append(prop)
        events_address = pak.read_ptr(address + 0x38)
        for i in range(event_count):
            offset = events_address + i * 16
            region['events_raw'].append({
                'offset': offset,
                'key_raw': f'0x{unpack("I", offset)[0]:08x}',
                'record_hex': data[offset:offset + 16].hex(),
                'payload_offset': pak.read_ptr(offset + 8),
                'semantics': 'not decoded',
            })

        shape_address = pak.read_ptr(address + 0x28)
        visited = set()
        while shape_address:
            if shape_address in visited:
                raise ValueError('Cyclic shape list')
            visited.add(shape_address)
            shape_type, face_count = unpack('HH', shape_address + 0x10)
            if shape_type in (0,3):
                from .analytic_shapes import read_analytic
                region['shapes'].append(read_analytic(data,shape_address,shape_type))
                shape_address=pak.read_ptr(shape_address)
                continue
            if shape_type != 1 or not 4 <= face_count <= 64:
                raise ValueError(f'Unsupported shape {shape_type}/{face_count}')
            faces = []
            normal_errors = []
            for i in range(face_count):
                offset = shape_address + 0x20 + i * 0x70
                matrix = np.array(unpack('16f', offset)).reshape(4, 4)
                normal = np.array(unpack('4f', offset + 0x40))
                uv = np.array(unpack('8f', offset + 0x50)).reshape(4, 2)
                local = np.column_stack((uv, np.zeros(4), np.ones(4)))
                world = local @ np.linalg.inv(matrix)
                if not np.all(np.isfinite(world)) or not np.allclose(world[:, 3], 1):
                    raise ValueError('Invalid reconstructed vertices')
                normal_errors.append(float(np.max(np.abs(normal[:3] - matrix[:3, 2]))))
                faces.append({'offset': offset, 'world_vertices': world[:, :3].tolist(),
                              'world_to_face_matrix_rows': matrix.tolist(),
                              'normal_raw': normal.tolist(), 'local_quad': uv.tolist()})
            vertices = np.array([v for f in faces for v in f['world_vertices']])
            distances = np.linalg.norm(vertices[:, None] - vertices[None, :], axis=2)
            np.fill_diagonal(distances, np.inf)
            nearest_error = float(distances.min(axis=1).max())
            # Independent face records must agree at the corners of the volume.
            # Keep raw vertices: this validates the transform without welding data.
            if max(normal_errors) > 0.0001:
                raise ValueError(f'Geometry validation failed at {shape_address:#x}')
            region['shapes'].append({
                'offset': shape_address, 'shape_type_raw': shape_type,
                'bounds_min': vertices.min(axis=0).tolist(),
                'bounds_max': vertices.max(axis=0).tolist(),
                'max_nearest_corner_error': nearest_error,
                'corner_validation': 'within 0.002' if nearest_error <= 0.002 else 'face seams require review',
                'max_normal_matrix_error': max(normal_errors), 'faces': faces,
            })
            shape_address = pak.read_ptr(shape_address)
        regions.append(region)
        if len(regions) > 10000:
            raise ValueError('Unterminated region table')
    if unpack('Q', table)[0] != 0:
        raise ValueError('Region pointer table does not end with a null')
    from tlou_extractor.streaming_native import read_grid
    grid = read_grid(pak, resource.abs_offset, regions)
    return {'source': str(path.resolve()), 'resource_offset': resource.abs_offset,
            'coordinate_system': 'native world coordinates, Y up',
            'limitations': ['Property keys and event behavior are not decoded.',
                            'Region order is storage order, not traversal order.',
                            'Multiple shapes are preserved; combination rules are not decoded.'],
            'native_grid': grid, 'regions': regions}


def export(result, output):
    output.mkdir(parents=True, exist_ok=True)
    stem = Path(result['source']).stem
    (output / (stem + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    lines = ['# Native Y-up coordinates; research geometry, not runtime triggers.']
    next_vertex = 1
    for region in result['regions']:
        for number, shape in enumerate(region['shapes']):
            lines.append(f'o {region["name"]}__shape_{number}')
            for face in shape['faces']:
                lines.extend('v ' + ' '.join(f'{c:.9g}' for c in v) for v in face['world_vertices'])
                lines.append('f ' + ' '.join(str(next_vertex + i) for i in range(len(face['world_vertices']))))
                next_vertex += len(face['world_vertices'])
    (output / (stem + '.obj')).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    regions = result['regions']
    summary = {'file': stem, 'regions': len(regions),
               'shapes': sum(len(r['shapes']) for r in regions),
               'events': sum(len(r['events_raw']) for r in regions),
               'properties': sum(len(r['properties']) for r in regions),
               'max_corner_error': max(s['max_nearest_corner_error'] for r in regions for s in r['shapes']),
               'property_keys': dict(Counter(p['key_raw'] for r in regions for p in r['properties']))}
    print(json.dumps(summary))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paks', nargs='*', type=Path)
    parser.add_argument('--output', type=Path, default=Path('research/streaming/output'))
    args = parser.parse_args()
    paths = args.paks or [Path(r'D:\TLOUPS4\Extracted\pak32') / (n + '-ingame14.pak')
                         for n in ('world-home', 'hom-house-interior', 'hom-road-suburb')]
    summaries = [export(inspect(path), args.output) for path in paths]
    (args.output / 'summary.json').write_text(json.dumps(summaries, indent=2), encoding='utf-8')
