"""
cli.py - Command Line Interface for The Last of Us Remastered (PS4) Asset Extractor.
"""
import argparse
import os
import sys
from typing import Optional

from .pak_reader import PakFile
from .mesh_builder import MeshBuilder
from .texture_handler import TextureHandler
from .skeleton_reader import SkeletonReader
from .anim_reader import AnimationReader
from .gltf_writer import GLTFWriter
from .level_assembler import LevelAssembler, find_matching_texture, find_matching_normal

def is_shadow_or_collision_submesh(sm) -> bool:
    """Identifies shadow caster proxies, collision proxies, or blocker meshes."""
    name_l = sm.name.lower()
    mat_l = (sm.material_name or "").lower()
    if any(k in name_l for k in ("shadowproxy", "shadow_geo", "shadow_lod", "shadowblocker")):
        return True
    if any(k in mat_l for k in ("shadowblocker", "lib-shadowblocker")):
        return True
    if any(k in name_l for k in ("collision", "col_lod")):
        return True
    return False

def extract_single_pak(pak_path: str, output_dir: str, 
                       root_dir: Optional[str] = None,
                       export_glb: bool = True, 
                       export_gltf: bool = True,
                       export_dds: bool = True, 
                       export_png: bool = True,
                       all_lods: bool = True) -> bool:
    """Extracts a single model PAK file with its skeleton, textures, and animations."""
    if not os.path.exists(pak_path):
        print(f"[ERROR] File not found: {pak_path}")
        return False

    base_name = os.path.splitext(os.path.basename(pak_path))[0]
    # Clean suffix like -tstrm
    model_name = base_name.replace("-tstrm", "").replace("-ingame14", "")
    target_out = os.path.join(output_dir, model_name)
    os.makedirs(target_out, exist_ok=True)
    tex_out = os.path.join(target_out, "textures")

    print(f"[*] Processing PAK: {pak_path}")
    pak = PakFile(pak_path)

    # 1. Geometry
    mb = MeshBuilder(pak)
    if not mb.models and root_dir and not pak_path.endswith("-tstrm.pak"):
        cand_tstrm = os.path.join(os.path.dirname(pak_path), f"{model_name}-tstrm.pak")
        if os.path.exists(cand_tstrm):
            mb = MeshBuilder(PakFile(cand_tstrm))

    if not mb.models:
        print(f"[!] No 3D geometry found in {pak_path}")
        return False

    # Collect texture hashes & material names referenced by submeshes
    needed_hashes = set()
    needed_names = set()
    for model in mb.models:
        for sm in model.submeshes:
            if is_shadow_or_collision_submesh(sm):
                continue
            if sm.diffuse_hash:
                needed_hashes.add(sm.diffuse_hash.lower())
            if sm.normal_hash:
                needed_hashes.add(sm.normal_hash.lower())
            if sm.texture_hashes:
                for th_val in sm.texture_hashes:
                    needed_hashes.add(th_val.lower())
            if sm.material_name:
                needed_names.add(sm.material_name.lower())

    # 2. Textures
    th = TextureHandler(pak)
    # Check for streaming pak if not already -tstrm
    if root_dir and not pak_path.endswith("-tstrm.pak"):
        cand_tstrm = os.path.join(os.path.dirname(pak_path), f"{model_name}-tstrm.pak")
        if os.path.exists(cand_tstrm):
            print(f"[*] Found streaming texture PAK: {cand_tstrm}")
            st_pak = PakFile(cand_tstrm)
            th.load_from_pak(st_pak)

    # Check for master texture dictionaries (world-home-tstrm.pak, sp-common-tstrm.pak, common-tstrm.pak)
    cand_dict_dirs = []
    if root_dir:
        cand_dict_dirs.append(os.path.join(root_dir, "texturedict1"))
    p_parent = os.path.dirname(os.path.abspath(pak_path))
    if os.path.basename(p_parent) in ("actor50", "pak32", "texturedict1"):
        cand_dict_dirs.append(os.path.join(os.path.dirname(p_parent), "texturedict1"))
    cand_dict_dirs.append(r"D:\TLOUPS4\Extracted\texturedict1")

    for t_dir in cand_dict_dirs:
        if os.path.isdir(t_dir):
            for dict_name in ("world-home-tstrm.pak", "sp-common-tstrm.pak", "common-tstrm.pak"):
                dict_file = os.path.join(t_dir, dict_name)
                if os.path.exists(dict_file):
                    try:
                        th.load_from_pak(PakFile(dict_file))
                    except Exception:
                        pass
            break

    exported_tex = th.export_all(tex_out, export_dds=export_dds, export_png=export_png,
                                 needed_hashes=needed_hashes, needed_names=needed_names)
    if exported_tex:
        print(f"[+] Exported {len(exported_tex)} texture(s)")

    # 3. Skeleton
    # Normalize root_dir
    effective_root = root_dir or ""
    if os.path.basename(effective_root) in ("actor50", "pak32", "texturedict1"):
        effective_root = os.path.dirname(effective_root)
    actor_dir = os.path.join(effective_root, "actor50") if effective_root else os.path.dirname(pak_path)

    # 3. Skeleton
    skel = SkeletonReader.read_skeleton(pak)
    # Check external skeleton package (e.g. *-skel.pak or *-base.pak)
    if not skel:
        cand_skels = [
            os.path.join(actor_dir, f"{model_name}-skel.pak"),
            os.path.join(actor_dir, f"{model_name}-skel-tstrm.pak"),
            os.path.join(actor_dir, f"{model_name}-base.pak"),
            os.path.join(actor_dir, f"{model_name}.pak"),
        ]
        # Common skeletons (joel-skel, sarah-skel, infected-skel, etc.)
        for part in model_name.split("-"):
            if part in ("joel", "sarah", "tommy", "ellie", "runner", "clicker", "bloater", "infected", "civilian", "tess"):
                cand_skels.append(os.path.join(actor_dir, f"{part}-skel-tstrm.pak"))
                cand_skels.append(os.path.join(actor_dir, f"{part}-skel.pak"))
        if "inf-" in model_name or "infected" in model_name or "runner" in model_name:
            if "fem" in model_name:
                cand_skels.append(os.path.join(actor_dir, "infected-fem-skel-tstrm.pak"))
            cand_skels.append(os.path.join(actor_dir, "infected-skel-tstrm.pak"))
        if "civilian" in model_name:
            if "fem" in model_name:
                cand_skels.append(os.path.join(actor_dir, "civilian-fem-skel-tstrm.pak"))
            cand_skels.append(os.path.join(actor_dir, "civilian-skel-tstrm.pak"))

        for c_skel in cand_skels:
            if os.path.exists(c_skel):
                print(f"[*] Found referenced skeleton: {c_skel}")
                skel = SkeletonReader.read_skeleton(PakFile(c_skel))
                if skel:
                    break

    if skel:
        print(f"[+] Loaded skeleton with {len(skel.bones)} bone(s)")

    # 4. Animations
    clips = AnimationReader.read_animations(pak, skeleton=skel)
    # Check external animation stream (e.g. anim-<name>-tstrm.pak)
    cand_anims = [
        os.path.join(actor_dir, f"anim-{model_name}-tstrm.pak"),
        os.path.join(actor_dir, f"anim-{model_name}.pak"),
    ]
    for part in model_name.split("-"):
        if part in ("joel", "sarah", "tommy", "ellie", "civilian", "runner", "clicker", "infected"):
            cand_anims.append(os.path.join(actor_dir, f"anim-{part}-player-tstrm.pak"))
            cand_anims.append(os.path.join(actor_dir, f"anim-{part}-tstrm.pak"))
    if "inf-" in model_name or "infected" in model_name or "runner" in model_name:
        cand_anims.append(os.path.join(actor_dir, "anim-runner-tstrm.pak"))
        cand_anims.append(os.path.join(actor_dir, "anim-infected-hom-tstrm.pak"))
        cand_anims.append(os.path.join(actor_dir, "anim-clicker-tstrm.pak"))
        cand_anims.append(os.path.join(actor_dir, "anim-inf-shared-tstrm.pak"))
    if "civilian" in model_name:
        cand_anims.append(os.path.join(actor_dir, "anim-civilian-hom-tstrm.pak"))
        cand_anims.append(os.path.join(actor_dir, "anim-civilian-hom-female-tstrm.pak"))

    # Resolve the source pose layout from AC/AH signatures for every bank.
    # A bank can also contain partner actors, doors, hair or backpack clips.
    for c_anim in dict.fromkeys(cand_anims):
        if os.path.exists(c_anim):
            ext_clips = AnimationReader.read_animations(PakFile(c_anim), skeleton=skel)
            if ext_clips:
                print(f"[*] Found {len(ext_clips)} referenced animation(s) in {os.path.basename(c_anim)}")
                clips.extend(ext_clips)
    unique = {}
    for clip in clips:
        unique.setdefault((clip.name, clip.source_rig_id), clip)
    clips = list(unique.values())

    # 5. Assemble GLTF
    writer = GLTFWriter(model_name)
    skin_idx = None
    joint_nodes = []
    if skel:
        skin_idx, joint_nodes = writer.add_skeleton(skel)

    # 5. Assemble GLTF with Multi-Material Submesh Assignment
    mat_cache = {}
    submesh_count = 0

    for model in mb.models:
        for sm in model.submeshes:
            if not all_lods and sm.lod_index > 0:
                continue
            if is_shadow_or_collision_submesh(sm):
                continue
            if not sm.positions or not sm.indices:
                continue

            diff_rel = None
            norm_rel = None

            # Resolve diffuse texture via exact 16-hex hash
            if sm.diffuse_hash:
                dh = sm.diffuse_hash.lower()
                if dh in exported_tex and exported_tex[dh].get('png'):
                    diff_rel = os.path.join("textures", f"{exported_tex[dh]['name']}.png").replace('\\', '/')
                else:
                    t_info = th.get_texture_by_hash(dh)
                    if t_info:
                        _, p_png = th.export_texture(t_info, tex_out, export_dds=export_dds, export_png=export_png)
                        if p_png:
                            exported_tex[dh] = {"name": t_info.name, "png": p_png}
                            diff_rel = os.path.join("textures", f"{t_info.name}.png").replace('\\', '/')

            # Resolve normal texture via exact 16-hex hash
            if sm.normal_hash:
                nh = sm.normal_hash.lower()
                if nh in exported_tex and exported_tex[nh].get('png'):
                    norm_rel = os.path.join("textures", f"{exported_tex[nh]['name']}.png").replace('\\', '/')
                else:
                    n_info = th.get_texture_by_hash(nh)
                    if n_info:
                        _, p_png = th.export_texture(n_info, tex_out, export_dds=export_dds, export_png=export_png)
                        if p_png:
                            exported_tex[nh] = {"name": n_info.name, "png": p_png}
                            norm_rel = os.path.join("textures", f"{n_info.name}.png").replace('\\', '/')

            # Fallback by material_name if hash resolution didn't find diffuse
            if not diff_rel and sm.material_name:
                matched_tex = find_matching_texture(th, sm.material_name)
                if matched_tex:
                    t_info = th.textures_by_name.get(matched_tex.lower())
                    if t_info:
                        _, p_png = th.export_texture(t_info, tex_out, export_dds=export_dds, export_png=export_png)
                        if p_png:
                            diff_rel = os.path.join("textures", f"{t_info.name}.png").replace('\\', '/')
                if not norm_rel:
                    matched_norm = find_matching_normal(th, matched_tex, sm.material_name)
                    if matched_norm:
                        n_info = th.textures_by_name.get(matched_norm.lower())
                        if n_info:
                            _, p_png = th.export_texture(n_info, tex_out, export_dds=export_dds, export_png=export_png)
                            if p_png:
                                norm_rel = os.path.join("textures", f"{n_info.name}.png").replace('\\', '/')

            mat_name = sm.material_name or f"{model_name}_sm{submesh_count}"
            mat_key = (diff_rel, norm_rel, mat_name, sm.transparency_hash)
            if mat_key not in mat_cache:
                from .material_transparency import transparency_extras
                extras = transparency_extras(sm,tex_out,th,export_png=export_png)
                if sm.diffuse_hash:
                    extras["diffuse_hash"] = sm.diffuse_hash
                if sm.normal_hash:
                    extras["normal_hash"] = sm.normal_hash
                mat_cache[mat_key] = writer.add_material(mat_name, base_color_tex=diff_rel, normal_tex=norm_rel, extras=extras)

            sm_mat_idx = mat_cache[mat_key]
            mesh_idx = writer.add_submesh(sm, material_idx=sm_mat_idx)
            if mesh_idx >= 0:
                node_data = {
                    "name": sm.name,
                    "mesh": mesh_idx
                }
                if skin_idx is not None:
                    node_data["skin"] = skin_idx
                writer.nodes.append(node_data)
                submesh_count += 1

    if clips and joint_nodes:
        for c in clips:
            writer.add_animation(c, joint_nodes)

    # Export files
    if not skel and pak.magic in (2681,68217):
        from pathlib import Path
        from .static_lighting import export as export_lighting
        lighting_sources=[pak_path]
        if not pak.get_items('GEOMETRY_1'):
            candidate=os.path.join(os.path.dirname(pak_path),f'{model_name}-tstrm.pak')
            if os.path.isfile(candidate): lighting_sources.append(candidate)
        lighting=export_lighting(lighting_sources,Path(target_out)/'static_lighting',owner_level=model_name)
        writer.asset_extras['nd_static_lighting']={
            'uri':'static_lighting/lighting.json','records':len(lighting['records']),
            'reconstruction':'experimental'}
    glb_path = os.path.join(target_out, f"{model_name}.glb")
    gltf_path = os.path.join(target_out, f"{model_name}.gltf")

    if export_glb:
        writer.export_glb(glb_path)
        print(f"[+] Exported GLB: {glb_path} ({os.path.getsize(glb_path):,} bytes)")

    if export_gltf:
        writer.export_gltf(gltf_path)
        print(f"[+] Exported GLTF: {gltf_path} ({os.path.getsize(gltf_path):,} bytes)")

    return True

