#!/usr/bin/env python3
"""
serve.py - Local high-resolution texture & model server for TLOU 3D Asset Viewer
Automatically indexes texture dictionaries in D:\\TLOUPS4\\Extracted\\texturedict1
and serves high-resolution (512px - 2048px) PNG textures on-demand to the WebGL viewer.
"""

import os
import io
import re
import json
import struct
import mimetypes
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from PIL import Image
try:
    from pyswizzle import ps4_deswizzle
except ImportError:
    ps4_deswizzle = None

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_INDEX_FILE = os.path.join(WORKSPACE_DIR, "texture_index.json")

def texture_directories():
    """Discover extracted chapters and shared dictionaries beside them."""
    root = os.environ.get('TLOU_ASSET_ROOT', r'D:\TLOUPS4')
    roots = [root]
    if os.path.isdir(root):
        roots += [os.path.join(root, n) for n in sorted(os.listdir(root))
                  if os.path.isdir(os.path.join(root, n))]
    return [os.path.join(r, sub) for r in roots for sub in ('texturedict1', 'pak32', 'actor50')
            if os.path.isdir(os.path.join(r, sub))]


def texture_sources(folders):
    sources = []
    for folder in folders:
        for entry in sorted(os.scandir(folder), key=lambda e: e.name):
            if entry.is_file() and entry.name.lower().endswith(('.pak', '.dds')):
                stat = entry.stat()
                sources.append([entry.path, stat.st_size, stat.st_mtime_ns])
    return sources


def resolve_texture(index, tex_hash='', tex_name=''):
    # A material hash identifies an exact texture. Never replace a missing hash
    # with a similarly named asset from another chapter.
    if tex_hash:
        return index.get(tex_hash.lower().strip())
    name = re.sub(r'\.(tga|dds|png|ndb)$', '', tex_name.lower().strip())
    return index.get(name) if name else None


# Supported formats mapping for DDS header
FOURCC_MAP = {
    0x40: b'DXT1', 0x46: b'DXT1', 0x47: b'DXT1', 0x48: b'DXT1', 71: b'DXT1',
    0x49: b'DXT3', 0x4A: b'DXT3', 0x4B: b'DXT3', 74: b'DXT3',
    0x4C: b'DXT5', 0x4D: b'DXT5', 0x4E: b'DXT5', 77: b'DXT5',
    0x4F: (True, 80), 0x50: (True, 80), 0x51: (True, 80), 80: (True, 80), # BC4
    0x52: (True, 83), 0x53: (True, 83), 0x54: (True, 83), 83: (True, 83), # BC5
    0x55: (True, 98), 0x56: (True, 98), 0x57: (True, 98), # BC7 (PS4)
    0x5E: (True, 95), 0x5F: (True, 95), 0x60: (True, 96), # BC6H (PC)
    0x61: (True, 98), 0x62: (True, 98), 0x63: (True, 99), 98: (True, 98), 99: (True, 99), # BC7 (PC)
    0x1C: (True, 28), 0x1D: (True, 28), 0x1E: (True, 28), 28: (True, 28), 29: (True, 28), 30: (True, 28), # R8G8B8A8
    0x23: (True, 28), 35: (True, 28), # R8G8B8A8 / B8G8R8A8
    0x5B: (True, 28), 91: (True, 28), # 32bpp uncompressed
}

def build_dds(raw_bytes: bytes, width: int, height: int, fmt_id: int, is_pc: bool = False) -> bytes:
    from tlou_extractor.texture_dds import build_dds as wrap_dds
    return wrap_dds(raw_bytes, width, height, fmt_id, is_pc)


