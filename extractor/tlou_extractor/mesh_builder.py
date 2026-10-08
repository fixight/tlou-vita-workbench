"""
mesh_builder.py - Extraction and decoding of 3D geometry from Naughty Dog PAK files.
"""
import struct
import math
import re
import copy
from typing import Dict, List, Optional, Tuple, Any
from .pak_reader import PakFile, ResItemEntry

class BitReaderMSB:
    def __init__(self, data: bytes, start_offset: int = 0):
        self.data = data
        self.bit_pos = start_offset * 8

    def read_bits(self, n: int) -> int:
        if n <= 0:
            return 0
        val = 0
        data = self.data
        data_len = len(data)
        for _ in range(n):
            byte_idx = self.bit_pos >> 3
            bit_idx = 7 - (self.bit_pos & 7)
            if byte_idx < data_len:
                bit = (data[byte_idx] >> bit_idx) & 1
                val = (val << 1) | bit
            self.bit_pos += 1
        return val

class SubmeshData:
    def __init__(self, name: str, lod_index: int = 0):
        self.name = name
        self.lod_index = lod_index
        self.positions: List[Tuple[float, float, float]] = []
        self.normals: List[Tuple[float, float, float]] = []
        self.tangents: List[Tuple[float, float, float, float]] = []
        self.uv0: List[Tuple[float, float]] = []
        self.uv1: List[Tuple[float, float]] = []
        self.uv12: List[Tuple[float, float]] = []
        self.colors: List[Tuple[float, float, float, float]] = []
        self.indices: List[int] = []
        self.bone_indices: List[List[int]] = []
        self.bone_weights: List[List[float]] = []
        self.material_name: str = ""
        self.texture_hashes: List[Any] = []
        self.diffuse_hash: str = ""
        self.normal_hash: str = ""
        self.transparency_hash: str = ""

    def __repr__(self):
        return f"<Submesh '{self.name}' LOD{self.lod_index}: verts={len(self.positions)}, tris={len(self.indices)//3}>"

class MeshModel:
    def __init__(self, name: str):
        self.name = name
        self.submeshes: List[SubmeshData] = []

    def __repr__(self):
        return f"<MeshModel '{self.name}' submeshes={len(self.submeshes)}>"


def bake_instance_palette(raw: SubmeshData, matrices) -> SubmeshData:
    """Bake instance-local 3x4 row-major matrices before the world transform."""
    import numpy as np
    if not raw.bone_indices:
        return raw
    palette = np.asarray(matrices, dtype=float).reshape(-1, 3, 4)
    joints = np.asarray(raw.bone_indices)
    weights = np.asarray(raw.bone_weights, dtype=float)
    if joints.shape != weights.shape or len(joints) != len(raw.positions):
        raise ValueError('invalid instance skin dimensions')
    active = weights > 0
    if np.any((joints[active] < 0) | (joints[active] >= len(palette))):
        raise ValueError('instance skin joint outside matrix palette')
    joints = np.where(active, joints, 0)
    transforms = (palette[joints] * weights[:, :, None, None]).sum(axis=1)
    result = copy.copy(raw)
    points = np.column_stack((raw.positions, np.ones(len(raw.positions))))
    result.positions = np.einsum('vij,vj->vi', transforms, points).tolist()
    linear = transforms[:, :, :3]
    if raw.normals:
        normals = np.linalg.solve(linear.transpose(0, 2, 1), np.asarray(raw.normals)[..., None])[..., 0]
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
        result.normals = normals.tolist()
    if raw.tangents:
        tangents = np.asarray(raw.tangents)
        vectors = np.einsum('vij,vj->vi', linear, tangents[:, :3])
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        result.tangents = np.column_stack((vectors, tangents[:, 3] * np.sign(np.linalg.det(linear)))).tolist()
    result.bone_indices = []
    result.bone_weights = []
    return result