def main():
    parser = argparse.ArgumentParser(
        description="The Last of Us Remastered (PS4) Asset Extractor - Parses level chunks, static geometry, models, animations, and textures."
    )
    parser.add_argument("-i", "--input", required=True, help="Path to extracted assets root folder or a specific .pak file")
    parser.add_argument("-o", "--output", default="./output", help="Output directory (default: ./output)")
    parser.add_argument("-c", "--chunk", help="Chunk/level name to assemble (e.g. hom-house-interior, hom-road-chunk-1)")
    parser.add_argument("-f", "--file", help="Specific .pak file to extract (relative or absolute path)")
    parser.add_argument("--batch-actors", action="store_true", help="Batch extract all models from actor50 folder")
    parser.add_argument("--format", choices=["glb", "gltf", "both"], default="both", help="3D output format (default: both)")
    parser.add_argument("--textures", choices=["dds", "png", "both", "none"], default="both", help="Texture format (default: both)")
    parser.add_argument("--lods", choices=["all", "lod0"], default="all", help="LOD extraction (default: all)")
    parser.add_argument("--no-actors", action="store_true", help="Skip spawning placed actors in chunk assembly mode")

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    export_glb = args.format in ("glb", "both")
    export_gltf = args.format in ("gltf", "both")
    export_dds = args.textures in ("dds", "both")
    export_png = args.textures in ("png", "both")
    all_lods = (args.lods == "all")

    # Mode 1: Chunk / Level Assembly
    if args.chunk:
        print(f"=== Assembling Level Chunk: {args.chunk} ===")
        assembler = LevelAssembler(input_path)
        out_chunk_dir = os.path.join(output_dir, args.chunk)
        report = assembler.assemble_chunk(
            chunk_name=args.chunk,
            output_dir=out_chunk_dir,
            export_glb=export_glb,
            export_gltf=export_gltf,
            include_actors=not args.no_actors,
            all_lods=all_lods
        )
        print("\n=== Assembly Finished ===")
        print(f"Static submeshes: {report['static_submeshes']}")
        print(f"Placed actor instances: {report['placed_actor_instances']}")
        print(f"Spawned actor submeshes: {report['spawned_actor_submeshes']}")
        print(f"Textures exported: {report['textures_exported']}")
        if report['output_glb']:
            print(f"GLB Output: {report['output_glb']}")
        if report['output_gltf']:
            print(f"GLTF Output: {report['output_gltf']}")
        return

    # Mode 2: Single File Extraction
    target_file = args.file
    if not target_file and os.path.isfile(input_path):
        target_file = input_path

    if target_file:
        full_pak_path = target_file if os.path.isabs(target_file) else os.path.join(input_path, target_file)
        root_dir = input_path if os.path.isdir(input_path) else os.path.dirname(input_path)
        print(f"=== Extracting Single Model: {full_pak_path} ===")
        extract_single_pak(
            pak_path=full_pak_path,
            output_dir=output_dir,
            root_dir=root_dir,
            export_glb=export_glb,
            export_gltf=export_gltf,
            export_dds=export_dds,
            export_png=export_png,
            all_lods=all_lods
        )
        return

    # Mode 3: Batch Extract All Actors
    if args.batch_actors:
        actor_dir = os.path.join(input_path, "actor50") if os.path.isdir(os.path.join(input_path, "actor50")) else input_path
        print(f"=== Batch Extracting Actors from {actor_dir} ===")
        paks = [f for f in os.listdir(actor_dir) if f.endswith(".pak") and not f.startswith("anim-")]
        print(f"Found {len(paks)} actor pak(s)")
        count = 0
        for p in paks:
            p_full = os.path.join(actor_dir, p)
            if extract_single_pak(
                pak_path=p_full,
                output_dir=os.path.join(output_dir, "actors"),
                root_dir=input_path,
                export_glb=export_glb,
                export_gltf=export_gltf,
                export_dds=export_dds,
                export_png=export_png,
                all_lods=all_lods
            ):
                count += 1
        print(f"=== Batch Finished: Successfully extracted {count} / {len(paks)} actors ===")
        return

    # If no specific mode chosen, display help
    parser.print_help()

if __name__ == "__main__":
    main()