def build_texture_index():
    folders = texture_directories()
    sources = texture_sources(folders)
    metadata_path = CACHE_INDEX_FILE + '.sources.json'
    if os.path.exists(CACHE_INDEX_FILE):
        try:
            with open(CACHE_INDEX_FILE, 'r', encoding='utf-8') as f:
                index = json.load(f)
                hex_keys_found = any(len(k) == 16 and all(c in '0123456789abcdef' for c in k.lower()) for k in list(index.keys())[:100])
                with open(metadata_path, 'r', encoding='utf-8') as meta:
                    cache_valid = json.load(meta) == sources
                if index and hex_keys_found and cache_valid:
                    print(f"[Server] Loaded {len(index):,} textures from cache ({CACHE_INDEX_FILE})")
                    return index
                else:
                    print("[Server] Cache missing 16-hex hash keys, rebuilding index...")
        except Exception as e:
            print("[Server] Cache read error, rebuilding index...", e)

    print("[Server] Scanning texture dictionaries...")
    index = {}

    from tlou_extractor.pak_reader import PakFile

    for folder in folders:
        if not os.path.exists(folder):
            continue

        # Check loose DDS files in folder
        try:
            for f in os.listdir(folder):
                if f.lower().endswith('.dds'):
                    base = os.path.splitext(f)[0].lower()
                    if base not in index:
                        index[base] = {
                            'pak': os.path.join(folder, f),
                            'is_direct_dds': True,
                            'is_pc': False,
                            'w': 0,
                            'h': 0,
                            'fmtId': 0
                        }
        except Exception:
            pass

        paks = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.pak') and os.path.getsize(os.path.join(folder, f)) > 10000 and ('dict' in f or 'stream' in f or 'common' in f or 'world' in f or 'render' in f or 'tstrm' in f or 'texturedict' in folder.lower())]
        for pak_path in paks:
            try:
                pak = PakFile(pak_path)
                raw = pak.data
                is_pc = pak.magic in (2685, 68221)
                added = 0
                for vd in pak.get_items('VRAM_DESC'):
                    base = vd.abs_offset
                    if is_pc:
                        inline_path = pak.read_str_at(base + 112, 300) or pak.read_str_at(base + 96, 300)
                    else:
                        inline_path = pak.read_str_at(base + 96, 300) or pak.read_str_at(base + 112, 300) or pak.read_str_at(base + 0x60, 300) or pak.read_str_at(base + 0x70, 300)
                    if not inline_path:
                        continue
                    parts = inline_path.replace('\\', '/').split('/')
                    cand = parts[-1]
                    if re.search(r'\.ndb$', cand, re.I) and len(parts) >= 2:
                        cand = parts[-2]
                    tga = re.sub(r'\.(tga|dds|ndb)$', '', cand, flags=re.I).lower().strip()
                    if not tga:
                        continue

                    m = re.search(r'([0-9a-fA-F]{16})', inline_path)
                    hex_hash = m.group(1).lower() if m else None

                    if is_pc:
                        tw = struct.unpack_from('<I', raw, base + 84)[0]
                        th = struct.unpack_from('<I', raw, base + 88)[0]
                        fmt_id = struct.unpack_from('<I', raw, base + 72)[0]
                    else:
                        tw = struct.unpack_from('<I', raw, base + 72)[0]
                        th = struct.unpack_from('<I', raw, base + 76)[0]
                        fmt_id = struct.unpack_from('<I', raw, base + 60)[0]
                    pak_offset = struct.unpack_from('<I', raw, base + 40)[0]
                    vram_size = struct.unpack_from('<I', raw, base + 48)[0]

                    if tw <= 0 or th <= 0 or vram_size <= 0:
                        continue

                    abs_tex_offset = pak.raw_data_start + pak_offset
                    if abs_tex_offset + vram_size > len(raw):
                        continue

                    entry = {
                        'pak': pak_path,
                        'w': tw,
                        'h': th,
                        'fmtId': fmt_id,
                        'offset': abs_tex_offset,
                        'size': vram_size,
                        'is_pc': is_pc,
                        'name': tga,
                        'hash': hex_hash or ''
                    }

                    # If already present, only replace if this one has higher resolution
                    existing = index.get(tga)
                    if not existing or tw > existing.get('w', 0) or th > existing.get('h', 0):
                        index[tga] = entry
                        added += 1

                    if hex_hash:
                        existing_h = index.get(hex_hash)
                        if not existing_h or tw > existing_h.get('w', 0) or th > existing_h.get('h', 0):
                            index[hex_hash] = entry
                            index[hex_hash.upper()] = entry
                            added += 1

                if added > 0:
                    print(f"  [+] {os.path.basename(pak_path)}: {added:,} textures (total: {len(index):,})")
            except Exception as e:
                pass

    try:
        with open(CACHE_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f)
        with open(metadata_path, 'w', encoding='utf-8') as meta:
            json.dump(sources, meta)
        print(f"[Server] Saved {len(index):,} textures to {CACHE_INDEX_FILE}")
    except Exception as e:
        print("[Server] Could not write cache:", e)

    return index

GLOBAL_TEX_INDEX = {}

