"""Resolve highest indexed mip by exact hash, retaining its source dimensions."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def texture_index():
    path = Path(__file__).resolve().parents[1] / 'texture_index.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


@lru_cache(maxsize=128)
def indexed_texture(key):
    from .texture_handler import TextureInfo
    info = texture_index().get(key)
    if not info or info.get('is_direct_dds'):
        return None
    try:
        with open(info['pak'], 'rb') as source:
            source.seek(info['offset'])
            raw = source.read(info['size'])
        if len(raw) != info['size']:
            return None
        return TextureInfo(name=info['name'], width=info['w'], height=info['h'],
                           fmt_id=info['fmtId'], vram_size=info['size'], pak_offset=info['offset'],
                           tex_hash=int(info['hash'],16), raw_bytes=raw,
                           is_pc=info.get('is_pc',False), hex_hash=info['hash'])
    except (OSError, KeyError, ValueError):
        return None
