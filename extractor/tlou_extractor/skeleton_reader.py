"""
skeleton_reader.py - Parsing bones, joint hierarchies, and local transforms for TLOU PS4.
"""
import struct
import math
import re
from typing import Dict, List, Optional, Tuple, Any
from .pak_reader import PakFile, ResItemEntry

class BoneNode:
    def __init__(self, index: int, name: str, parent_index: int = -1):
        self.index = index
        self.name = name
        self.parent_index = parent_index
        self.children: List[int] = []
        self.translation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.rotation: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0) # (x, y, z, w)
        self.scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)

    def __repr__(self):
        return f"<Bone #{self.index} '{self.name}' parent={self.parent_index}>"

class Skeleton:
    def __init__(self, name: str = "skeleton"):
        self.name = name
        self.native_rig_id: Optional[int] = None
        self.bones: List[BoneNode] = []
        self.bone_by_name: Dict[str, BoneNode] = {}

    def add_bone(self, bone: BoneNode):
        self.bones.append(bone)
        self.bone_by_name[bone.name] = bone

    def resolve_parents(self):
        """Build child lists and resolve any missing parent connections."""
        for b in self.bones:
            b.children = []

        # Automatic standard name-based parenting heuristic for Naughty Dog rigs
        name_map = {b.name.lower(): b.index for b in self.bones if b.name and b.name.strip()}

        for b in self.bones:
            if b.index == 0:
                b.parent_index = -1
                continue

            name = b.name.lower()
            pid = -1

            # Standard Naughty Dog naming hierarchy
            if "lower_base" in name or "upper_base" in name:
                pid = name_map.get("root", 0)
            elif "pelvis" in name:
                pid = name_map.get("lower_base", name_map.get("root", 0))
            elif "spine" in name:
                # spinea/spine1 -> upper_base/pelvis, etc.
                if name in ("spinea", "spine1", "spine"):
                    pid = name_map.get("upper_base", name_map.get("pelvis", 0))
                elif name in ("spineb", "spine2"):
                    pid = name_map.get("spinea", name_map.get("spine1", name_map.get("pelvis", 0)))
                elif name in ("spinec", "spine3"):
                    pid = name_map.get("spineb", name_map.get("spine2", name_map.get("pelvis", 0)))
                elif name in ("spined", "spine4"):
                    pid = name_map.get("spinec", name_map.get("spine3", name_map.get("pelvis", 0)))
                else:
                    pid = name_map.get("pelvis", 0)
            elif "neck" in name:
                pid = name_map.get("spined", name_map.get("spinec", name_map.get("spine3", name_map.get("pelvis", 0))))
            elif any(x in name for x in ("eye", "jaw", "lip", "chin", "cheek", "brow", "nose", "tongue")):
                pid = name_map.get("headb", name_map.get("heada", name_map.get("head", 0)))
            elif "head" in name:
                if "headb" in name:
                    pid = name_map.get("heada", name_map.get("neck", 0))
                else:
                    pid = name_map.get("neck", name_map.get("spined", 0))
            elif "clavicle" in name:
                pid = name_map.get("spined", name_map.get("spinec", name_map.get("spine3", name_map.get("neck", 0))))
            elif "upper_arm" in name or "shoulder" in name:
                side = "l_" if ("l_" in name or "_l" in name) else "r_"
                pid = name_map.get(f"{side}clavicle", name_map.get("spined", 0))
            elif "elbow" in name or "forearm" in name:
                side = "l_" if ("l_" in name or "_l" in name) else "r_"
                pid = name_map.get(f"{side}upper_arm", name_map.get(f"{side}clavicle", 0))
            elif any(f in name for f in ("thumb", "index", "middle", "ring", "pinky", "palm")):
                side = "l_" if ("l_" in name or "_l" in name) else "r_"
                pid = name_map.get(f"{side}wrist", name_map.get(f"{side}palm", 0))
            elif "wrist" in name or "hand" in name:
                side = "l_" if ("l_" in name or "_l" in name) else "r_"
                pid = name_map.get(f"{side}elbow", name_map.get(f"{side}forearm", 0))
            elif "upper_leg" in name or "thigh" in name:
                pid = name_map.get("pelvis", 0)
            elif "knee" in name:
                side = "l_" if ("l_" in name or "_l" in name) else "r_"
                pid = name_map.get(f"{side}upper_leg", name_map.get("pelvis", 0))
            elif "ankle" in name:
                side = "l_" if ("l_" in name or "_l" in name) else "r_"
                pid = name_map.get(f"{side}knee", 0)
            elif "heel" in name or ("ball" in name and "eye" not in name) or "foot" in name or "toe" in name:
                side = "l_" if ("l_" in name or "_l" in name) else "r_"
                pid = name_map.get(f"{side}ankle", 0)
            elif "helper" in name or "grp" in name or "offset" in name or "muscle" in name:
                # Find corresponding base bone
                clean = re.sub(r'(_helper|_grp|_offset|_base|_twist[a-z]?|_front|_rear|_lower|_upper|_inner|_outer|_calf|_thigh|_shirt|_muscle)+', '', name)
                pid = name_map.get(clean, name_map.get("pelvis", 0)) if clean and clean in name_map else name_map.get("pelvis", 0)
            else:
                pid = 0 # Default parent to root

            if pid == b.index or pid < 0 or pid >= len(self.bones):
                pid = 0
            b.parent_index = pid

        for b in self.bones:
            if 0 <= b.parent_index < len(self.bones) and b.parent_index != b.index:
                self.bones[b.parent_index].children.append(b.index)

