"""Join native PS4 cinematic animation chunks from an animstream14 STM.

STM records have a 16-byte identifier followed by a relocated PAK. Each
following chunk repeats the preceding chunk's last sample (30-frame stride).
This reader does not infer script timing, camera cuts or corrective channels.
"""
import re
import struct
from .pak_reader import PakFile
from .anim_reader import AnimationReader, AnimationClip, AnimationTrack
from .anim_codec import AnimationDecodeError, require


def stream_packages(data):
    """Read record boundaries from PAK pages, never scan arbitrary pose bytes."""
    cursor = 0
    while cursor < len(data):
        require(data, cursor, 16 + 0x2c)
        header = cursor + 16
        magic, _, _, _, pages, table = struct.unpack_from('<6I',data,header)
        if magic not in (2681,68217,2147486329) or not 0 < pages <= 4096:
            raise AnimationDecodeError('Unsupported STM package header')
        require(data,header+table,pages*12)
        last_page,size,_=struct.unpack_from('<3I',data,header+table+(pages-1)*12)
        end = header + last_page + size
        if not header < end <= len(data):
            raise AnimationDecodeError('Invalid STM record boundary')
        # Avoid repeatedly copying the remainder of a multi-megabyte stream.
        # Also do not let a relocation escape into the next record.
        pak = PakFile(data[header:end])
        yield cursor, pak
        cursor = end


def read_streamed_clip(bank, item, skeleton, stream_data):
    """Decode a 64-byte parent AC using cached chunk 0 and named STM chunks."""
    start = bank.read_ptr(item.abs_offset + 0x28)
    require(bank.data, start, 0x40)
    if bank.data[start:start+4] != b'\x02\x01CA':
        raise AnimationDecodeError('Unsupported streamed AC header')
    if struct.unpack_from('<I', bank.data, start+8)[0] != 0x40:
        raise AnimationDecodeError('Expected a streamed parent, not an inline clip')
    total = struct.unpack_from('<H', bank.data, start+14)[0]
    fps = struct.unpack_from('<f', bank.data, start+0x1c)[0]
    first_name = item.name + '-chunk-0'
    first = next((i for i in bank.get_items('ANIM') if i.name == first_name), None)
    if first is None:
        raise AnimationDecodeError('Missing cached first cinematic chunk')
    chunks = {0: AnimationReader._parse_clip(bank, first, skeleton)}
    evidence = [{'index': 0, 'source': bank.filepath, 'offset': first.abs_offset}]
    pattern = re.compile(re.escape(item.name) + r'-chunk-(\d+)$')
    for offset, package in stream_packages(stream_data):
        for resource in package.get_items('ANIM'):
            match = pattern.fullmatch(resource.name)
            if not match:
                continue
            index = int(match[1])
            if index in chunks:
                raise AnimationDecodeError('Duplicate cinematic chunk index')
            chunks[index] = AnimationReader._parse_clip(package, resource, skeleton)
            evidence.append({'index': index, 'stm_record_offset': offset,
                             'resource_offset': resource.abs_offset})
    if sorted(chunks) != list(range(len(chunks))):
        raise AnimationDecodeError('Missing cinematic chunk; refusing a shortened clip')
    if len(chunks) < 2:
        raise AnimationDecodeError('No matching cinematic chunks in STM')
    merged = AnimationClip(item.name, (total-1)/fps, fps)
    merged.source_rig_id = chunks[0].source_rig_id
    merged.has_secondary_stream = any(c.has_secondary_stream for c in chunks.values())
    merged.unsupported_opcodes = sorted({op for c in chunks.values() for op in c.unsupported_opcodes})
    merged.stream_chunks = sorted(evidence, key=lambda e: e['index'])
    merged.stream_overlap_max_error = 0.0
    tracks = {}
    frame_offset = 0
    previous_last = {}
    for index, clip in sorted(chunks.items()):
        if clip is None or clip.source_rig_id != merged.source_rig_id or abs(clip.fps-fps) > 1e-5:
            raise AnimationDecodeError('Incompatible cinematic chunk')
        keys = {(t.node_index, t.target_path) for t in clip.tracks}
        if index and keys != set(tracks):
            raise AnimationDecodeError('Cinematic chunk track layout changed')
        frames = round(clip.duration*fps)+1
        if frames < 2 or (index < len(chunks)-1 and frames != 31):
            raise AnimationDecodeError('Unsupported cinematic chunk frame stride')
        for track in clip.tracks:
            key = track.node_index, track.target_path
            destination = tracks.setdefault(key, AnimationTrack(*key))
            if index:
                before, after = previous_last[key], track.values[0]
                # Quaternion q and -q describe the same rotation.
                error = max(abs(a-b) for a,b in zip(before, after))
                if key[1] == 'rotation':
                    error = min(error, max(abs(a+b) for a,b in zip(before, after)))
                merged.stream_overlap_max_error = max(merged.stream_overlap_max_error, error)
            begin = 1 if index else 0
            destination.timestamps.extend((frame_offset+j)/fps for j in range(begin, frames))
            destination.values.extend(track.values[begin:])
            previous_last[key] = track.values[-1]
        frame_offset += frames-1
    if frame_offset+1 != total:
        raise AnimationDecodeError(f'Stream has {frame_offset+1} frames, parent requires {total}')
    merged.tracks = list(tracks.values())
    return merged
