"""Native animation sound notes and localized cinematic voice resources.

Timing of animation notes is authored in frames. Composite speech files keep
pre-roll silence; do not trim it or substitute the first subtitle's time for
stream start. Selection of voices and their scene offset remains explicit.
"""
import math
import struct
from .anim_codec import AnimationDecodeError, require
from research.streaming.visibility_base import string_id


def animation_notes(pak, item, fps):
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('Invalid animation note FPS')
    field = item.abs_offset + 0x48
    if field not in pak.pointer_page_ids:
        return []
    table = pak.read_ptr(field)
    if not table:
        return []
    require(pak.data, table, 16)
    owner, count = struct.unpack_from('<II', pak.data, table)
    if owner != string_id(item.name) or count > 4096:
        raise AnimationDecodeError('Unsupported animation note owner/count')
    events = pak.read_ptr(table + 8)
    require(pak.data, events, count * 24)
    result = []
    for index in range(count):
        offset = events + index * 24
        kind, frame, property_count = struct.unpack_from('<IfI', pak.data, offset)
        if not math.isfinite(frame) or frame < 0 or property_count > 256:
            raise AnimationDecodeError('Invalid animation note')
        payload = pak.read_ptr(offset + 16)
        require(pak.data, payload, property_count * 8)
        properties = dict(struct.iter_unpack('<II', pak.data[payload:payload + property_count * 8]))
        result.append({'offset':offset, 'type_id':kind, 'frame':frame,
                       'time':frame/fps, 'properties':properties})
    return result


def voice_resource(data, name):
    """Resolve a vox-igc global to the native hexadecimal speech archive entry."""
    if data[:8] != b'00CD\x01\0\0\0':
        raise ValueError('Unsupported vox DC file')
    count = struct.unpack_from('<I',data,20)[0]
    require(data,32,count*16)
    key = string_id(name)
    matches = [off for off in range(32,32+count*16,16)
               if struct.unpack_from('<I',data,off)[0] == key]
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous voice binding: '+name)
    offset = matches[0]
    kind, wrapper = struct.unpack_from('<IQ',data,offset+4)
    require(data,wrapper,48)
    if kind != 0xe3825e8d or struct.unpack_from('<I',data,wrapper+20)[0] != 0x0100000d:
        raise ValueError('Unsupported vox binding layout')
    element = struct.unpack_from('<Q',data,wrapper+32)[0]
    require(data,element,32)
    record = struct.unpack_from('<Q',data,element+16)[0]
    require(data,record,12)
    identifier, flags, record_type = struct.unpack_from('<III',data,record)
    if flags != 0x00053c00 or record_type != 0x1ed2e0a2:
        raise ValueError('Unsupported voice record type')
    return {'name':name,'symbol_id':f'0x{key:08x}', 'speech_id':f'{identifier:X}',
            'global_offset':offset,'record_offset':record}


def subtitle_metadata(data):
    if data[:4] != b'XVAG' or len(data) < 32:
        raise ValueError('Expected XVAG')
    end = struct.unpack_from('<I',data,4)[0]
    require(data,0,end)
    offset = 32
    while offset+8 <= end:
        tag,size = struct.unpack_from('<4sI',data,offset)
        require(data,offset+8,size)
        if offset+8+size > end:
            raise ValueError('XVAG chunk overlaps audio')
        payload = data[offset+8:offset+8+size]
        if tag == b'LIPS' and payload[:4] == b'SUBT':
            require(payload,0,32)
            speech,whole_text,language,count = (struct.unpack_from('<I',payload,x)[0] for x in [12,20,24,28])
            if count > 4096 or 32+count*16 != len(payload):
                raise ValueError('Invalid speech subtitle records')
            entries=[]
            for i in range(count):
                line,text,frame,finish=struct.unpack_from('<4I',payload,32+i*16)
                entries.append({'line_id':f'{line:X}','text_id':f'0x{text:08x}',
                                'start_frame':frame,'end_frame':finish})
            return {'speech_id':f'{speech:X}','text_id':f'0x{whole_text:08x}',
                    'language_id':language,'entries':entries}
        offset += 8+size
        if tag == b'0000':break
    return None


def subtitle_text(data, key, encoding='cp1251'):
    count=struct.unpack_from('<I',data)[0]
    base=4+count*8
    require(data,0,base)
    matches=[value for symbol,value in struct.iter_unpack('<II',data[4:base]) if symbol == key]
    if len(matches) != 1:return None
    start=base+matches[0]
    require(data,start,1)
    end=data.find(b'\0',start)
    if end < 0:raise ValueError('Unterminated subtitle text')
    return data[start:end].decode(encoding).replace('_',' ')
