"""Prepare level/chunk audio banks on a PC, never inside the rendering loop.
Usage: python3 tools/build_audio_bank.py audio.json exports/assets/audio
Input: PCM16 WAV at 48 kHz, or a single mono/stereo ATRAC9 XVAG stream.
Other WAV formats can be converted offline with --ffmpeg /path/to/ffmpeg.
"""
import argparse
import hashlib
import json
import math
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

HEADER = struct.Struct('<4sIIIIQIII4sQ12s')
BUSES = {'effects': 0, 'dialogue': 1, 'music': 2}
STORAGE = {'resident': 0, 'stream': 1}


def sound_id(name):
    result = 14695981039346656037
    for byte in name.encode('ascii'):
        result = ((result ^ byte) * 1099511628211) & 0xffffffffffffffff
    return result


def text(value):
    data = value.encode('utf-8')
    if not 0 < len(data) <= 1024 or b'\0' in data:
        raise ValueError('Audio name/path length or NUL byte is invalid')
    return struct.pack('<H', len(data)) + data


def pcm_wave(path):
    with wave.open(str(path), 'rb') as audio:
        channels, frames = audio.getnchannels(), audio.getnframes()
        if audio.getframerate() != 48000 or audio.getsampwidth() != 2 or channels not in (1, 2):
            raise ValueError('WAV must be 48 kHz signed PCM16 mono/stereo; use --ffmpeg to convert')
        payload = audio.readframes(frames)
        if not frames or len(payload) != frames * channels * 2:
            raise ValueError('Empty or truncated WAV')
    return HEADER.pack(b'VAS1', 1, 1, 48000, channels, frames, 0, 0, 0,
                       bytes(4), len(payload), bytes(12)) + payload


def atrac9_xvag(data):
    # Container fields follow vgmstream's XVAG parser:
    # https://github.com/vgmstream/vgmstream/blob/master/src/meta/xvag.c
    # Layered/interleaved streams must be flattened offline, not guessed here.
    if len(data) < 32 or data[:4] != b'XVAG' or data[8] & 1:
        raise ValueError('Expected little-endian XVAG')
    start = struct.unpack_from('<I', data, 4)[0]
    if not 32 <= start < len(data):
        raise ValueError('Invalid XVAG payload offset')
    chunks, offset = {}, 32
    while offset + 8 <= start:
        tag, size = struct.unpack_from('<4sI', data, offset)
        if offset + 8 + size > start:
            raise ValueError('Invalid XVAG chunk size')
        chunks[tag] = data[offset + 8:offset + 8 + size]
        offset += 8 + size
        if tag == b'0000':
            break
    fmt, info = chunks.get(b'fmat', b''), chunks.get(b'a9in', b'')
    if len(fmt) < 36 or len(info) < 24:
        raise ValueError('Missing XVAG format / ATRAC9 info')
    channels, codec, frames, _, factor, rate, _, subsongs, layers = struct.unpack_from('<9I', fmt)
    block_bytes, block_frames = struct.unpack_from('<II', info)
    delay = struct.unpack_from('<I', info, 20)[0]
    payload = data[start:]
    # TLOU PS4 can prepend padding and a fake RIFF inside a whole superframe.
    # Mirror xvag_streamfile.h: zero at the block start marks this preamble.
    if block_bytes:
        while len(payload) >= block_bytes and payload[:4] == bytes(4):
            payload = payload[block_bytes:]
    if codec != 9 or rate != 48000 or channels not in (1, 2) or (factor, subsongs, layers) != (1, 1, 1):
        raise ValueError('Only single 48 kHz mono/stereo ATRAC9 XVAG is supported')
    if not 0 < block_bytes <= 1024 or not 0 < block_frames <= 2048 or not frames or \
            len(payload) % block_bytes or frames + delay > len(payload) // block_bytes * block_frames:
        raise ValueError('Invalid ATRAC9 block count/duration')
    return HEADER.pack(b'VAS1', 1, 2, rate, channels, frames, block_bytes, block_frames,
                       delay, info[8:12], len(payload), bytes(12)) + payload


