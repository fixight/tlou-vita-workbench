"""
pak_reader.py - Core parser for Naughty Dog PAK archives (PS4 / TLOU Remastered)
"""
import struct
import os
from typing import Dict, List, Optional, Tuple, Any

class ResItemEntry:
    def __init__(self, page_idx: int, entry_idx: int, name: str, item_name: str, item_type: str, abs_offset: int, size: int = 0):
        self.page_idx = page_idx
        self.entry_idx = entry_idx
        self.name = name
        self.item_name = item_name
        self.item_type = item_type
        self.abs_offset = abs_offset
        self.size = size

    def __repr__(self):
        return f"<ResItem '{self.name}' type={self.item_type} at {self.abs_offset:#x}>"

class PakFile:
    def __init__(self, filepath_or_data: Any):
        if isinstance(filepath_or_data, str):
            self.filepath = filepath_or_data
            with open(filepath_or_data, 'rb') as f:
                self.data = f.read()
        elif isinstance(filepath_or_data, (bytes, bytearray, memoryview)):
            self.filepath = ""
            self.data = bytes(filepath_or_data)
        else:
            raise ValueError("Expected filepath or bytes")

        self.size = len(self.data)
        self.magic = 0
        self.hdr_size = 0
        self.login_tbl_idx = 0
        self.login_tbl_offs = 0
        self.page_count = 0
        self.p_page_entries = 0
        self.num_pf_pages = 0
        self.pf_tbl_offs = 0
        
        self.pages: List[Tuple[int, int, int]] = [] # (offset, size, flags)
        self.pointer_page_ids: Dict[int, int] = {} # fixup_address -> page2_idx
        self.items_by_type: Dict[str, List[ResItemEntry]] = {}
        self.all_items: List[ResItemEntry] = []
        self.raw_data_start = 0

        self._parse_header()
        self._parse_pointer_fixups()
        self._parse_res_items()

    def _parse_header(self):
        if self.size < 0x2C:
            raise ValueError(f"File too small for PAK header ({self.size} bytes)")

        (self.magic, self.hdr_size, self.login_tbl_idx, self.login_tbl_offs,
         self.page_count, self.p_page_entries, self.num_pf_pages, self.pf_tbl_offs) = struct.unpack_from('<8I', self.data, 0)

        # 2681 = 0x0A79, 2685 = 0x0A7D (TLOU Part 1 PC), 68217 = 0x00010A79, etc.
        if self.magic not in (2681, 2685, 68217, 68221, 2147486329):
            raise ValueError(f"Invalid PAK magic {self.magic:#x} ({self.magic})")

        # Read page entries table
        self.pages = []
        for i in range(self.page_count):
            p_offs, p_size, p_flags = struct.unpack_from('<3I', self.data, self.p_page_entries + i * 12)
            self.pages.append((p_offs, p_size, p_flags))

        if self.pages:
            last_page = self.pages[-1]
            self.raw_data_start = last_page[0] + last_page[1]
        else:
            self.raw_data_start = self.size

    def _parse_pointer_fixups(self):
        if self.pf_tbl_offs + 12 > self.size:
            return

        pf_entry_num, pf_data_offs, pf_count = struct.unpack_from('<3I', self.data, self.pf_tbl_offs)
        self.pointer_page_ids = {}

        if pf_data_offs + pf_count * 8 <= self.size:
            for i in range(pf_count):
                p1_idx, p2_idx, ptr_offs = struct.unpack_from('<HHI', self.data, pf_data_offs + i * 8)
                if p1_idx < len(self.pages) and p2_idx < len(self.pages):
                    fixup_addr = ptr_offs + self.pages[p1_idx][0]
                    self.pointer_page_ids[fixup_addr] = p2_idx

    def read_ptr(self, addr: int) -> int:
        """Reads a 64-bit pointer and applies page fixup if registered."""
        if addr + 8 > self.size or addr < 0:
            return 0
        raw_val = struct.unpack_from('<q', self.data, addr)[0]
        if raw_val == 0:
            return 0
        p2_idx = self.pointer_page_ids.get(addr)
        if p2_idx is not None and p2_idx < len(self.pages):
            return raw_val + self.pages[p2_idx][0]
        return raw_val

    def read_str_at(self, offset: int, max_len: int = 512) -> str:
        """Reads null-terminated ASCII string from the given offset."""
        if offset < 0 or offset >= self.size:
            return ""
        end = self.data.find(b'\x00', offset)
        if end == -1 or end - offset > max_len:
            end = min(offset + max_len, self.size)
        try:
            return self.data[offset:end].decode('ascii', errors='replace').strip()
        except:
            return ""

    def _parse_res_items(self):
        self.items_by_type = {}
        self.all_items = []

        is_pc = self.magic in (2685, 68221)
        if is_pc:
            TP1_pakStringIDs = {
                0x50CAF5257D6A140B: "JOINT_HIERARCHY",
                0x349D779A792F45C1: "GEOMETRY_1",
                0xCE3ADE693131B309: "VRAM_DESC",
                0xE7254422A7A8F476: "VRAM_DESC_TABLE",
                0xA2481DA1A5D2CE2B: "TEXTURE_TABLE",
                0x36125D3CFB7F3991: "TEXTURE_DICTIONARY",
                0x4903731234F1BEA6: "PAK_LOGIN_TABLE",
                0x61DE7E6141BC6F2B: "EFFECT_TABLE",
                0x460F497540A29F73: "SPAWNER_GROUP",
                0x596A72779C4C87D: "TAG_INT",
                0x53DE1E1977F9CBA4: "ANIM_GROUP",
                0x791137002DB17EBB: "MATERIAL_TABLE_1",
                0x384ADF724B123839: "FOREGROUND_SECTION_2",
                0x5ADB4A2D2E2A6EB: "COLLISION_DATA_CLOTH",
                0x3A3BB43D817C93DE: "TAG_VEC4",
                0x35EB8812D3A2D576: "TAG_FLOAT",
                0x6A98005088A56C5: "LEVEL_BOUNDING_BOX_DATA",
                0x438E1B0DBFFAA93: "AMBSHADOWS_OCCLUDER_INFO",
                0x7D9BFD5CEC879080: "COLLISION_DATA_FOREGROUND",
                0xEC3AFEDF7EF282F0: "SOUND_BANK_TABLE",
            }
            if self.login_tbl_idx < len(self.pages):
                login_start = self.pages[self.login_tbl_idx][0] + self.login_tbl_offs
                res_padding = 48
                if login_start + res_padding + 4 <= self.size:
                    login_cnt = struct.unpack_from('<I', self.data, login_start + res_padding)[0]
                    for i in range(login_cnt):
                        entry_addr = login_start + 56 + i * 8
                        if entry_addr + 8 > self.size:
                            break
                        page, offs = struct.unpack_from('<2I', self.data, entry_addr)
                        if page >= len(self.pages):
                            continue
                        res_abs = self.pages[page][0] + offs
                        if res_abs + 40 > self.size:
                            continue
                        type_id = struct.unpack_from('<Q', self.data, res_abs + 32)[0]
                        item_type = TP1_pakStringIDs.get(type_id, "")
                        if item_type:
                            entry = ResItemEntry(
                                page_idx=page,
                                entry_idx=i,
                                name="",
                                item_name="",
                                item_type=item_type,
                                abs_offset=res_abs
                            )
                            self.all_items.append(entry)
                            if item_type not in self.items_by_type:
                                self.items_by_type[item_type] = []
                            self.items_by_type[item_type].append(entry)

                            if item_type in ("TEXTURE_TABLE", "TEXTURE_DICTIONARY"):
                                if res_abs + res_padding + 32 <= self.size:
                                    num_tex = struct.unpack_from('<I', self.data, res_abs + res_padding)[0]
                                    list_start = self.read_ptr(res_abs + res_padding + 24)
                                    if list_start > 0:
                                        for t in range(num_tex):
                                            t_addr = list_start + t * 8
                                            if t_addr + 8 > self.size:
                                                break
                                            raw_ptr = struct.unpack_from('<Q', self.data, t_addr)[0]
                                            p2 = self.pointer_page_ids.get(t_addr)
                                            vram_abs = (raw_ptr + self.pages[p2][0] - 32) if (p2 is not None and p2 < len(self.pages)) else (raw_ptr - 32)
                                            if 0 <= vram_abs and vram_abs + 80 <= self.size:
                                                v_entry = ResItemEntry(
                                                    page_idx=p2 if p2 is not None else 0,
                                                    entry_idx=t,
                                                    name="",
                                                    item_name="",
                                                    item_type="VRAM_DESC",
                                                    abs_offset=vram_abs
                                                )
                                                self.all_items.append(v_entry)
                                                if "VRAM_DESC" not in self.items_by_type:
                                                    self.items_by_type["VRAM_DESC"] = []
                                                self.items_by_type["VRAM_DESC"].append(v_entry)
            return

        for p_idx, (p_offs, p_size, p_flags) in enumerate(self.pages):
            if p_offs + 20 > self.size:
                continue

            num_entries = struct.unpack_from('<H', self.data, p_offs + 18)[0]
            if num_entries > 5000:
                continue

            cur = p_offs + 20
            for e in range(num_entries):
                if cur + 16 > self.size:
                    break
                name_offs = struct.unpack_from('<Q', self.data, cur)[0]
                res_item_offs = struct.unpack_from('<I', self.data, cur + 8)[0]
                cur += 16

                name = self.read_str_at(name_offs + p_offs)
                res_abs = res_item_offs + p_offs
                if res_abs + 16 > self.size:
                    continue

                item_name_offs = struct.unpack_from('<Q', self.data, res_abs)[0]
                item_type_offs = struct.unpack_from('<Q', self.data, res_abs + 8)[0]

                item_name = self.read_str_at(item_name_offs + p_offs)
                item_type = self.read_str_at(item_type_offs + p_offs)

                if not item_type:
                    continue

                entry = ResItemEntry(
                    page_idx=p_idx,
                    entry_idx=e,
                    name=name,
                    item_name=item_name,
                    item_type=item_type,
                    abs_offset=res_abs
                )
                self.all_items.append(entry)
                if item_type not in self.items_by_type:
                    self.items_by_type[item_type] = []
                self.items_by_type[item_type].append(entry)

    def get_items(self, item_type: str) -> List[ResItemEntry]:
        """Returns all ResItems of the given type (e.g. GEOMETRY_1, VRAM_DESC, JOINT_HIERARCHY, ANIM)."""
        return self.items_by_type.get(item_type, [])

    def get_first_item(self, item_type: str) -> Optional[ResItemEntry]:
        items = self.get_items(item_type)
        return items[0] if items else None