class MeshBuilder:
    def __init__(self, pak: PakFile):
        self.pak = pak
        self.models: List[MeshModel] = []
        self.parse_all()

    def parse_all(self):
        geom_items = self.pak.get_items('GEOMETRY_1')
        for item in geom_items:
            model = self._parse_geometry(item)
            if model and model.submeshes:
                self.models.append(model)

    def _parse_geometry(self, item: ResItemEntry) -> Optional[MeshModel]:
        res_abs = item.abs_offset
        data = self.pak.data
        if res_abs + 48 > len(data):
            return None

        is_pc = self.pak.magic in (2685, 68221)
        model_name = item.name or item.item_name or "model"
        model = MeshModel(model_name)

        if is_pc:
            res_padding = 48
            if res_abs + res_padding + 64 > len(data):
                return None

            num_submeshes = struct.unpack_from('<I', data, res_abs + res_padding + 8)[0]
            submeshes_offs = self.pak.read_ptr(res_abs + res_padding + 40)
            if not submeshes_offs:
                return None

            num_materials = struct.unpack_from('<I', data, res_abs + res_padding + 16)[0]
            pap_transform = self.pak.read_ptr(res_abs + res_padding + 56)
            xforms: Dict[int, List[List[float]]] = {}
            if pap_transform and num_materials > 0:
                for i in range(num_materials):
                    off = self.pak.read_ptr(pap_transform + 8 * i)
                    if off and off + 64 <= len(data):
                        mat_floats = list(struct.unpack_from('<16f', data, off))
                        submesh_xforms_offs = self.pak.read_ptr(off + 152)
                        num_submesh_xforms = struct.unpack_from('<I', data, off + 212)[0] if off + 216 <= len(data) else 0
                        if submesh_xforms_offs and num_submesh_xforms > 0:
                            for j in range(num_submesh_xforms):
                                sm_off = self.pak.read_ptr(submesh_xforms_offs + j * 112 + 64)
                                if sm_off not in xforms:
                                    xforms[sm_off] = []
                                xforms[sm_off].append(mat_floats)

            for s in range(num_submeshes):
                sm_addr = submeshes_offs + s * 176
                if sm_addr + 140 > len(data):
                    break

                sm_name_ptr = self.pak.read_ptr(sm_addr + 32)
                sm_name = self.pak.read_str_at(sm_name_ptr) if sm_name_ptr else f"submesh_{s}"

                lod_idx = 0
                name_lower = sm_name.lower()
                if "shape" in name_lower:
                    shape_part = name_lower.split("shape")[-1]
                    if shape_part and shape_part[0].isdigit():
                        lod_idx = int(shape_part[0])
                elif "lod" in name_lower:
                    lod_part = name_lower.split("lod")[-1]
                    if lod_part and lod_part[0].isdigit():
                        lod_idx = int(lod_part[0])

                p_streams = self.pak.read_ptr(sm_addr + 48)
                p_indices = self.pak.read_ptr(sm_addr + 64)
                p_material = self.pak.read_ptr(sm_addr + 72)
                num_verts = struct.unpack_from('<I', data, sm_addr + 128)[0]
                num_indices = struct.unpack_from('<I', data, sm_addr + 132)[0]
                num_streams = struct.unpack_from('<I', data, sm_addr + 136)[0]

                if num_verts == 0 or num_indices == 0:
                    continue

                raw_positions = []
                raw_normals = []
                raw_uv0 = []
                indices = []

                if 0 < p_indices and p_indices + num_indices * 2 <= len(data):
                    indices = list(struct.unpack_from(f'<{num_indices}H', data, p_indices))

                if 0 < p_streams and 0 < num_streams < 16:
                    for st in range(num_streams):
                        st_addr = p_streams + st * 64
                        if st_addr + 64 > len(data):
                            break
                        buf_ptr = self.pak.read_ptr(st_addr)
                        if not buf_ptr or buf_ptr <= 0 or buf_ptr >= len(data):
                            continue
                        comp_type = data[st_addr + 20]
                        b22 = data[st_addr + 22]
                        stride = b22 >> 4
                        sizes = list(data[st_addr + 24:st_addr + 28])
                        q_scale = struct.unpack_from('<4f', data, st_addr + 32)
                        q_offs = struct.unpack_from('<4f', data, st_addr + 48)

                        if comp_type == 64:
                            r = BitReaderMSB(data, buf_ptr)
                            for v in range(num_verts):
                                px = r.read_bits(sizes[0]) * q_scale[0] + q_offs[0]
                                py = r.read_bits(sizes[1]) * q_scale[1] + q_offs[1]
                                pz = r.read_bits(sizes[2]) * q_scale[2] + q_offs[2]
                                raw_positions.append((px, py, pz))
                        elif comp_type in (65, 75, 76):
                            r = BitReaderMSB(data, buf_ptr)
                            for v in range(num_verts):
                                u = r.read_bits(sizes[0]) * q_scale[0] + q_offs[0]
                                vc = r.read_bits(sizes[1]) * q_scale[1] + q_offs[1]
                                raw_uv0.append((u, vc))
                        elif comp_type in (2, 130) and buf_ptr + num_verts * 4 <= len(data):
                            for v in range(num_verts):
                                u32 = struct.unpack_from('<I', data, buf_ptr + v * 4)[0]
                                nx = u32 & 0x3FF
                                if nx & 0x200: nx -= 0x400
                                ny = (u32 >> 10) & 0x3FF
                                if ny & 0x200: ny -= 0x400
                                nz = (u32 >> 20) & 0x3FF
                                if nz & 0x200: nz -= 0x400
                                nlen = math.hypot(nx, ny, nz) or 1.0
                                raw_normals.append((nx / nlen, ny / nlen, nz / nlen))

                if not raw_positions or not indices:
                    continue

                mat_name = ""
                if 0 < p_material < len(data):
                    p_inner = self.pak.read_ptr(p_material)
                    mat_str = ""
                    if 0 < p_inner < len(data):
                        mat_str = self.pak.read_str_at(p_inner, 512)
                    if not mat_str or not any(c.isalnum() for c in mat_str):
                        mat_str = self.pak.read_str_at(p_material, 512)
                    if mat_str and any(c.isalnum() for c in mat_str):
                        mat_path = mat_str.split(':')[0] if ':' in mat_str else mat_str.split(',')[0]
                        mat_name = mat_path.replace('\\', '/').split('/')[-1].strip()

                if not mat_name and sm_name:
                    clean_sm = sm_name.replace('\\', '/').split('/')[-1].split('|')[-1]
                    clean_sm = clean_sm.replace('.ma', '').split('_shader')[0].replace('Shape', '').strip()
                    if clean_sm and len(clean_sm) > 2 and any(c.isalnum() for c in clean_sm):
                        mat_name = clean_sm

                mat_instances = xforms.get(sm_addr, [None])
                for inst_idx, M in enumerate(mat_instances):
                    submesh = SubmeshData(name=f"{sm_name}#{inst_idx}" if inst_idx > 0 else sm_name, lod_index=lod_idx)
                    submesh.indices = list(indices)
                    submesh.uv0 = list(raw_uv0)
                    submesh.material_name = mat_name

                    if M is not None:
                        # Transform positions by 4x4 world matrix
                        for px, py, pz in raw_positions:
                            tx = M[0] * px + M[4] * py + M[8] * pz + M[12]
                            ty = M[1] * px + M[5] * py + M[9] * pz + M[13]
                            tz = M[2] * px + M[6] * py + M[10] * pz + M[14]
                            submesh.positions.append((tx, ty, tz))

                        if raw_normals:
                            for nx, ny, nz in raw_normals:
                                tnx = M[0] * nx + M[4] * ny + M[8] * nz
                                tny = M[1] * nx + M[5] * ny + M[9] * nz
                                tnz = M[2] * nx + M[6] * ny + M[10] * nz
                                nlen = math.hypot(tnx, tny, tnz) or 1.0
                                submesh.normals.append((tnx / nlen, tny / nlen, tnz / nlen))
                    else:
                        submesh.positions = list(raw_positions)
                        submesh.normals = list(raw_normals)

                    model.submeshes.append(submesh)

            return model

        # Determine submeshes offset (PS4)
        submeshes_offs = self.pak.read_ptr(res_abs + 0x30)
        if not submeshes_offs:
            submeshes_offs = self.pak.read_ptr(res_abs + 0x40)
        if not submeshes_offs:
            return None

        # In GEOMETRY_1 header:
        # Pair 1: SubMeshDescTable (res_abs + 0x28 count, res_abs + 0x30 pointer)
        num_submeshes = struct.unpack_from('<I', data, res_abs + 0x28)[0]
        if num_submeshes == 0 or num_submeshes > 5000:
            num_submeshes = 1

        # Pair 5: ShaderDesc array (stride 72 bytes at res_abs + 0x68 count, res_abs + 0x70 ptr)
        p5_cnt = struct.unpack_from('<I', data, res_abs + 0x68)[0] if res_abs + 0x70 <= len(data) else 0
        p5_ptr = self.pak.read_ptr(res_abs + 0x70) if res_abs + 0x78 <= len(data) else 0
        shader_materials: Dict[str, Dict[str, Any]] = {}

        if p5_cnt > 0 and 0 < p5_ptr < len(data):
            for i in range(p5_cnt):
                sh_addr = p5_ptr + i * 72
                if sh_addr + 72 > len(data):
                    break
                mat_ptr = self.pak.read_ptr(sh_addr)
                mat_str = self.pak.read_str_at(mat_ptr) if mat_ptr else ""
                p_tex_hdr = self.pak.read_ptr(sh_addr + 0x28)
                tex_count = struct.unpack_from('<I', data, sh_addr + 0x38)[0] if sh_addr + 0x3C <= len(data) else 0

                diff_h = ""
                norm_h = ""
                opacity_h = ""
                hashes = []

                if p_tex_hdr and 0 < tex_count < 64:
                    for t in range(tex_count):
                        th_addr = p_tex_hdr + t * 40
                        if th_addr + 40 > len(data):
                            break
                        slot_ptr = self.pak.read_ptr(th_addr)
                        slot_name = self.pak.read_str_at(slot_ptr) if slot_ptr else ""
                        path_ptr = self.pak.read_ptr(th_addr + 0x10)
                        tex_path = self.pak.read_str_at(path_ptr) if path_ptr else ""
                        m = re.search(r'([0-9a-fA-F]{16})', tex_path)
                        h = m.group(1).lower() if m else ""
                        if h:
                            hashes.append(h)
                            s_low = slot_name.lower()
                            # LightColor is illumination in lightmap UVs, not albedo.
                            surface_slot = not any(x in s_low for x in ('g_tlm', 'light', 'environment', 'reflection'))
                            if surface_slot and (s_low == 'g_tndfetchcolor1map' or 'diffuse' in s_low or 'albedo' in s_low or 'basecolor' in s_low):
                                # Color4 can contain specular/data; Color1 is albedo.
                                diff_h = h
                            elif s_low == 'g_tndfetchtransparencymap':
                                opacity_h = h
                            elif s_low == 'g_tndfetchnormal1map' or ('normal' in s_low and not norm_h):
                                norm_h = h

                if mat_str:
                    shader_materials[mat_str] = {
                        "diffuse_hash": diff_h,
                        "normal_hash": norm_h,
                        "transparency_hash": opacity_h,
                        "hashes": hashes
                    }

        raw_submeshes: List[SubmeshData] = []
        for s in range(num_submeshes):
            sm_addr = submeshes_offs + s * 136 # 0x88 (136 bytes) per submesh descriptor in TLOU PS4
            if sm_addr + 0x48 > len(data):
                break

            sm_name_ptr = self.pak.read_ptr(sm_addr + 0x08)
            sm_name = self.pak.read_str_at(sm_name_ptr) if sm_name_ptr else f"submesh_{s}"
            
            # Detect LOD index from name if explicitly marked
            lod_idx = 0
            name_lower = sm_name.lower()
            if "_lod" in name_lower or "|lod" in name_lower or "lod" in name_lower:
                lod_part = name_lower.split("lod")[-1]
                if lod_part and lod_part[0].isdigit():
                    lod_idx = int(lod_part[0])

            submesh = SubmeshData(name=sm_name, lod_index=lod_idx)

            # Submesh attributes
            num_verts = struct.unpack_from('<I', data, sm_addr + 0x1C)[0]
            num_indices = struct.unpack_from('<I', data, sm_addr + 0x20)[0]
            num_streams = struct.unpack_from('<I', data, sm_addr + 0x24)[0]

            p_streams = self.pak.read_ptr(sm_addr + 0x30)
            p_indices = self.pak.read_ptr(sm_addr + 0x40)
            p_material = self.pak.read_ptr(sm_addr + 0x48)
            p_skindata = self.pak.read_ptr(sm_addr + 0x60)

            if num_verts == 0 or num_indices == 0:
                continue

            # Read indices (triangle list, 16-bit uint)
            if 0 < p_indices and p_indices + num_indices * 2 <= len(data):
                submesh.indices = list(struct.unpack_from(f'<{num_indices}H', data, p_indices))

            # Read streams
            if 0 < p_streams and 0 < num_streams < 16:
                for st in range(num_streams):
                    st_addr = p_streams + st * 24
                    if st_addr + 24 > len(data):
                        break
                    comp_info_ptr = self.pak.read_ptr(st_addr + 8)
                    buf_ptr = self.pak.read_ptr(st_addr + 16)
                    stride = struct.unpack_from('<H', data, st_addr + 2)[0]

                    if not buf_ptr or buf_ptr <= 0 or buf_ptr >= len(data):
                        continue

                    # Read attribute index from comp_info_ptr
                    attr_idx = 0
                    if comp_info_ptr and 0 < comp_info_ptr + 4 <= len(data):
                        attr_idx = struct.unpack_from('<B', data, comp_info_ptr)[0]
                    else:
                        attr_idx = st

                    # Decode attributes
                    if attr_idx == 0:
                        # POSITION: 3 x float32 (stride 12)
                        for v in range(num_verts):
                            v_addr = buf_ptr + v * stride
                            if 0 <= v_addr and v_addr + 12 <= len(data):
                                submesh.positions.append(struct.unpack_from('<3f', data, v_addr))
                    elif attr_idx in (1, 12):
                        # TEXCOORD_0: 2 x float32 (stride 8) or 2 x float16
                        target_uv = []
                        if stride == 8:
                            for v in range(num_verts):
                                v_addr = buf_ptr + v * stride
                                if 0 <= v_addr and v_addr + 8 <= len(data):
                                    target_uv.append(struct.unpack_from('<2f', data, v_addr))
                        elif stride >= 4:
                            for v in range(num_verts):
                                v_addr = buf_ptr + v * stride
                                if 0 <= v_addr and v_addr + 4 <= len(data):
                                    target_uv.append(struct.unpack_from('<2e', data, v_addr))
                        if attr_idx == 1:
                            submesh.uv0 = target_uv
                        else:
                            submesh.uv12 = target_uv
                    elif attr_idx == 2:
                        # NORMAL: 3 x float32 (stride 12)
                        if stride >= 12:
                            for v in range(num_verts):
                                v_addr = buf_ptr + v * stride
                                if 0 <= v_addr and v_addr + 12 <= len(data):
                                    submesh.normals.append(struct.unpack_from('<3f', data, v_addr))
                    elif attr_idx == 3:
                        # TANGENT: 4 x float32 (stride 16)
                        if stride >= 16:
                            for v in range(num_verts):
                                v_addr = buf_ptr + v * stride
                                if 0 <= v_addr and v_addr + 16 <= len(data):
                                    submesh.tangents.append(struct.unpack_from('<4f', data, v_addr))
                    elif attr_idx == 5:
                        # TEXCOORD_1: 2 x float32 or 2 x float16
                        if stride == 8:
                            for v in range(num_verts):
                                v_addr = buf_ptr + v * stride
                                if 0 <= v_addr and v_addr + 8 <= len(data):
                                    submesh.uv1.append(struct.unpack_from('<2f', data, v_addr))

            if not submesh.uv0 and submesh.uv12:
                submesh.uv0 = list(submesh.uv12)

            # Read Material if available
            mat_str = ""
            if 0 < p_material < len(data):
                mat_str = self.pak.read_str_at(p_material, 512)
                if not mat_str or len(mat_str) < 2:
                    p_inner = self.pak.read_ptr(p_material)
                    if 0 < p_inner < len(data):
                        mat_str = self.pak.read_str_at(p_inner, 512)

            if mat_str:
                mat_path = mat_str.split(':')[0] if ':' in mat_str else mat_str.split(',')[0]
                mat_base = mat_path.replace('\\', '/').split('/')[-1].strip()
                submesh.material_name = mat_base
                if mat_str in shader_materials:
                    submesh.diffuse_hash = shader_materials[mat_str]["diffuse_hash"]
                    submesh.normal_hash = shader_materials[mat_str]["normal_hash"]
                    submesh.transparency_hash = shader_materials[mat_str]["transparency_hash"]
                    submesh.texture_hashes = shader_materials[mat_str]["hashes"]

            # Read Skinning weights and bone indices
            if 0 < p_skindata and p_skindata + 40 <= len(data):
                total_inf = struct.unpack_from('<I', data, p_skindata + 4)[0]
                p_counts = self.pak.read_ptr(p_skindata + 8)
                p_offsets = self.pak.read_ptr(p_skindata + 16)
                p_bones = self.pak.read_ptr(p_skindata + 24)
                p_weights = self.pak.read_ptr(p_skindata + 32)

                if (p_counts and p_offsets and p_bones and p_weights and
                    p_counts + num_verts * 2 <= len(data) and
                    p_offsets + num_verts * 2 <= len(data) and
                    p_bones + total_inf * 2 <= len(data) and
                    p_weights + total_inf * 4 <= len(data)):
                    counts = struct.unpack_from(f'<{num_verts}H', data, p_counts)
                    offsets = struct.unpack_from(f'<{num_verts}H', data, p_offsets)
                    bones = struct.unpack_from(f'<{total_inf}H', data, p_bones)
                    weights = struct.unpack_from(f'<{total_inf}f', data, p_weights)

                    for v in range(num_verts):
                        cnt = counts[v]
                        off = offsets[v]
                        v_bones = [0, 0, 0, 0]
                        v_weights = [0.0, 0.0, 0.0, 0.0]
                        for k in range(min(cnt, 4)):
                            if off + k < total_inf:
                                v_bones[k] = bones[off + k]
                                v_weights[k] = weights[off + k]

                        # Normalize weights to sum to 1.0
                        w_sum = sum(v_weights)
                        if w_sum > 1e-6:
                            v_weights = [w / w_sum for w in v_weights]
                        else:
                            v_weights = [1.0, 0.0, 0.0, 0.0]

                        submesh.bone_indices.append(v_bones)
                        submesh.bone_weights.append(v_weights)

            raw_submeshes.append(submesh)

        # Pair 2: Collections (res_abs + 0x38 count, res_abs + 0x40 ptr)
        # Pair 3: Instances (res_abs + 0x48 count, res_abs + 0x50 ptr)
        p2_cnt = struct.unpack_from('<I', data, res_abs + 0x38)[0] if res_abs + 0x40 <= len(data) else 0
        p2_ptr = self.pak.read_ptr(res_abs + 0x40) if res_abs + 0x48 <= len(data) else 0
        p3_cnt = struct.unpack_from('<I', data, res_abs + 0x48)[0] if res_abs + 0x50 <= len(data) else 0
        p3_ptr = self.pak.read_ptr(res_abs + 0x50) if res_abs + 0x58 <= len(data) else 0

        collections_by_name: Dict[str, Tuple[int, int]] = {}
        if p2_cnt > 0 and 0 < p2_ptr < len(data):
            cur_sm = 0
            for c in range(p2_cnt):
                c_addr = self.pak.read_ptr(p2_ptr + c * 8)
                if not c_addr or c_addr >= len(data):
                    c_addr = p2_ptr + c * 120
                if c_addr + 20 > len(data):
                    break
                sm_count = struct.unpack_from('<I', data, c_addr + 4)[0]
                name_ptr = self.pak.read_ptr(c_addr + 0x10)
                name = self.pak.read_str_at(name_ptr) if name_ptr else f"collection_{c}"
                collections_by_name[name] = (cur_sm, sm_count)
                cur_sm += sm_count

        if p3_cnt > 0 and 0 < p3_ptr < len(data) and collections_by_name:
            for inst_idx in range(p3_cnt):
                inst_addr = self.pak.read_ptr(p3_ptr + inst_idx * 8)
                if not inst_addr or inst_addr + 0xC0 > len(data):
                    continue
                proto_ptr = self.pak.read_ptr(inst_addr + 8)
                proto_name = self.pak.read_str_at(proto_ptr) if proto_ptr else ""
                M = list(struct.unpack_from('<16f', data, inst_addr + 0x80))
                palette_count = struct.unpack_from('<I', data, inst_addr + 0x24)[0]
                palette_ptr = self.pak.read_ptr(inst_addr + 0x38)
                palette = None
                if palette_count and palette_ptr:
                    if palette_ptr + palette_count * 48 > len(data):
                        raise ValueError('truncated instance matrix palette')
                    palette = struct.unpack_from(f'<{palette_count * 12}f', data, palette_ptr)

                if proto_name in collections_by_name:
                    start_sm, count_sm = collections_by_name[proto_name]
                    clean_proto = proto_name.replace('\\', '/').split('/')[-1].replace('.ma', '')
                    for s_off in range(count_sm):
                        s_idx = start_sm + s_off
                        if s_idx >= len(raw_submeshes):
                            continue
                        raw = raw_submeshes[s_idx]
                        if not raw.positions or not raw.indices:
                            continue

                        if palette is not None:
                            raw = bake_instance_palette(raw, palette)

                        inst_name = f"{clean_proto}_{raw.name}#{inst_idx}" if inst_idx > 0 else f"{clean_proto}_{raw.name}"
                        submesh = SubmeshData(name=inst_name, lod_index=raw.lod_index)
                        submesh.indices = list(raw.indices)
                        submesh.uv0 = list(raw.uv0)
                        submesh.uv1 = list(raw.uv1)
                        submesh.uv12 = list(raw.uv12)
                        submesh.material_name = raw.material_name
                        submesh.diffuse_hash = raw.diffuse_hash
                        submesh.normal_hash = raw.normal_hash
                        submesh.transparency_hash = raw.transparency_hash
                        submesh.texture_hashes = list(raw.texture_hashes)

                        # 4x4 Row-major world transformation
                        for px, py, pz in raw.positions:
                            tx = M[0] * px + M[4] * py + M[8] * pz + M[12]
                            ty = M[1] * px + M[5] * py + M[9] * pz + M[13]
                            tz = M[2] * px + M[6] * py + M[10] * pz + M[14]
                            submesh.positions.append((tx, ty, tz))

                        if raw.normals:
                            for nx, ny, nz in raw.normals:
                                tnx = M[0] * nx + M[4] * ny + M[8] * nz
                                tny = M[1] * nx + M[5] * ny + M[9] * nz
                                tnz = M[2] * nx + M[6] * ny + M[10] * nz
                                nlen = math.hypot(tnx, tny, tnz) or 1.0
                                submesh.normals.append((tnx / nlen, tny / nlen, tnz / nlen))

                        if raw.tangents:
                            for tx, ty, tz, tw in raw.tangents:
                                ttx = M[0] * tx + M[4] * ty + M[8] * tz
                                tty = M[1] * tx + M[5] * ty + M[9] * tz
                                ttz = M[2] * tx + M[6] * ty + M[10] * tz
                                tlen = math.hypot(ttx, tty, ttz) or 1.0
                                submesh.tangents.append((ttx / tlen, tty / tlen, ttz / tlen, tw))

                        submesh.colors = list(raw.colors)
                        submesh.bone_indices = list(raw.bone_indices)
                        submesh.bone_weights = list(raw.bone_weights)

                        model.submeshes.append(submesh)
        else:
            # Standalone model without instances (e.g. single prop/actor)
            for raw in raw_submeshes:
                if raw.positions and raw.indices:
                    model.submeshes.append(raw)

        return model
