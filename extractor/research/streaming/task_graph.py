"""DC00 task graph reader, using pointers and IDs rather than string order."""
import struct
from .visibility_base import string_id


def read_task_graphs(data):
    if data[:8] != b'00CD\x01\0\0\0':
        raise ValueError('Unsupported task DC00 file')
    def u32(offset): return struct.unpack_from('<I', data, offset)[0]
    def ptr(offset):
        value = struct.unpack_from('<Q', data, offset)[0]
        if not 0 < value < len(data): raise ValueError('Invalid task pointer')
        return value
    def name(offset):
        end = data.index(0, offset)
        return data[offset:end].decode('ascii')
    # Global symbol 6e51b48f is a sorted graph dictionary (type 832a49d8).
    entry = next((ptr(32+i*16+8) for i in range(u32(20))
                  if u32(32+i*16) == 0x6e51b48f and u32(36+i*16) == 0x832a49d8), None)
    if entry is None: raise ValueError('Task graph dictionary absent')
    table = ptr(entry)
    count = u32(table)
    objects = ptr(table+16)
    if count > 10000: raise ValueError('Invalid task graph count')
    result = {}
    for index in range(count):
        root = ptr(objects+8*index)
        chapter = name(ptr(root))
        chapter_id = u32(root+8)
        world = name(ptr(root+16)) if u32(root+16) else None
        if string_id(chapter) != chapter_id or (world and string_id(world) != u32(root+24)):
            raise ValueError('Task graph name hash mismatch')
        nodes_table, edges_table = ptr(root+32), ptr(root+40)
        n, e = u32(nodes_table), u32(edges_table)
        if n > 100000 or e > 100000: raise ValueError('Invalid task graph size')
        keys, values, edge_data = ptr(nodes_table+8), ptr(nodes_table+16), ptr(edges_table+8)
        nodes = {}
        for j in range(n):
            symbol = u32(keys+4*j)
            node = ptr(values+8*j)
            label = name(ptr(node))
            if u32(node+8) != symbol or string_id(label) != symbol:
                raise ValueError('Task node name hash mismatch')
            nodes[f'0x{symbol:08x}'] = {'name': label, 'offset': node}
        edges = [{'from': f'0x{u32(edge_data+8*j):08x}',
                  'to': f'0x{u32(edge_data+8*j+4):08x}', 'offset': edge_data+8*j}
                 for j in range(e)]
        result[chapter] = {'id': f'0x{chapter_id:08x}', 'world': world, 'offset': root,
                           'nodes': nodes, 'edges': edges,
                           'note': 'Graph connectivity, not automatic completion or a positional trigger.'}
    return result