class SkeletonReader:
    @staticmethod
    def read_skeleton(pak: PakFile) -> Optional[Skeleton]:
        joint_item = pak.get_first_item('JOINT_HIERARCHY')
        if not joint_item:
            return None

        res_abs = joint_item.abs_offset
        data = pak.data
        if res_abs + 48 > len(data):
            return None

        cnt_a = struct.unpack_from('<I', data, res_abs + 0x20)[0]
        cnt_b = struct.unpack_from('<I', data, res_abs + 0x24)[0]
        bone_count = cnt_b if (0 < cnt_b < 1000) else cnt_a
        if bone_count == 0 or bone_count > 1000:
            return None

        xforms_ptr = pak.read_ptr(res_abs + 0x28)
        names_ptr = pak.read_ptr(res_abs + 0x38)
        page_start = pak.pages[joint_item.page_idx][0]

        if not xforms_ptr or not names_ptr or xforms_ptr >= len(data) or names_ptr >= len(data):
            return None

        # Determine valid primary transform count from header
        valid_xform_count = bone_count
        if xforms_ptr + 64 <= len(data):
            pos = xforms_ptr + 16
            node_cnt, xform_cnt, ukn_cnt, ukn_short = struct.unpack_from('<4H', data, pos); pos += 8
            ukn0, ukn1, hdr_sz, u_int0, ukn_int1, a_offs = struct.unpack_from('<6I', data, pos)
            if a_offs > ukn_int1:
                cand_valid = (a_offs - ukn_int1) // 48
                if 0 < cand_valid <= bone_count:
                    valid_xform_count = cand_valid

        # Read bone names
        bone_names = []
        for b in range(bone_count):
            rel_offs = struct.unpack_from('<Q', data, names_ptr + b * 16 + 8)[0]
            target = rel_offs + page_start
            b_name = pak.read_str_at(target) if target < len(data) else f"bone_{b}"
            bone_names.append(b_name or f"bone_{b}")

        # Transforms start at xforms_ptr + 144
        xforms_start = xforms_ptr + 144
        skel = Skeleton(joint_item.name or "skeleton")
        if data[xforms_ptr:xforms_ptr+4] == b"\x04\x01HA":
            skel.native_rig_id = struct.unpack_from("<I", data, xforms_ptr+4)[0]

        for b in range(bone_count):
            addr = xforms_start + b * 48
            bone = BoneNode(index=b, name=bone_names[b], parent_index=0 if b > 0 else -1)

            is_valid = (b < valid_xform_count) and (addr + 48 <= len(data))
            if is_valid:
                sx, sy, sz = struct.unpack_from('<3f', data, addr)
                qx, qy, qz, qw = struct.unpack_from('<4f', data, addr + 16)
                tx, ty, tz = struct.unpack_from('<3f', data, addr + 32)

                q_len = math.sqrt(qx*qx + qy*qy + qz*qz + qw*qw)
                max_t = max(abs(tx), abs(ty), abs(tz))
                max_s = max(abs(sx), abs(sy), abs(sz))

                # Sanitize corrupted/uninitialized transform floats
                if (q_len < 1e-4 or abs(q_len - 1.0) > 0.15 or 
                    max_t > 50.0 or max_s > 10.0 or abs(sx) < 0.01):
                    bone.translation = (0.0, 0.0, 0.0)
                    bone.rotation = (0.0, 0.0, 0.0, 1.0)
                    bone.scale = (1.0, 1.0, 1.0)
                else:
                    bone.translation = (tx, ty, tz)
                    bone.rotation = (qx / q_len, qy / q_len, qz / q_len, qw / q_len)
                    bone.scale = (sx, sy, sz)
            else:
                # Helper bones outside primary array get clean identity local transform
                bone.translation = (0.0, 0.0, 0.0)
                bone.rotation = (0.0, 0.0, 0.0, 1.0)
                bone.scale = (1.0, 1.0, 1.0)

            skel.add_bone(bone)

        # Read the true native binary parenting table from JOINT_HIERARCHY
        hier_loaded = False
        if xforms_ptr + 0x50 <= len(data):
            hier_off = struct.unpack_from('<I', data, xforms_ptr + 0x4C)[0]
            if hier_off > 0 and xforms_ptr + hier_off + 24 <= len(data):
                base = xforms_ptr + hier_off
                hashes_sz = struct.unpack_from('<I', data, base + 20)[0]
                p_start = base + 20 + 4 + (hashes_sz - 24)
                if p_start + bone_count * 16 <= len(data):
                    name_map = {b.name.lower(): b.index for b in skel.bones if b.name and b.name.strip()}
                    for b in range(bone_count):
                        grp_id, parent_id, child_id, chain_id = struct.unpack_from('<4i', data, p_start + b * 16)
                        if b == 0:
                            skel.bones[b].parent_index = -1
                        elif 0 <= parent_id < bone_count and parent_id != b:
                            skel.bones[b].parent_index = parent_id
                        else:
                            # Helper bones/groups where parent_id == -1: reparent to matching base bone
                            clean = re.sub(r'(_helper|_grp|_offset|_base|_twist[a-z]?|_muscle)+', '', skel.bones[b].name.lower())
                            pid = name_map.get(clean, 0) if clean and clean in name_map else 0
                            if pid == b or pid < 0 or pid >= bone_count:
                                pid = 0
                            skel.bones[b].parent_index = pid

                    # Cycle detection and prevention: if any cycle exists, break it by pointing to root
                    for b in range(bone_count):
                        curr = skel.bones[b].parent_index
                        visited = {b}
                        while 0 <= curr < bone_count:
                            if curr in visited:
                                skel.bones[b].parent_index = 0
                                break
                            visited.add(curr)
                            curr = skel.bones[curr].parent_index

                    for b in skel.bones:
                        b.children = []
                    for b in skel.bones:
                        if 0 <= b.parent_index < len(skel.bones) and b.parent_index != b.index:
                            skel.bones[b.parent_index].children.append(b.index)
                    hier_loaded = True

        if not hier_loaded:
            skel.resolve_parents()

        return skel
