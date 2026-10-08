"""
texture_handler.py - Extraction, DDS wrapping, and PNG conversion for Naughty Dog PS4 textures.
"""
import struct
import os
import io
import re
from typing import Dict, List, Optional, Tuple, Any
from PIL import Image
from .pak_reader import PakFile, ResItemEntry

try:
    from pyswizzle import ps4_deswizzle
except ImportError:
    ps4_deswizzle = None

# DXGI Format constants
DXGI_FORMAT_R8G8B8A8_UNORM = 28
DXGI_FORMAT_BC1_UNORM = 71
DXGI_FORMAT_BC1_UNORM_SRGB = 72
DXGI_FORMAT_BC2_UNORM = 74
DXGI_FORMAT_BC2_UNORM_SRGB = 75
DXGI_FORMAT_BC3_UNORM = 77
DXGI_FORMAT_BC3_UNORM_SRGB = 78
DXGI_FORMAT_BC4_UNORM = 80
DXGI_FORMAT_BC4_SNORM = 81
DXGI_FORMAT_BC5_UNORM = 83
DXGI_FORMAT_BC5_SNORM = 84
DXGI_FORMAT_BC6H_UF16 = 95
DXGI_FORMAT_BC7_UNORM = 98
DXGI_FORMAT_BC7_UNORM_SRGB = 99

class TextureInfo:
    def __init__(self, name: str, width: int, height: int, fmt_id: int, 
                 vram_size: int, pak_offset: int, tex_hash: int, 
                 raw_bytes: bytes = b"", mip_count: int = 1, is_pc: bool = False,
                 hex_hash: str = ""):
        self.name = name
        self.width = width
        self.height = height
        self.fmt_id = fmt_id
        self.vram_size = vram_size
        self.pak_offset = pak_offset
        self.tex_hash = tex_hash
        self.hex_hash = hex_hash
        self.raw_bytes = raw_bytes
        self.mip_count = mip_count
        self.is_pc = is_pc

    def __repr__(self):
        return f"<Texture '{self.name}' {self.width}x{self.height} fmt={self.fmt_id:#x} size={self.vram_size}>"

