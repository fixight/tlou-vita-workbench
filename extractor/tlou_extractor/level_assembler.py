"""
level_assembler.py - Parses level manifests, static level geometry, and spawns actor instances in world coordinates.
"""
import os
import re
import json
import struct
from typing import Dict, List, Optional, Tuple, Any

from .pak_reader import PakFile, ResItemEntry
from .mesh_builder import MeshBuilder, MeshModel, SubmeshData
from .texture_handler import TextureHandler
from .material_transparency import transparency_extras
from .skeleton_reader import SkeletonReader, Skeleton
from .anim_reader import AnimationReader, AnimationClip
from .gltf_writer import GLTFWriter

class PlacedActorInstance:
    def __init__(self, name: str, position: Tuple[float, float, float], 
                 rotation: Tuple[float, float, float, float], actor_type: str = ""):
        self.name = name
        self.position = position
        self.rotation = rotation # (qx, qy, qz, qw)
        self.actor_type = actor_type

    def __repr__(self):
        return f"<PlacedActor '{self.name}' type='{self.actor_type}' at {self.position}>"

class LevelManifest:
    def __init__(self, level_id: str):
        self.level_id = level_id
        self.packages: List[str] = []
        self.actors: List[str] = []
        self.caches: List[str] = []
        self.modules: List[str] = []

    @staticmethod
    def parse_file(manifest_path: str) -> 'LevelManifest':
        level_id = os.path.splitext(os.path.basename(manifest_path))[0]
        manifest = LevelManifest(level_id)
        if not os.path.exists(manifest_path):
            return manifest

        with open(manifest_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    tag = parts[0].lower()
                    val = parts[1]
                    if tag == 'level-id':
                        manifest.level_id = val
                    elif tag == 'package':
                        manifest.packages.append(val)
                    elif tag == 'actor':
                        manifest.actors.append(val)
                    elif tag == 'cache':
                        manifest.caches.append(val)
                    elif tag == 'module':
                        manifest.modules.append(val)
        return manifest

def find_matching_texture(tex_handler: TextureHandler, name: str) -> Optional[str]:
    """Finds the best matching diffuse/color texture name in texture_handler for a material/submesh name."""
    if not name or not tex_handler.textures_by_name:
        return None
    name_low = name.lower().strip()
    if name_low in tex_handler.textures_by_name:
        cand = tex_handler.textures_by_name[name_low].name
        if any(x in cand.lower() for x in ('color', 'diffuse', 'alb')) or not any(x in cand.lower() for x in ('norm', 'normal', 'mask', 'spec', 'height')):
            return cand

    # Priority 1: exact / prefix / substring match on diffuse/color
    for k, v in tex_handler.textures_by_name.items():
        if (k.startswith(name_low) or name_low.startswith(k) or name_low in k or k in name_low) and any(x in k for x in ('color', 'diffuse', 'alb')) and not any(x in k for x in ('norm', 'normal', 'mask', 'spec', 'height', 'rough')):
            return v.name

    # Priority 2: token match with singular/plural normalization
    stop = {'hom', 'hun', 'sub', 'bil', 'level', 'mod', 'default', 'set', 'part', 'merged', 'partition', 'shape', 'shader', 'asset', 'assets', 'shared'}
    raw_tokens = [t for t in re.findall(r'[a-z0-9]+', name_low) if len(t) > 2 and t not in stop]
    norm_tokens = [t[:-1] if t.endswith('s') and len(t) > 3 else t for t in raw_tokens]

    best_cand = None
    best_score = 0
    for k, v in tex_handler.textures_by_name.items():
        if not any(x in k for x in ('color', 'diffuse', 'alb')):
            continue
        if any(x in k for x in ('norm', 'normal', 'mask', 'spec', 'height', 'rough')):
            continue
        score = 0
        for t in norm_tokens:
            if t in k or (len(t) > 4 and t[:-1] in k):
                score += len(t) * 2
        if score > best_score:
            best_score = score
            best_cand = v.name

    if best_score >= 6:
        return best_cand

    # Priority 3: any match
    for k, v in tex_handler.textures_by_name.items():
        if (k.startswith(name_low) or name_low.startswith(k) or name_low in k or k in name_low) and not any(x in k for x in ('norm', 'normal', 'mask', 'spec')):
            return v.name
    return None

def find_matching_normal(tex_handler: TextureHandler, diffuse_tex_name: Optional[str], material_name: str) -> Optional[str]:
    """Finds matching normal map for a diffuse texture or material name."""
    if not tex_handler.textures_by_name:
        return None
    cand_base = None
    if diffuse_tex_name:
        cand_base = re.sub(r'[-_](color|diffuse|alb).*$', '', diffuse_tex_name.lower())
    elif material_name:
        cand_base = material_name.lower().strip()

    if cand_base:
        norm_key = f"{cand_base}-normal"
        if norm_key in tex_handler.textures_by_name:
            return tex_handler.textures_by_name[norm_key].name
        for k, v in tex_handler.textures_by_name.items():
            if cand_base in k and any(x in k for x in ('norm', 'normal')) and not any(x in k for x in ('mask', 'spec', 'color')):
                return v.name
    return None

class LevelAssembler:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        candidate_dirs = [
            root_dir,
            os.path.join(root_dir, "pak32"),
            os.path.join(root_dir, "actor50"),
            os.path.join(root_dir, "texturedict1"),
            os.path.join(os.path.dirname(root_dir), "pak32"),
            os.path.join(os.path.dirname(root_dir), "actor50"),
            os.path.join(os.path.dirname(root_dir), "texturedict1"),
            r"D:\TLOUPS4\Extracted\pak32",
            r"D:\TLOUPS4\Extracted\actor50",
            r"D:\TLOUPS4\Extracted\texturedict1",
        ]
        seen = set()
        self.valid_dirs = []
        for d in candidate_dirs:
            norm = os.path.normpath(d)
            if norm not in seen and os.path.isdir(norm):
                seen.add(norm)
                self.valid_dirs.append(norm)

    def find_file(self, filename: str) -> Optional[str]:
        """Searches for a file across valid candidate directories."""
        for d in self.valid_dirs:
            c = os.path.join(d, filename)
            if os.path.exists(c):
                return c
        return None

    def read_spawner_instances(self, pak: PakFile) -> List[PlacedActorInstance]:
        """Extracts actor placement positions and orientations from SPAWNER_GROUP."""
        instances: List[PlacedActorInstance] = []
        sg_item = pak.get_first_item('SPAWNER_GROUP')
        if not sg_item:
            return instances

        res_abs = sg_item.abs_offset
        data = pak.data
        if res_abs + 48 > len(data):
            return instances

        is_pc = pak.magic in (2685, 68221)
        if is_pc:
            p_list = pak.read_ptr(res_abs + 0x38)
            list_count = struct.unpack_from('<I', data, res_abs + 0x40)[0] if res_abs + 0x44 <= len(data) else 0
        else:
            p_list = pak.read_ptr(res_abs + 0x28)
            list_count = struct.unpack_from('<I', data, res_abs + 0x30)[0] if res_abs + 0x34 <= len(data) else 0

        if not p_list or list_count == 0 or list_count > 5000:
            return instances

        for i in range(list_count):
            actor_ptr = pak.read_ptr(p_list + i * 8)
            if actor_ptr and 0 < actor_ptr + 48 <= len(data):
                px, py, pz = struct.unpack_from('<3f', data, actor_ptr)
                rx, ry, rz, rw = struct.unpack_from('<4f', data, actor_ptr + 16)

                # Check candidate pointer locations for name and asset type
                # In PS4: name at +32, type at +0x48 (72)
                # In PC: name at +0x30 (48), type at +0x50 (80)
                if is_pc:
                    name_ptr = pak.read_ptr(actor_ptr + 0x30) or pak.read_ptr(actor_ptr + 32)
                    t_ptr = pak.read_ptr(actor_ptr + 0x50) or pak.read_ptr(actor_ptr + 0x48)
                else:
                    name_ptr = pak.read_ptr(actor_ptr + 32) or pak.read_ptr(actor_ptr + 0x30)
                    t_ptr = pak.read_ptr(actor_ptr + 0x48) or pak.read_ptr(actor_ptr + 0x50)

                inst_name = pak.read_str_at(name_ptr) if name_ptr else f"actor_{i}"
                type_name = pak.read_str_at(t_ptr) if t_ptr else ""
                if type_name and len(type_name) > 1 and type_name.isprintable():
                    actor_type = type_name
                else:
                    actor_type = inst_name
                    actor_type = re.sub(r'-\d+$', '', actor_type)

                instances.append(PlacedActorInstance(
                    name=inst_name,
                    position=(px, py, pz),
                    rotation=(rx, ry, rz, rw),
                    actor_type=actor_type
                ))
        return instances

    def assemble_chunk(self, chunk_name: str, output_dir: str, 
                       export_glb: bool = True, export_gltf: bool = True,
                       include_actors: bool = True, all_lods: bool = True) -> Dict[str, Any]:
        """Assembles a location chunk with static geometry and placed actor instances."""
        clean_name = chunk_name.replace(".txt", "").replace(".pak", "")
        os.makedirs(output_dir, exist_ok=True)
        tex_output_dir = os.path.join(output_dir, "textures")

        # 1. Parse Manifest if present
        manifest_path = self.find_file(f"{clean_name}.txt")
        manifest = LevelManifest.parse_file(manifest_path) if manifest_path else LevelManifest(clean_name)

        # 2. Find Level PAK files (PS4 and PC naming variants)
        name_variants = [clean_name]
        unique_variants = [clean_name]

        related_paks = []
        chunk_ingame_paks = []

        for v in unique_variants:
            for pat in [
                f"{v}-tstrm.pak",
                f"{v}.pak",
                f"part-level-{v}.pak",
                f"{v}-script.pak",
                f"part-level-{v}-script.pak",
                f"{v}-render.pak",
            ]:
                fpath = self.find_file(pat)
                if fpath and fpath not in related_paks:
                    related_paks.append(fpath)

            for pat in [
                f"{v}-ingame.pak",
                f"{v}-ingame14.pak",
                f"{v}-script-ingame.pak",
            ]:
                fpath = self.find_file(pat)
                if fpath and fpath not in chunk_ingame_paks:
                    chunk_ingame_paks.append(fpath)

        for cache_name in manifest.packages:
            for pat in [
                f"{cache_name}-tstrm.pak",
                f"{cache_name}-render.pak",
                f"{cache_name}.pak",
                f"part-level-{cache_name}.pak",
            ]:
                c_pak = self.find_file(pat)
                if c_pak and c_pak not in related_paks:
                    related_paks.append(c_pak)

        writer = GLTFWriter(clean_name)
        tex_handler = TextureHandler()
        exported_textures = {}

        # Auto-load texture dictionary for hom-* chunks
        if clean_name.startswith("hom"):
            home_dict_path = None
            for cand_dir in self.valid_dirs:
                if "texturedict" in cand_dir.lower():
                    cand = os.path.join(cand_dir, "world-home-tstrm.pak")
                    if os.path.exists(cand) and os.path.getsize(cand) > 100000:
                        home_dict_path = cand
                        break
            if not home_dict_path:
                cand = r"D:\TLOUPS4\Extracted\texturedict1\world-home-tstrm.pak"
                if os.path.exists(cand) and os.path.getsize(cand) > 100000:
                    home_dict_path = cand

            if home_dict_path:
                try:
                    home_dict_pak = PakFile(home_dict_path)
                    tex_handler.load_from_pak(home_dict_pak)
                    print(f"[+] Loaded texture dictionary: {home_dict_path} ({len(tex_handler.textures_by_name)} textures, {len(tex_handler.textures_by_hex)} hashes)")
                except Exception as e:
                    print(f"[-] Warning: Failed to load texture dictionary {home_dict_path}: {e}")

        # 3. Load Level Textures and Static Geometry (Main chunk + Packages from manifest)
        static_submesh_count = 0
        for p_path in related_paks:
            try:
                tstrm_pak = PakFile(p_path)
                tex_handler.load_from_pak(tstrm_pak)
                # Export local textures from this specific PAK
                local_th = TextureHandler(tstrm_pak)
                local_exp = local_th.export_all(tex_output_dir)
                if local_exp:
                    exported_textures.update(local_exp)

                mb = MeshBuilder(tstrm_pak)
                for model in mb.models:
                    for sm in model.submeshes:
                        if not all_lods and sm.lod_index > 0:
                            continue
                        if not sm.positions or not sm.indices:
                            continue

                        # Deterministic texture resolution via exact 16-hex hash
                        matched_tex = None
                        matched_norm = None

                        if sm.diffuse_hash:
                            t_info = tex_handler.get_texture_by_hash(sm.diffuse_hash)
                            if t_info:
                                matched_tex = t_info.name
                                if t_info.raw_bytes:
                                    _, png_p = tex_handler.export_texture(t_info, tex_output_dir)
                                    if png_p:
                                        exported_textures[matched_tex] = png_p

                        if sm.normal_hash:
                            n_info = tex_handler.get_texture_by_hash(sm.normal_hash)
                            if n_info:
                                matched_norm = n_info.name
                                if n_info.raw_bytes:
                                    _, png_p = tex_handler.export_texture(n_info, tex_output_dir)
                                    if png_p:
                                        exported_textures[matched_norm] = png_p

                        # No fuzzy substitution: shaders without an albedo slot
                        # may use constants, lightmaps, or generated textures.
                        mat_name = sm.material_name or sm.name

                        png_rel = None
                        if matched_tex:
                            png_rel = os.path.join("textures", f"{matched_tex}.png").replace('\\', '/')
                        norm_rel = None
                        if matched_norm:
                            norm_rel = os.path.join("textures", f"{matched_norm}.png").replace('\\', '/')
                        mat_idx = writer.add_material(mat_name, base_color_tex=png_rel, normal_tex=norm_rel, extras={**transparency_extras(sm,tex_output_dir,tex_handler),'nd_diffuse_hash':sm.diffuse_hash,'nd_normal_hash':sm.normal_hash,'nd_texture_hashes':sm.texture_hashes,'nd_missing_albedo':bool(sm.diffuse_hash and not png_rel)})

                        mesh_idx = writer.add_submesh(sm, material_idx=mat_idx)
                        if mesh_idx >= 0:
                            writer.nodes.append({
                                "name": f"{os.path.basename(p_path).replace('.pak', '')}_{sm.name}",
                                "mesh": mesh_idx
                            })
                            static_submesh_count += 1
            except Exception as e:
                print(f"[-] Warning: Failed to process sub-chunk {p_path}: {e}")

        # 4. Read Placed Actor Instances
        placed_actors = []
        for ingame_path in chunk_ingame_paks:
            try:
                ingame_pak = PakFile(ingame_path)
                placed_actors.extend(self.read_spawner_instances(ingame_pak))
            except Exception as e:
                print(f"[-] Warning: Failed to read spawner instances from {ingame_path}: {e}")

        # 5. Optionally resolve and attach referenced actors
        spawned_count = 0
        if include_actors and placed_actors:
            # Cache loaded actor models: cname -> (actor_model, dict[sm_idx, mat_idx])
            actor_cache: Dict[str, Tuple[Optional[MeshModel], Dict[int, Optional[int]]]] = {}

            for inst in placed_actors:
                # Find matching actor pak in actor50 / actor97 / pak68
                cand_names = [inst.actor_type]
                clean_type = re.sub(r'-\d+$', '', inst.actor_type)
                if clean_type != inst.actor_type:
                    cand_names.append(clean_type)
                if clean_type.startswith('fx-'):
                    cand_names.append(clean_type[3:])
                for prefix in ("ap-", "ss-", "hom-", "hom1-", "hom2-", "hun-", "bil-", "bar-", "fx-"):
                    if clean_type.startswith(prefix):
                        cand_names.append(clean_type[len(prefix):])

                actor_model = None
                sm_mat_map: Dict[int, Optional[int]] = {}
                for cname in cand_names:
                    if cname in actor_cache:
                        actor_model, sm_mat_map = actor_cache[cname]
                        break

                    actor_pak_path = (
                        self.find_file(f"{cname}-tstrm.pak") or 
                        self.find_file(f"{cname}.pak") or 
                        self.find_file(f"{cname}-render.pak") or 
                        self.find_file(f"actor-{cname}.pak") or
                        self.find_file(f"part-actor-{cname}.pak") or
                        self.find_file(f"part-actor-{cname}-skel.pak")
                    )
                    if actor_pak_path:
                        a_pak = PakFile(actor_pak_path)
                        a_th = TextureHandler(a_pak)
                        a_exp = a_th.export_all(tex_output_dir)
                        if a_exp:
                            exported_textures.update(a_exp)
                        a_mb = MeshBuilder(a_pak)
                        if a_mb.models:
                            actor_model = a_mb.models[0]
                            # Build unique material and texture for each submesh
                            for sm_idx, sm in enumerate(actor_model.submeshes):
                                sm_query = sm.material_name or sm.name or cname
                                sm_tex_name = None
                                sm_norm_name = None

                                if sm.diffuse_hash:
                                    t_info = a_th.get_texture_by_hash(sm.diffuse_hash) or tex_handler.get_texture_by_hash(sm.diffuse_hash)
                                    if t_info:
                                        sm_tex_name = t_info.name
                                        if t_info.raw_bytes:
                                            _, png_p = tex_handler.export_texture(t_info, tex_output_dir)
                                            if png_p:
                                                exported_textures[sm_tex_name] = png_p

                                if sm.normal_hash:
                                    n_info = a_th.get_texture_by_hash(sm.normal_hash) or tex_handler.get_texture_by_hash(sm.normal_hash)
                                    if n_info:
                                        sm_norm_name = n_info.name
                                        if n_info.raw_bytes:
                                            _, png_p = tex_handler.export_texture(n_info, tex_output_dir)
                                            if png_p:
                                                exported_textures[sm_norm_name] = png_p

                                png_rel = None
                                if sm_tex_name:
                                    png_rel = os.path.join("textures", f"{sm_tex_name}.png").replace('\\', '/')
                                norm_rel = None
                                if sm_norm_name:
                                    norm_rel = os.path.join("textures", f"{sm_norm_name}.png").replace('\\', '/')
                                m_idx = writer.add_material(f"{cname}_{sm_query}", base_color_tex=png_rel, normal_tex=norm_rel, extras={**transparency_extras(sm,tex_output_dir,tex_handler),'nd_diffuse_hash':sm.diffuse_hash,'nd_normal_hash':sm.normal_hash,'nd_texture_hashes':sm.texture_hashes,'nd_missing_albedo':bool(sm.diffuse_hash and not png_rel)})
                                sm_mat_map[sm_idx] = m_idx
                            actor_cache[cname] = (actor_model, sm_mat_map)
                            break

                if actor_model:
                    for sm_idx, sm in enumerate(actor_model.submeshes):
                        if not all_lods and sm.lod_index > 0:
                            continue
                        mat_idx = sm_mat_map.get(sm_idx)
                        mesh_idx = writer.add_submesh(sm, material_idx=mat_idx)
                        if mesh_idx >= 0:
                            writer.nodes.append({
                                "name": f"{inst.name}_{sm.name}",
                                "mesh": mesh_idx,
                                "translation": list(inst.position),
                                "rotation": list(inst.rotation)
                            })
                            spawned_count += 1

        # 6. Export outputs
        from pathlib import Path
        from .static_lighting import export as export_lighting
        lighting_dir = Path(output_dir)/'static_lighting'
        lighting = export_lighting(related_paks,lighting_dir,owner_level=clean_name)
        writer.asset_extras['nd_static_lighting'] = {
            'uri':'static_lighting/lighting.json','records':len(lighting['records']),
            'reconstruction':'experimental'}
        glb_out = os.path.join(output_dir, f"{clean_name}.glb")
        gltf_out = os.path.join(output_dir, f"{clean_name}.gltf")

        if export_glb:
            writer.export_glb(glb_out)
        if export_gltf:
            writer.export_gltf(gltf_out)

        # 7. Write manifest report
        report = {
            "chunk_name": clean_name,
            "manifest_file": manifest_path,
            "level_id": manifest.level_id,
            "static_submeshes": static_submesh_count,
            "placed_actor_instances": len(placed_actors),
            "spawned_actor_submeshes": spawned_count,
            "textures_exported": len(exported_textures),
            "actors_in_manifest": manifest.actors,
            "static_lighting": str((lighting_dir/'lighting.json').resolve()),
            "static_lighting_records": len(lighting['records']),
            "static_lighting_warnings": lighting['warnings'],
            "output_glb": glb_out if export_glb else None,
            "output_gltf": gltf_out if export_gltf else None
        }

        with open(os.path.join(output_dir, "manifest.json"), 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)

        return report
