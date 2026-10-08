"""
gltf_writer.py - Generates valid glTF 2.0 (.gltf + .bin) and GLB (.glb) models.
Supports PBR materials, multi-LOD nodes, skeletal rigging (skin), and animation tracks.
"""
import struct
import json
import os
import math
from typing import Dict, List, Optional, Tuple, Any
from .mesh_builder import MeshModel, SubmeshData
from .skeleton_reader import Skeleton, BoneNode
from .anim_reader import AnimationClip, AnimationTrack
from .texture_handler import TextureInfo

class GLTFWriter:
    def __init__(self, scene_name: str = "TLOU_Scene"):
        self.scene_name = scene_name
        self.asset_extras: Dict[str, Any] = {}
        self.bin_buffer = bytearray()
        self.buffer_views: List[Dict[str, Any]] = []
        self.accessors: List[Dict[str, Any]] = []
        self.materials: List[Dict[str, Any]] = []
        self.textures: List[Dict[str, Any]] = []
        self.images: List[Dict[str, Any]] = []
        self.samplers: List[Dict[str, Any]] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
        self.meshes: List[Dict[str, Any]] = []
        self.nodes: List[Dict[str, Any]] = []
        self.animations: List[Dict[str, Any]] = []
        self.skins: List[Dict[str, Any]] = []
        
        self.tex_uri_map: Dict[str, int] = {} # uri -> texture_index

    def _pad_buffer(self, alignment: int = 4):
        remainder = len(self.bin_buffer) % alignment
        if remainder != 0:
            self.bin_buffer.extend(b'\x00' * (alignment - remainder))

    def _add_buffer_view(self, data_bytes: bytes, target: Optional[int] = None) -> int:
        self._pad_buffer(4)
        offset = len(self.bin_buffer)
        self.bin_buffer.extend(data_bytes)
        bv_idx = len(self.buffer_views)
        view_entry: Dict[str, Any] = {
            "buffer": 0,
            "byteOffset": offset,
            "byteLength": len(data_bytes)
        }
        if target is not None:
            view_entry["target"] = target
        self.buffer_views.append(view_entry)
        return bv_idx

    def _add_accessor(self, buffer_view_idx: int, component_type: int, count: int, 
                      accessor_type: str, min_val: Optional[List[float]] = None, 
                      max_val: Optional[List[float]] = None) -> int:
        acc_idx = len(self.accessors)
        acc_entry: Dict[str, Any] = {
            "bufferView": buffer_view_idx,
            "byteOffset": 0,
            "componentType": component_type,
            "count": count,
            "type": accessor_type
        }
        if min_val is not None:
            acc_entry["min"] = min_val
        if max_val is not None:
            acc_entry["max"] = max_val
        self.accessors.append(acc_entry)
        return acc_idx

    def add_texture(self, uri: str) -> int:
        """Registers a texture image and returns the texture index."""
        clean_uri = uri.replace('\\', '/')
        if clean_uri in self.tex_uri_map:
            return self.tex_uri_map[clean_uri]

        img_idx = len(self.images)
        self.images.append({"uri": clean_uri})

        tex_idx = len(self.textures)
        self.textures.append({"sampler": 0, "source": img_idx})
        self.tex_uri_map[clean_uri] = tex_idx
        return tex_idx

    def add_material(self, name: str, base_color_tex: Optional[str] = None, 
                     normal_tex: Optional[str] = None,
                     extras: Optional[Dict[str, Any]] = None) -> int:
        mat_entry: Dict[str, Any] = {
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "metallicFactor": 0.1,
                "roughnessFactor": 0.8
            },
            "doubleSided": True
        }
        if base_color_tex:
            tex_idx = self.add_texture(base_color_tex)
            mat_entry["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex_idx}
        if normal_tex:
            tex_idx = self.add_texture(normal_tex)
            mat_entry["normalTexture"] = {"index": tex_idx}
        if extras:
            mat_entry["extras"] = extras

        mat_idx = len(self.materials)
        self.materials.append(mat_entry)
        return mat_idx

    def add_submesh(self, submesh: SubmeshData, material_idx: Optional[int] = None) -> int:
        """Builds buffer views and accessors for submesh attributes and indices."""
        if not submesh.positions or not submesh.indices:
            return -1

        num_verts = len(submesh.positions)
        primitives_attributes: Dict[str, int] = {}

        # 1. POSITION (FLOAT, VEC3)
        pos_bytes = bytearray()
        min_pos = [float('inf')] * 3
        max_pos = [float('-inf')] * 3
        for x, y, z in submesh.positions:
            pos_bytes.extend(struct.pack('<3f', x, y, z))
            min_pos[0] = min(min_pos[0], x)
            min_pos[1] = min(min_pos[1], y)
            min_pos[2] = min(min_pos[2], z)
            max_pos[0] = max(max_pos[0], x)
            max_pos[1] = max(max_pos[1], y)
            max_pos[2] = max(max_pos[2], z)

        pos_bv = self._add_buffer_view(bytes(pos_bytes), target=34962) # ARRAY_BUFFER
        pos_acc = self._add_accessor(pos_bv, 5126, num_verts, "VEC3", min_val=min_pos, max_val=max_pos)
        primitives_attributes["POSITION"] = pos_acc

        # 2. NORMAL (FLOAT, VEC3)
        if submesh.normals and len(submesh.normals) == num_verts:
            nrm_bytes = bytearray()
            for nx, ny, nz in submesh.normals:
                nrm_bytes.extend(struct.pack('<3f', nx, ny, nz))
            nrm_bv = self._add_buffer_view(bytes(nrm_bytes), target=34962)
            nrm_acc = self._add_accessor(nrm_bv, 5126, num_verts, "VEC3")
            primitives_attributes["NORMAL"] = nrm_acc

        # 3. TANGENT (FLOAT, VEC4)
        if submesh.tangents and len(submesh.tangents) == num_verts:
            tan_bytes = bytearray()
            for tx, ty, tz, tw in submesh.tangents:
                tan_bytes.extend(struct.pack('<4f', tx, ty, tz, tw))
            tan_bv = self._add_buffer_view(bytes(tan_bytes), target=34962)
            tan_acc = self._add_accessor(tan_bv, 5126, num_verts, "VEC4")
            primitives_attributes["TANGENT"] = tan_acc

        # 4. TEXCOORD_0 (FLOAT, VEC2)
        if submesh.uv0 and len(submesh.uv0) == num_verts:
            uv_bytes = bytearray()
            for u, v in submesh.uv0:
                uv_bytes.extend(struct.pack('<2f', u, v))
            uv_bv = self._add_buffer_view(bytes(uv_bytes), target=34962)
            uv_acc = self._add_accessor(uv_bv, 5126, num_verts, "VEC2")
            primitives_attributes["TEXCOORD_0"] = uv_acc

        for channel, values in enumerate((submesh.uv1, submesh.uv12), 1):
            if values and len(values) == num_verts:
                uv_bytes = b''.join(struct.pack('<2f',u,v) for u,v in values)
                uv_bv = self._add_buffer_view(uv_bytes, target=34962)
                primitives_attributes[f'TEXCOORD_{channel}'] = self._add_accessor(uv_bv,5126,num_verts,'VEC2')

        # 5. JOINTS_0 & WEIGHTS_0 (if rigged)
        if submesh.bone_indices and len(submesh.bone_indices) == num_verts:
            joints_bytes = bytearray()
            weights_bytes = bytearray()
            for j in submesh.bone_indices:
                joints_bytes.extend(struct.pack('<4H', j[0], j[1], j[2], j[3]))
            for w in submesh.bone_weights:
                weights_bytes.extend(struct.pack('<4f', w[0], w[1], w[2], w[3]))

            j_bv = self._add_buffer_view(bytes(joints_bytes), target=34962)
            j_acc = self._add_accessor(j_bv, 5123, num_verts, "VEC4") # UNSIGNED_SHORT
            primitives_attributes["JOINTS_0"] = j_acc

            w_bv = self._add_buffer_view(bytes(weights_bytes), target=34962)
            w_acc = self._add_accessor(w_bv, 5126, num_verts, "VEC4") # FLOAT
            primitives_attributes["WEIGHTS_0"] = w_acc

        # 6. INDICES (UNSIGNED_SHORT, SCALAR)
        idx_bytes = bytearray()
        for idx in submesh.indices:
            idx_bytes.extend(struct.pack('<H', idx))
        idx_bv = self._add_buffer_view(bytes(idx_bytes), target=34963) # ELEMENT_ARRAY_BUFFER
        idx_acc = self._add_accessor(idx_bv, 5123, len(submesh.indices), "SCALAR")

        prim: Dict[str, Any] = {
            "attributes": primitives_attributes,
            "indices": idx_acc,
            "mode": 4 # TRIANGLES
        }
        if material_idx is not None and material_idx >= 0:
            prim["material"] = material_idx

        mesh_idx = len(self.meshes)
        self.meshes.append({
            "name": submesh.name,
            "primitives": [prim]
        })
        return mesh_idx

    def add_skeleton(self, skeleton: Skeleton) -> Tuple[int, List[int]]:
        """Adds skeleton bones as nodes and creates a glTF skin. Returns (skin_idx, joint_node_indices)."""
        joint_node_indices = []
        base_node_offset = len(self.nodes)

        # Create nodes for all bones
        for bone in skeleton.bones:
            node_idx = len(self.nodes)
            joint_node_indices.append(node_idx)
            node_data: Dict[str, Any] = {
                "name": bone.name,
                "translation": list(bone.translation),
                "rotation": list(bone.rotation),
                "scale": list(bone.scale)
            }
            self.nodes.append(node_data)

        # Set children relationships
        for bone in skeleton.bones:
            if bone.children:
                child_node_ids = [base_node_offset + c for c in bone.children]
                self.nodes[base_node_offset + bone.index]["children"] = child_node_ids

        # Compute World Transform for each bone in rest pose and invert it for Inverse Bind Matrices (IBM)
        import numpy as np
        world_mats = []
        for bone in skeleton.bones:
            qx, qy, qz, qw = bone.rotation
            x2, y2, z2 = qx + qx, qy + qy, qz + qz
            xx, xy, xz = qx * x2, qx * y2, qx * z2
            yy, yz, zz = qy * y2, qy * z2, qz * z2
            wx, wy, wz = qw * x2, qw * y2, qw * z2
            sx, sy, sz = bone.scale
            tx, ty, tz = bone.translation

            loc_m = np.eye(4, dtype=np.float32)
            loc_m[0, 0] = (1.0 - (yy + zz)) * sx
            loc_m[0, 1] = (xy - wz) * sy
            loc_m[0, 2] = (xz + wy) * sz
            loc_m[0, 3] = tx
            loc_m[1, 0] = (xy + wz) * sx
            loc_m[1, 1] = (1.0 - (xx + zz)) * sy
            loc_m[1, 2] = (yz - wx) * sz
            loc_m[1, 3] = ty
            loc_m[2, 0] = (xz - wy) * sx
            loc_m[2, 1] = (yz + wx) * sy
            loc_m[2, 2] = (1.0 - (xx + yy)) * sz
            loc_m[2, 3] = tz

            if 0 <= bone.parent_index < len(world_mats):
                wm = world_mats[bone.parent_index] @ loc_m
            else:
                wm = loc_m
            world_mats.append(wm)

        ibm_bytes = bytearray()
        for wm in world_mats:
            try:
                inv_m = np.linalg.inv(wm)
            except Exception:
                inv_m = np.eye(4, dtype=np.float32)
            # Store in column-major order as required by glTF 2.0
            ibm_bytes.extend(struct.pack('<16f', *[float(v) for v in inv_m.flatten(order='F')]))

        ibm_bv = self._add_buffer_view(bytes(ibm_bytes))
        ibm_acc = self._add_accessor(ibm_bv, 5126, len(skeleton.bones), "MAT4")

        skin_idx = len(self.skins)
        self.skins.append({
            "inverseBindMatrices": ibm_acc,
            "joints": joint_node_indices,
            "skeleton": joint_node_indices[0] if joint_node_indices else 0
        })
        return skin_idx, joint_node_indices

    def add_animation(self, clip: AnimationClip, joint_node_indices: List[int]):
        """Adds an animation clip targeting bone nodes."""
        channels = []
        samplers = []

        for track in clip.tracks:
            if not 0 <= track.node_index < len(joint_node_indices):
                continue

            target_node = joint_node_indices[track.node_index]
            if not track.timestamps or not track.values:
                continue
            if len(track.timestamps) != len(track.values):
                raise ValueError(f"Mismatched animation samples in {clip.name}")
            times, values = track.timestamps, track.values
            # Constant pose channels need only endpoints, while retaining clip duration.
            if len(values) > 2 and all(value == values[0] for value in values[1:]):
                times, values = [times[0], times[-1]], [values[0], values[-1]]

            # Input accessor (time floats)
            time_bytes = bytearray()
            for t in times:
                time_bytes.extend(struct.pack('<f', t))
            time_bv = self._add_buffer_view(bytes(time_bytes))
            time_acc = self._add_accessor(time_bv, 5126, len(times), "SCALAR",
                                         min_val=[min(times)], max_val=[max(times)])

            # Output accessor (Vec3 or Quat)
            val_bytes = bytearray()
            is_rot = (track.target_path == "rotation")
            acc_type = "VEC4" if is_rot else "VEC3"

            for val in values:
                if is_rot:
                    val_bytes.extend(struct.pack('<4f', val[0], val[1], val[2], val[3]))
                else:
                    val_bytes.extend(struct.pack('<3f', val[0], val[1], val[2]))

            val_bv = self._add_buffer_view(bytes(val_bytes))
            val_acc = self._add_accessor(val_bv, 5126, len(values), acc_type)

            sampler_idx = len(samplers)
            samplers.append({
                "input": time_acc,
                "output": val_acc,
                "interpolation": "LINEAR"
            })

            channels.append({
                "sampler": sampler_idx,
                "target": {
                    "node": target_node,
                    "path": track.target_path
                }
            })

        if channels:
            animation = {
                "name": clip.name,
                "samplers": samplers,
                "channels": channels
            }
            if clip.unsupported_opcodes or clip.has_secondary_stream or clip.source_rig_id is not None:
                animation["extras"] = {"decoding": {
                    "sourceRig": f"{clip.source_rig_id:08x}" if clip.source_rig_id is not None else None,
                    "targetRig": f"{clip.target_rig_id:08x}" if clip.target_rig_id is not None else None,
                    "unsupportedPrimaryOpcodes": clip.unsupported_opcodes,
                    "secondaryStreamDecoded": False,
                    "hasSecondaryStream": clip.has_secondary_stream,
                }}
            self.animations.append(animation)

    def export_glb(self, output_path: str):
        """Exports full scene to a self-contained GLB file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Assemble root scene nodes (nodes that are not children of any other node)
        all_children = set()
        for node in self.nodes:
            if "children" in node:
                all_children.update(node["children"])

        root_nodes = [i for i in range(len(self.nodes)) if i not in all_children]
        if not root_nodes and self.nodes:
            root_nodes = [0]

        gltf_dict: Dict[str, Any] = {
            "asset": {
                "version": "2.0",
                "generator": "TLOU Remastered PS4 Asset Extractor",
                "extras": self.asset_extras
            },
            "scene": 0,
            "scenes": [{"name": self.scene_name, "nodes": root_nodes}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self.bin_buffer)}]
        }

        if self.materials:
            gltf_dict["materials"] = self.materials
        if self.textures:
            gltf_dict["textures"] = self.textures
        if self.images:
            gltf_dict["images"] = self.images
        if self.samplers:
            gltf_dict["samplers"] = self.samplers
        if self.skins:
            gltf_dict["skins"] = self.skins
        if self.animations:
            gltf_dict["animations"] = self.animations

        json_bytes = json.dumps(gltf_dict, separators=(',', ':')).encode('utf-8')
        json_padding = (4 - (len(json_bytes) % 4)) % 4
        json_bytes += b' ' * json_padding

        bin_padding = (4 - (len(self.bin_buffer) % 4)) % 4
        bin_data = bytes(self.bin_buffer) + (b'\x00' * bin_padding)

        total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_data)

        # GLB Header
        header = bytearray(12)
        header[0:4] = b'glTF'
        struct.pack_into('<I', header, 4, 2) # version 2
        struct.pack_into('<I', header, 8, total_length)

        # Chunk 0: JSON
        chunk0_header = bytearray(8)
        struct.pack_into('<I', chunk0_header, 0, len(json_bytes))
        chunk0_header[4:8] = b'JSON'

        # Chunk 1: BIN
        chunk1_header = bytearray(8)
        struct.pack_into('<I', chunk1_header, 0, len(bin_data))
        chunk1_header[4:8] = b'BIN\x00'

        with open(output_path, 'wb') as f:
            f.write(header)
            f.write(chunk0_header)
            f.write(json_bytes)
            f.write(chunk1_header)
            f.write(bin_data)

    def export_gltf(self, output_gltf_path: str):
        """Exports .gltf JSON and separate .bin file."""
        out_dir = os.path.dirname(os.path.abspath(output_gltf_path))
        os.makedirs(out_dir, exist_ok=True)
        bin_filename = os.path.splitext(os.path.basename(output_gltf_path))[0] + ".bin"
        bin_path = os.path.join(out_dir, bin_filename)

        with open(bin_path, 'wb') as f:
            f.write(self.bin_buffer)

        all_children = set()
        for node in self.nodes:
            if "children" in node:
                all_children.update(node["children"])

        root_nodes = [i for i in range(len(self.nodes)) if i not in all_children]
        if not root_nodes and self.nodes:
            root_nodes = [0]

        gltf_dict: Dict[str, Any] = {
            "asset": {
                "version": "2.0",
                "generator": "TLOU Remastered PS4 Asset Extractor",
                "extras": self.asset_extras
            },
            "scene": 0,
            "scenes": [{"name": self.scene_name, "nodes": root_nodes}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self.bin_buffer), "uri": bin_filename}]
        }

        if self.materials:
            gltf_dict["materials"] = self.materials
        if self.textures:
            gltf_dict["textures"] = self.textures
        if self.images:
            gltf_dict["images"] = self.images
        if self.samplers:
            gltf_dict["samplers"] = self.samplers
        if self.skins:
            gltf_dict["skins"] = self.skins
        if self.animations:
            gltf_dict["animations"] = self.animations

        with open(output_gltf_path, 'w', encoding='utf-8') as f:
            json.dump(gltf_dict, f, indent=2)