class ViewerHandler(SimpleHTTPRequestHandler):
    def json_reply(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        from tlou_extractor import editor_export
        parsed = urlparse(self.path)
        # Export endpoints accept requests from this local editor only.
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://127.0.0.1:8080', 'http://localhost:8080'):
            self.json_reply({'error': 'Local editor origin required'}, 403)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 512*1024*1024:
                raise ValueError('Export request must be between 1 byte and 512 MB')
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError('Incomplete request')
            if parsed.path == '/api/export-source':
                name = parse_qs(parsed.query).get('name', ['source.pak'])[0]
                self.json_reply({'token': editor_export.save_source(body, name)})
            elif parsed.path == '/api/export-mesh-init':
                self.json_reply({'token': editor_export.begin_mesh_upload()})
            elif parsed.path == '/api/export-mesh':
                token = parse_qs(parsed.query).get('upload', [''])[0]
                self.json_reply({'count': editor_export.append_mesh_upload(token, json.loads(body))})
            elif parsed.path == '/api/export-fbx':
                def texture_loader(tex_hash, tex_name):
                    info = resolve_texture(GLOBAL_TEX_INDEX, tex_hash, tex_name)
                    if not info:
                        return None
                    with open(info['pak'], 'rb') as source:
                        if info.get('is_direct_dds'):
                            data = source.read()
                        else:
                            source.seek(info['offset'])
                            data = build_dds(source.read(info['size']),info['w'],info['h'],info['fmtId'],info.get('is_pc',False))
                    image = Image.open(io.BytesIO(data))
                    output = io.BytesIO(); image.save(output,format='PNG')
                    return output.getvalue()
                token = editor_export.start_job(json.loads(body), texture_loader)
                self.json_reply({'job': token}, 202)
            else:
                self.json_reply({'error': 'Unknown endpoint'}, 404)
        except Exception as exc:
            self.json_reply({'error': str(exc)}, 400)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WORKSPACE_DIR, **kwargs)

    def end_headers(self):
        # Enable CORS for local testing
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        if not any(h.lower().startswith(b'cache-control:') for h in getattr(self, '_headers_buffer', [])):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/export-status':
            from tlou_extractor.editor_export import JOBS
            job = JOBS.get(parse_qs(parsed.query).get('job', [''])[0])
            self.json_reply(job or {'error': 'Unknown export'}, 200 if job else 404)
            return
        if parsed.path == '/api/texture':
            qs = parse_qs(parsed.query)
            tex_hash = qs.get('hash', [''])[0].lower().strip()
            tex_name = qs.get('name', [''])[0].lower().strip()
            # Clean up extensions or suffixes
            tex_name = re.sub(r'\.(tga|dds|png|ndb)$', '', tex_name)

            tex_info = resolve_texture(GLOBAL_TEX_INDEX, tex_hash, tex_name)

            if not tex_info:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                self.wfile.write(json.dumps({'error': f'Texture not found: {tex_name}'}).encode('utf-8'))
                return

            try:
                tw, th = tex_info.get('w', 0), tex_info.get('h', 0)
                if tex_info.get('is_direct_dds'):
                    with open(tex_info['pak'], 'rb') as f:
                        dds_bytes = f.read()
                    img = Image.open(io.BytesIO(dds_bytes))
                    tw, th = img.size
                else:
                    # Read texture bytes directly from pak
                    with open(tex_info['pak'], 'rb') as f:
                        f.seek(tex_info['offset'])
                        raw_bytes = f.read(tex_info['size'])

                    dds = build_dds(raw_bytes, tw, th, tex_info['fmtId'], is_pc=tex_info.get('is_pc', False))
                    img = Image.open(io.BytesIO(dds))

                buf = io.BytesIO()
                img.save(buf, format='PNG')
                png_bytes = buf.getvalue()

                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Content-Length', str(len(png_bytes)))
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.send_header('X-Texture-Resolution', f"{tw}x{th}")
                self.end_headers()
                self.wfile.write(png_bytes)
                return
            except Exception as e:
                import traceback
                print(f"[Server ERROR] Failed serving texture '{tex_name}': {e}")
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
                return

        elif parsed.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'online',
                'indexedTextures': len(GLOBAL_TEX_INDEX)
            }).encode('utf-8'))
            return

        elif parsed.path == '/' or parsed.path == '/viewer':
            self.path = '/viewer.html'

        return super().do_GET()

def main():
    global GLOBAL_TEX_INDEX
    print("=" * 60)
    print("  TLOU PS4 3D Asset Viewer Local Server")
    print("=" * 60)
    GLOBAL_TEX_INDEX = build_texture_index()
    port = 8080
    server = ThreadingHTTPServer(('127.0.0.1', port), ViewerHandler)
    print(f"\n[OK] Server running at http://127.0.0.1:{port}/")
    print(f"[OK] High-res texture API: http://127.0.0.1:{port}/api/texture?name=<texture_name>")
    print("[OK] Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == '__main__':
    main()
