"""Extract door interaction evidence; never invent character alignment transforms.

Positions use original Y-up coordinates. An animation locator is a shared
reference frame, not necessarily the player's feet position or a hand target.
"""
import struct
import math
from .pak_reader import PakFile
from .skeleton_reader import SkeletonReader
from .anim_reader import AnimationReader, q_conj, q_mul, q_rot_vec
from research.streaming.visibility_base import string_id


def spawner_records(pak):
    """PS4 SPAWNER_GROUP placements and typed override dictionaries."""
    if pak.magic not in (2681, 68217, 2147486329):
        raise ValueError('Only PS4 spawner layout is supported')
    item = pak.get_first_item('SPAWNER_GROUP')
    if item is None:
        return []

    def require(offset, size):
        if not 0 <= offset <= pak.size - size:
            raise ValueError('Spawner data outside PAK')

    def pointer(field):
        require(field, 8)
        if field not in pak.pointer_page_ids:
            raise ValueError(f'Missing spawner relocation at {field:#x}')
        value = pak.read_ptr(field)
        require(value, 1)
        return value

    base = item.abs_offset
    require(base, 0x34)
    count = struct.unpack_from('<I', pak.data, base + 0x30)[0]
    if count > 5000:
        raise ValueError('Invalid spawner count')
    if not count:
        return []
    array = pointer(base + 0x28)
    require(array, count * 8)
    result = []
    for index in range(count):
        actor = pointer(array + index * 8)
        require(actor, 0x90)
        name = pak.read_str_at(pointer(actor + 0x20))
        record = {'name': name, 'id': f'0x{string_id(name):08x}',
                  'source_offset': actor,
                  'position': list(struct.unpack_from('<3f', pak.data, actor)),
                  'rotation_xyzw': list(struct.unpack_from('<4f', pak.data, actor + 0x10)),
                  'properties': []}
        if actor + 0x68 in pak.pointer_page_ids:
            dictionary = pointer(actor + 0x68)
            require(dictionary, 16)
            size = struct.unpack_from('<I', pak.data, dictionary + 8)[0]
            if size > 4096:
                raise ValueError('Invalid spawner property count')
            table = pointer(dictionary) if size else 0
            require(table, size * 16)
            for prop_index in range(size):
                row = table + prop_index * 16
                key = struct.unpack_from('<I', pak.data, row)[0]
                header = pointer(row + 8)
                require(header, 16)
                value_type, declared_size = struct.unpack_from('<HH', pak.data, header)
                payload = pointer(header + 8)
                prop = {'key': f'0x{key:08x}', 'type': value_type,
                        'declared_size': declared_size, 'source_offset': row,
                        'payload_offset': payload}
                if value_type in (1, 4, 13):
                    require(payload, 4)
                    raw = pak.data[payload:payload + 4]
                    prop['raw_hex'] = raw.hex()
                    if value_type == 4:
                        prop['value'] = struct.unpack('<f', raw)[0]
                    elif value_type == 13:
                        prop['symbol_id'] = f'0x{struct.unpack("<I", raw)[0]:08x}'
                    else:
                        prop['value'] = struct.unpack('<i', raw)[0]
                elif value_type == 5:
                    # Pointer wrapper; declared_size describes the string,
                    # not bytes adjacent to the wrapper.
                    prop['string'] = pak.read_str_at(pointer(payload))
                else:
                    prop['status'] = 'unresolved_value_type'
                record['properties'].append(prop)
        result.append(record)
    return result


def rig_anchors(path):
    pak = PakFile(str(path))
    skeleton = SkeletonReader.read_skeleton(pak)
    return {'source': str(path), 'rig_id': f'0x{skeleton.native_rig_id:08x}',
            'anchors': [{'name': bone.name, 'parent': skeleton.bones[bone.parent_index].name
                         if bone.parent_index >= 0 else None,
                         'local_translation': list(bone.translation),
                         'local_rotation_xyzw': list(bone.rotation),
                         'role': 'hand_ik_target'} for bone in skeleton.bones
                        if bone.name.startswith('handle_ik_')]}


