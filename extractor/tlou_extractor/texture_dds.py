"""Shared DDS wrapping for VRAM format IDs (DXGI IDs in the inspected PS4 data)."""
import struct
try:
    from pyswizzle import ps4_deswizzle
except ImportError:
    ps4_deswizzle = None


def build_dds(raw, width, height, fmt, is_pc=False):
    if width <= 0 or height <= 0:
        raise ValueError('Invalid texture dimensions')
    legacy = {70:b'DXT1',71:b'DXT1',72:b'DXT1',73:b'DXT3',74:b'DXT3',75:b'DXT3',
              76:b'DXT5',77:b'DXT5',78:b'DXT5'}
    dx10 = {79:80,80:80,81:81,82:83,83:83,84:84,
            94:95,95:95,96:96,97:98,98:98,99:99,
            27:28,28:28,29:29,30:28,35:28,91:91}
    bgra = fmt in (87,88,90,92,93)
    if fmt not in legacy and fmt not in dx10 and not bgra:
        raise ValueError(f'Unsupported VRAM texture format {fmt}; refusing DXT1 fallback')
    pixel = bgra or fmt in (27,28,29,30,35,91)
    bw,bh,bpb = (1,1,4) if pixel else (4,4,8 if fmt in (70,71,72,79,80,81) else 16)
    size = ((width+bw-1)//bw)*((height+bh-1)//bh)*bpb
    if len(raw) < size:
        raise ValueError(f'Truncated texture: {len(raw)} bytes, expected at least {size}')
    raw = raw[:size]
    if not is_pc and width % (bw*8) == 0 and height % (bh*8) == 0:
        if ps4_deswizzle is None:
            raise RuntimeError('pyswizzle is required to decode tiled PS4 textures')
        raw = bytes(ps4_deswizzle(raw, (width,height), (bw,bh), bpb))
    extended = fmt in dx10
    hdr = bytearray(148 if extended else 128)
    hdr[:4] = b'DDS '
    struct.pack_into('<I',hdr,4,124)
    struct.pack_into('<I',hdr,8,0x1|0x2|0x4|0x1000|(0x8 if pixel else 0x80000))
    struct.pack_into('<II',hdr,12,height,width)
    struct.pack_into('<I',hdr,20,width*4 if pixel else size)
    struct.pack_into('<I',hdr,28,1)
    struct.pack_into('<I',hdr,76,32)
    if bgra:
        struct.pack_into('<I',hdr,80,0x40 | (0 if fmt in (88,92,93) else 1))
        struct.pack_into('<IIIII',hdr,88,32,0x00ff0000,0x0000ff00,0x000000ff,
                         0 if fmt in (88,92,93) else 0xff000000)
    else:
        struct.pack_into('<I',hdr,80,4)
        hdr[84:88] = b'DX10' if extended else legacy[fmt]
    struct.pack_into('<I',hdr,108,0x1000)
    if extended:
        struct.pack_into('<IIIII',hdr,128,dx10[fmt],3,0,1,0)
    return bytes(hdr)+raw