class TextureHandler:
    def __init__(self, pak: Optional[PakFile] = None):
        self.textures_by_hash: Dict[Any, TextureInfo] = {}
        self.textures_by_hex: Dict[str, TextureInfo] = {}
        self.textures_by_name: Dict[str, TextureInfo] = {}
        if pak is not None:
            self.load_from_pak(pak)

    def load_from_pak(self, pak: PakFile, streaming_pak: Optional[PakFile] = None):
        """Extracts all VRAM_DESC items from the PAK file (and optional streaming PAK)."""
        source_pak = streaming_pak or pak
        raw_data_start = source_pak.raw_data_start
        pak_data = source_pak.data
        is_pc = source_pak.magic in (2685, 68221)

        vram_items = pak.get_items('VRAM_DESC')
        for item in vram_items:
            res_abs = item.abs_offset
            if res_abs + 80 > len(pak.data):
                continue

            # Read VRAM_DESC payload
            pak_offset = struct.unpack_from('<I', pak.data, res_abs + 40)[0]
            vram_size = struct.unpack_from('<I', pak.data, res_abs + 48)[0]
            if is_pc:
                fmt_id = struct.unpack_from('<I', pak.data, res_abs + 72)[0]
                mip_count = struct.unpack_from('<I', pak.data, res_abs + 80)[0]
                w = struct.unpack_from('<I', pak.data, res_abs + 84)[0]
                h = struct.unpack_from('<I', pak.data, res_abs + 88)[0]
                tex_path = pak.read_str_at(res_abs + 112, 300) or pak.read_str_at(res_abs + 96, 300) or pak.read_str_at(res_abs + 0x60, 300)
            else:
                fmt_id = struct.unpack_from('<I', pak.data, res_abs + 60)[0]
                w = struct.unpack_from('<I', pak.data, res_abs + 72)[0]
                h = struct.unpack_from('<I', pak.data, res_abs + 76)[0]
                mip_count = 1
                tex_path = pak.read_str_at(res_abs + 96, 300) or pak.read_str_at(res_abs + 112, 300) or pak.read_str_at(res_abs + 0x60, 300)

            # Extract true 16-hex hash from tex_path (.../<16HEX_HASH>.ndb)
            hex_hash = ""
            if tex_path:
                m = re.search(r'([0-9a-fA-F]{16})', tex_path)
                if m:
                    hex_hash = m.group(1).lower()

            if hex_hash:
                tex_hash = int(hex_hash, 16)
            else:
                tex_hash = struct.unpack_from('<Q', pak.data, res_abs + 56)[0]
                hex_hash = f"{tex_hash:016x}"

            name = item.name
            if not name or name.startswith("res_") or name.startswith("VRAM_DESC"):
                if tex_path and '/' in tex_path.replace('\\', '/'):
                    parts = tex_path.replace('\\', '/').split('/')
                    cand = parts[-1]
                    if cand.lower().endswith('.ndb') and len(parts) >= 2:
                        cand = parts[-2]
                    name = cand
                else:
                    name = tex_path or f"texture_{hex_hash}"

            # Remove original .tga / .dds extension from base name
            base_name = name
            for ext in ('.tga', '.dds', '.exr', '.png', '.ndb'):
                if base_name.lower().endswith(ext):
                    base_name = base_name[:-len(ext)]
            base_name = base_name.strip()
            if not base_name:
                base_name = f"texture_{hex_hash}"

            # Extract raw texture bytes from raw_data_start + pak_offset
            data_start = raw_data_start + pak_offset
            raw_bytes = b""
            if data_start + vram_size <= len(pak_data):
                raw_bytes = pak_data[data_start : data_start + vram_size]

            # If already indexed, do not overwrite higher resolution with lower resolution mip
            if hex_hash:
                existing = self.textures_by_hex.get(hex_hash.lower())
                if existing is not None and len(existing.raw_bytes) > 0 and existing.vram_size > vram_size:
                    continue
            else:
                existing_name = self.textures_by_name.get(base_name.lower())
                if existing_name is not None and len(existing_name.raw_bytes) > 0 and existing_name.vram_size > vram_size:
                    continue

            tex_info = TextureInfo(
                name=base_name,
                width=w,
                height=h,
                fmt_id=fmt_id,
                vram_size=vram_size,
                pak_offset=pak_offset,
                tex_hash=tex_hash,
                raw_bytes=raw_bytes,
                mip_count=1,
                is_pc=is_pc,
                hex_hash=hex_hash
            )
            self.textures_by_name[base_name.lower()] = tex_info
            self.textures_by_hash[tex_hash] = tex_info
            if hex_hash:
                self.textures_by_hex[hex_hash.lower()] = tex_info
                self.textures_by_hex[hex_hash.upper()] = tex_info
                self.textures_by_hash[hex_hash.lower()] = tex_info
                self.textures_by_hash[hex_hash.upper()] = tex_info

    def get_texture_by_hash(self, hash_val: Any) -> Optional[TextureInfo]:
        """Resolves a texture by 16-hex hash string or integer hash."""
        if not hash_val:
            return None
        from .texture_quality import indexed_texture
        key = f'{hash_val:016x}' if isinstance(hash_val, int) else str(hash_val).lower().strip()
        high = indexed_texture(key)
        if high:
            local = self.textures_by_hex.get(key)
            if local is None or high.width * high.height > local.width * local.height:
                self.textures_by_hex[key] = high
                self.textures_by_name[high.name.lower()] = high
                self.textures_by_hash[key] = high
                self.textures_by_hash[high.tex_hash] = high
        if not hash_val:
            return None
        if isinstance(hash_val, str):
            h_str = hash_val.lower().strip()
            if h_str in self.textures_by_hash:
                return self.textures_by_hash[h_str]
            if h_str in self.textures_by_hex:
                return self.textures_by_hex[h_str]
            try:
                h_int = int(h_str, 16)
                if h_int in self.textures_by_hash:
                    return self.textures_by_hash[h_int]
            except ValueError:
                pass
        elif isinstance(hash_val, int):
            if hash_val in self.textures_by_hash:
                return self.textures_by_hash[hash_val]
            h_str = f"{hash_val:016x}"
            if h_str in self.textures_by_hash:
                return self.textures_by_hash[h_str]
        return None

    def build_dds(self, tex: TextureInfo) -> bytes:
        from .texture_dds import build_dds
        return build_dds(tex.raw_bytes, tex.width, tex.height, tex.fmt_id, tex.is_pc)

    def export_texture(self, tex: TextureInfo, output_dir: str, 
                       export_dds: bool = True, export_png: bool = True) -> Tuple[Optional[str], Optional[str]]:
        """Exports the given texture to DDS and PNG files. Returns (dds_path, png_path)."""
        os.makedirs(output_dir, exist_ok=True)
        dds_path = None
        png_path = None

        existing_png = os.path.join(output_dir, f'{tex.name}.png')
        if export_png and os.path.exists(existing_png):
            with Image.open(existing_png) as previous:
                if previous.width * previous.height >= tex.width * tex.height:
                    existing_dds = os.path.join(output_dir, f'{tex.name}.dds')
                    return existing_dds if os.path.exists(existing_dds) else None, existing_png

        if not tex.raw_bytes:
            return None, None

        dds_bytes = self.build_dds(tex)

        if export_dds:
            dds_filename = f"{tex.name}.dds"
            dds_path = os.path.join(output_dir, dds_filename)
            with open(dds_path, 'wb') as f:
                f.write(dds_bytes)

        if export_png:
            png_filename = f"{tex.name}.png"
            png_path = os.path.join(output_dir, png_filename)
            try:
                img = Image.open(io.BytesIO(dds_bytes))
                img.save(png_path, format="PNG")
            except Exception:
                # If Pillow can't directly convert this DXGI variant, leave dds
                png_path = None

        return dds_path, png_path

    def export_all(self, output_dir: str, export_dds: bool = True, export_png: bool = True,
                   needed_hashes: Optional[Any] = None,
                   needed_names: Optional[Any] = None) -> Dict[str, Dict[str, str]]:
        """Exports loaded textures to the specified folder.
        If needed_hashes or needed_names is provided, only textures matching those filters are exported."""
        results = {}
        target_hashes = {str(h).lower() for h in needed_hashes} if needed_hashes else None
        target_names = {str(n).lower() for n in needed_names} if needed_names else None

        # Gather unique textures
        unique_tex = {}
        for tex in self.textures_by_name.values():
            unique_tex[id(tex)] = tex
        for tex in self.textures_by_hex.values():
            unique_tex[id(tex)] = tex

        for tex in unique_tex.values():
            if target_hashes is not None or target_names is not None:
                match = False
                if target_hashes and tex.hex_hash and tex.hex_hash.lower() in target_hashes:
                    match = True
                if not match and target_names and tex.name and tex.name.lower() in target_names:
                    match = True
                if not match:
                    continue

            dds_p, png_p = self.export_texture(tex, output_dir, export_dds, export_png)
            entry = {
                "name": tex.name,
                "dds": dds_p,
                "png": png_p
            }
            results[tex.name.lower()] = entry
            if tex.hex_hash:
                results[tex.hex_hash.lower()] = entry
        return results