def paired_clips(bank_path, character_rig, door_rig, character_name, door_name):
    """Preserve both native curves including root motion for offline alignment."""
    bank = PakFile(str(bank_path))
    result = {'source': str(bank_path), 'clips': []}
    for role, rig_path, name in [('character', character_rig, character_name),
                                 ('door', door_rig, door_name)]:
        skeleton = SkeletonReader.read_skeleton(PakFile(str(rig_path)))
        item = next(i for i in bank.get_items('ANIM') if i.name == name)
        clip = AnimationReader._parse_clip(bank, item, skeleton)
        if clip is None or clip.unsupported_opcodes:
            raise ValueError('Incomplete paired animation: ' + name)
        result['clips'].append({'role': role, 'name': name,
            'source_offset': item.abs_offset, 'rig_id': f'0x{clip.source_rig_id:08x}',
            'duration': clip.duration, 'fps': clip.fps,
            'animation_entry': animation_entry(bank, item),
            'secondary_stream_decoded': False, 'has_secondary_stream': clip.has_secondary_stream,
            'tracks': [{'bone': skeleton.bones[t.node_index].name, 'path': t.target_path,
                        'times': t.timestamps, 'values': t.values} for t in clip.tracks]})
    if abs(result['clips'][0]['duration'] - result['clips'][1]['duration']) > 1e-5:
        raise ValueError('Paired clip durations disagree')
    character_entry, door_entry = [c['animation_entry'] for c in result['clips']]
    if character_entry and door_entry:
        # ActorWorld = SharedLocatorWorld * inverse(DoorApReference).
        # CharacterWorld = SharedLocatorWorld * inverse(CharacterApReference).
        # Hence CharacterWorld = ActorWorld * DoorApReference * inverse(CharacterApReference).
        result['character_relative_to_door_actor'] = compose_rigid(
            door_entry['ap_reference'], character_entry['relative_to_shared_locator'])
    return result


def compose_rigid(left, right):
    rotation = q_mul(left['rotation_xyzw'], right['rotation_xyzw'])
    delta = q_rot_vec(left['rotation_xyzw'], right['position'])
    return {'position': [a+b for a,b in zip(left['position'], delta)],
            'rotation_xyzw': list(rotation)}


def inverse_rigid(transform):
    rotation = q_conj(transform['rotation_xyzw'])
    return {'position': list(q_rot_vec(rotation, [-v for v in transform['position']])),
            'rotation_xyzw': list(rotation)}


def animation_entry(pak, item):
    """Native get-animation-entry at time 0, apReference auxiliary channel.

    eboot file offsets: wrapper 0x9c78c0; inverse composition 0x9e7490;
    channel dictionary 0x9fe2d0; first transform sampler 0x9fd460/0x9fcb20.
    This does not read the AC primary bone pose or estimate alignment from IK.
    Alternate encodings fail explicitly instead of becoming guessed transforms.
    """
    def pointer(field):
        if field not in pak.pointer_page_ids:
            raise ValueError(f'Missing animation reference relocation at {field:#x}')
        value = pak.read_ptr(field)
        if not 0 < value < pak.size:
            raise ValueError('Animation reference outside PAK')
        return value

    if item.abs_offset + 0x30 not in pak.pointer_page_ids:
        return None
    table = pointer(item.abs_offset + 0x30)
    if table + 24 > pak.size:
        raise ValueError('Truncated animation reference dictionary')
    count = struct.unpack_from('<I', pak.data, table)[0]
    if not 0 < count <= 4096:
        raise ValueError('Invalid animation reference channel count')
    keys, values = pointer(table+8), pointer(table+16)
    if keys+count*4 > pak.size or values+count*8 > pak.size:
        raise ValueError('Truncated animation reference channel table')
    for i in range(count):
        if struct.unpack_from('<I',pak.data,keys+4*i)[0] != 0xeb87513f:
            continue
        channel = pointer(values+8*i)
        if channel+16 > pak.size:
            raise ValueError('Truncated apReference curve')
        frames, flags = struct.unpack_from('<HH',pak.data,channel)
        # Verified float32 quaternion and XYZ translation encodings. Other
        # encodings require their own decoder, not the bone codec.
        if not frames or not flags & 0x100 or flags & 0x1:
            raise ValueError(f'Unsupported apReference encoding {flags:#x}')
        payload = pointer(channel+8)
        if payload+28 > pak.size:
            raise ValueError('Truncated apReference first sample')
        q = list(struct.unpack_from('<4f',pak.data,payload))
        position = list(struct.unpack_from('<3f',pak.data,payload+16))
        length = math.hypot(*q)
        if not all(math.isfinite(v) for v in q+position) or abs(length-1) > .005:
            raise ValueError('Invalid apReference transform')
        q = [v/length for v in q]
        transform = {'position':position, 'rotation_xyzw':q}
        return {'channel':'apReference', 'channel_id':'0xeb87513f',
                'channel_offset':channel, 'sample_offset':payload,
                'flags':f'0x{flags:04x}', 'frame_count':frames, 'sample_time':0.0,
                'ap_reference':transform,
                'relative_to_shared_locator':inverse_rigid(transform),
                'semantics':'locator_world * inverse(ap_reference_at_time_0)',
                'evidence':'PS4 eboot 0x9c78c0 -> 0x9e7860 -> 0x9e7490'}
    return None


def symbol_references(data, names):
    """CRC occurrences are evidence of a reference, not proof of its VM role."""
    result = []
    for name in names:
        symbol = string_id(name)
        raw = struct.pack('<I', symbol)
        offsets = []
        cursor = 0
        while (cursor := data.find(raw, cursor)) >= 0:
            offsets.append(cursor)
            cursor += 1
        if offsets:
            result.append({'name': name, 'symbol_id': f'0x{symbol:08x}', 'offsets': offsets})
    return result
