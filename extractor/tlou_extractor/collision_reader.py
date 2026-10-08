"""PS4 Havok 2011.3 BV compressed mesh extraction (no generated collision).

Static mesh section layout and quantization cross-checked with Soulstruct-Havok
and Smithbox HKX2; see COLLISION_EXPORT.md for references and supported scope.
"""
import math
import struct


class CollisionFormatError(ValueError):
    pass


def decode_havok_mesh(blob):
    def read(fmt, offset):
        size = struct.calcsize('<' + fmt)
        if offset < 0 or offset + size > len(blob):
            raise CollisionFormatError('Truncated Havok data')
        return struct.unpack_from('<' + fmt, blob, offset)

    if blob[:8] != bytes.fromhex('57e0e05710c0c010') or blob[16:20] != bytes([8, 1, 1, 1]):
        raise CollisionFormatError('Expected 64-bit little-endian Havok packfile')
    if not blob[40:56].startswith(b'hk_2011.3.0'):
        raise CollisionFormatError('Unsupported Havok version')
    sections = []
    for i in range(read('I', 20)[0]):
        offset = 64 + i * 48
        sections.append((blob[offset:offset+20].split(b'\0')[0], read('7I', offset+20)))
    data_index = next((i for i, (name, _) in enumerate(sections) if name == b'__data__'), None)
    if data_index is None:
        raise CollisionFormatError('Missing Havok data section')
    base, local, glob, virtual, exports, imports, end = sections[data_index][1]
    if not 0 <= local <= glob <= virtual <= exports <= imports <= end or base + end > len(blob):
        raise CollisionFormatError('Invalid Havok section bounds')
    fixups = {}
    for off in range(base + local, base + glob, 8):
        src, dst = read('2I', off)
        if src != 0xffffffff:
            if src >= local or dst >= local:
                raise CollisionFormatError('Invalid local fixup')
            fixups[src] = base + dst
    objects = []
    for off in range(base + virtual, base + exports - 11, 12):
        src, sec, name = read('3I', off)
        if src == 0xffffffff:
            continue
        if sec >= len(sections):
            raise CollisionFormatError('Invalid class section')
        at = sections[sec][1][0] + name
        klass = blob[at:at+120].split(b'\0')[0]
        objects.append((src, klass))
    if objects != [(0, b'hkpBvCompressedMeshShape')]:
        raise CollisionFormatError('Unsupported Havok objects: ' + repr(objects))

    def array(offset, fmt):
        count = read('I', base+offset+8)[0]
        if not count:
            return []
        ptr = fixups.get(offset)
        stride = struct.calcsize('<'+fmt)
        if ptr is None or count > 10000000 or ptr + count*stride > base+local:
            raise CollisionFormatError('Invalid Havok array')
        return [read(fmt, ptr+i*stride) for i in range(count)]

    low = read('3f', base+0x60)
    high = read('3f', base+0x70)
    if not all(math.isfinite(v) for v in low+high) or any(a > b for a,b in zip(low,high)):
        raise CollisionFormatError('Invalid collision bounds')
    packed = [x[0] for x in array(0xc0, 'I')]
    shared_bits = [x[0] for x in array(0xd0, 'Q')]
    shared = [tuple(low[j] + ((bits >> shift) & ((1 << width)-1)) *
                    (high[j]-low[j]) / ((1 << width)-1)
                    for j,(shift,width) in enumerate(((0,21),(21,21),(42,22)))) for bits in shared_bits]
    shared_indices = [x[0] for x in array(0xb0, 'H')]
    primitives = array(0xa0, '4B')
    section_count = read('I', base+0x98)[0]
    start = fixups.get(0x90)
    if start is None or start + section_count*96 > base+local:
        raise CollisionFormatError('Invalid mesh sections')
    vertices, faces = [], []
    for i in range(section_count):
        at = start+i*96
        offset = read('3f', at+48)
        scale = read('3f', at+60)
        first, shared_range, primitive_range = read('3I', at+72)
        n_packed, n_shared = read('2B', at+88)
        if (shared_range & 255) != n_packed:
            raise CollisionFormatError('Unsupported shared vertex layout')
        section_vertices = []
        try:
            for j in range(n_packed):
                bits = packed[first+j]
                section_vertices.append(tuple(offset[k]+scale[k]*((bits>>shift)&mask)
                    for k,(shift,mask) in enumerate(((0,2047),(11,2047),(22,1023)))))
            for j in range(n_shared):
                section_vertices.append(shared[shared_indices[(shared_range>>8)+j]])
            origin = len(vertices)
            for j in range(primitive_range & 255):
                a,b,c,d = primitives[(primitive_range>>8)+j]
                if max(a,b,c,d) >= len(section_vertices):
                    raise CollisionFormatError('Collision vertex index outside section')
                if len({a,b,c}) == 3:
                    faces.append([origin+a,origin+b,origin+c])
                if c != d and len({a,c,d}) == 3:
                    faces.append([origin+a,origin+c,origin+d])
        except IndexError as exc:
            raise CollisionFormatError('Collision array index out of bounds') from exc
        # Independent source section bounds validate quantization and sharing.
        section_low, section_high = read('3f', at+16), read('3f', at+32)
        for point in section_vertices:
            if any(not math.isfinite(v) or v < section_low[k]-0.02 or v > section_high[k]+0.02
                   for k,v in enumerate(point)):
                raise CollisionFormatError('Decoded vertex outside native section bounds')
        vertices.extend(section_vertices)
    if len(faces) != read('I', base+0x80)[0]:
        raise CollisionFormatError('Decoded triangle count differs from native primitive-key count')
    return {'vertices': vertices, 'faces': faces, 'bounds': [low,high], 'sections': section_count}


def extract_collisions(pak):
    meshes, raw_files, warnings = [], [], []
    for item in pak.all_items:
        if 'COLLISION' not in item.item_type:
            continue
        name = f'{item.item_type}_{len(raw_files)}'
        if item.item_type != 'COLLISION_DATA_HAVOK_BG':
            warnings.append(f'{item.item_type}: not decoded')
            continue
        try:
            size = struct.unpack_from('<I', pak.data, item.abs_offset+0x2c)[0]
            start = pak.read_ptr(item.abs_offset+0x30)
            if not start or start+size > len(pak.data):
                raise CollisionFormatError('Invalid collision resource bounds')
            blob = pak.data[start:start+size]
            raw_files.append((name+'.hkx', blob))
            mesh = decode_havok_mesh(blob)
            mesh['name'] = 'COLLISION_' + name
            mesh['source_resource'] = item.item_type
            meshes.append(mesh)
        except (CollisionFormatError, struct.error) as exc:
            warnings.append(f'{name}: {exc}')
    return meshes, raw_files, warnings