def build(config_path, output, runtime_root='app0:/assets/audio', bank_name='level.vabk', ffmpeg=None):
    config_path, output = Path(config_path), Path(output)
    document = json.loads(config_path.read_text(encoding='utf-8'))
    sounds = document['sounds']
    if not isinstance(sounds, list) or len(sounds) > 4096:
        raise ValueError('Expected at most 4096 sounds')
    if Path(bank_name).name != bank_name or not bank_name.endswith('.vabk'):
        raise ValueError('Bank name must be a simple .vabk filename')
    prepared, entries, report, seen = [], [], [], set()
    for item in sounds:
        name = item['name']
        if not isinstance(name, str) or not name or not name.isascii():
            raise ValueError('Sound names must be nonempty ASCII identifiers')
        identifier = sound_id(name)
        if identifier in seen:
            raise ValueError('Duplicate sound name / ID collision: ' + name)
        seen.add(identifier)
        storage, bus = item.get('storage', 'resident'), item.get('bus', 'effects')
        loop, volume = item.get('loop', False), item.get('volume', 1.0)
        if storage not in STORAGE or bus not in BUSES or not isinstance(loop, bool) or \
                not isinstance(volume, (int, float)) or not math.isfinite(volume) or not 0 <= volume <= 4:
            raise ValueError('Invalid audio storage/bus/loop/volume')
        source = (config_path.parent / item['source']).resolve()
        if source.suffix.lower() == '.xvag':
            data = atrac9_xvag(source.read_bytes())
        elif source.suffix.lower() == '.wav':
            if ffmpeg:
                with tempfile.TemporaryDirectory() as temporary:
                    converted = Path(temporary) / 'sound.wav'
                    command = [ffmpeg, '-v', 'error', '-y', '-i', str(source), '-ar', '48000']
                    if 'channels' in item:
                        if item['channels'] not in (1, 2):
                            raise ValueError('Converted audio must use one or two channels')
                        command += ['-ac', str(item['channels'])]
                    command += ['-c:a', 'pcm_s16le', str(converted)]
                    subprocess.run(command, check=True)
                    data = pcm_wave(converted)
            else:
                data = pcm_wave(source)
        else:
            raise ValueError('Use WAV or a supported XVAG source: ' + str(source))
        # Identical assets shared by adjacent banks get exactly the same path.
        digest = hashlib.sha256(data).hexdigest()[:16]
        filename = f'{identifier:016x}_{digest}.vas'
        prepared.append((filename, data))
        entries.append(text(name) + text(runtime_root.rstrip('/') + '/' + filename) +
                       struct.pack('<BBBBf', STORAGE[storage], BUSES[bus], loop, 0, volume))
        report.append({'name': name, 'id': f'{identifier:016x}', 'file': filename,
                       'storage': storage, 'bus': bus, 'payload_bytes': len(data) - 64})
    resident_bytes = sum(item['payload_bytes'] for item in report if item['storage'] == 'resident')
    budget = document.get('resident_budget_bytes', 8 * 1024 * 1024)
    if not isinstance(budget, int) or budget < 0 or resident_bytes > budget:
        raise ValueError(f'Resident budget exceeded: {resident_bytes} bytes')
    output.mkdir(parents=True, exist_ok=True)
    for filename, data in prepared:
        target = output / filename
        if target.exists() and target.read_bytes() != data:
            raise ValueError('Unexpected audio content hash collision')
        if not target.exists():
            target.write_bytes(data)
    bank = struct.pack('<4sII', b'VAB1', 1, len(sounds)) + b''.join(entries)
    temporary_bank = output / (bank_name + '.tmp')
    temporary_bank.write_bytes(bank)
    temporary_bank.replace(output / bank_name)
    result = {'version': 1, 'resident_bytes': resident_bytes, 'sounds': report}
    (output / (bank_name + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--runtime-root', default='app0:/assets/audio')
    parser.add_argument('--bank', default='level.vabk')
    parser.add_argument('--ffmpeg', help='Optional offline conversion executable')
    args = parser.parse_args()
    print(json.dumps(build(args.config, args.output, args.runtime_root, args.bank, args.ffmpeg), ensure_ascii=False, indent=2))
