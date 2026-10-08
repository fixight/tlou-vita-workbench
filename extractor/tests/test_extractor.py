"""
test_extractor.py - Integration and unit tests for tlou_extractor package.
"""
import unittest
import os
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.mesh_builder import MeshBuilder
from tlou_extractor.texture_handler import TextureHandler
from tlou_extractor.skeleton_reader import SkeletonReader
from tlou_extractor.anim_reader import AnimationReader
from tlou_extractor.gltf_writer import GLTFWriter
from tlou_extractor.level_assembler import LevelAssembler

TEST_DATA_DIR = r"D:\TLOUPS4\Extracted"

class TestTLOUAssetExtractor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(TEST_DATA_DIR):
            raise unittest.SkipTest(f"Test data directory {TEST_DATA_DIR} not found")

    def test_pak_reader(self):
        pak_path = os.path.join(TEST_DATA_DIR, "actor50", "cell-phone-tstrm.pak")
        pak = PakFile(pak_path)
        self.assertEqual(pak.magic, 2681)
        self.assertGreater(len(pak.pages), 0)
        self.assertGreater(len(pak.all_items), 0)
        self.assertIn("GEOMETRY_1", pak.items_by_type)
        self.assertIn("VRAM_DESC", pak.items_by_type)

    def test_texture_handler(self):
        pak_path = os.path.join(TEST_DATA_DIR, "actor50", "cell-phone-tstrm.pak")
        pak = PakFile(pak_path)
        th = TextureHandler(pak)
        self.assertGreater(len(th.textures_by_hash), 0)

        first_tex = list(th.textures_by_hash.values())[0]
        dds_bytes = th.build_dds(first_tex)
        self.assertTrue(dds_bytes.startswith(b'DDS '))

    def test_mesh_builder(self):
        pak_path = os.path.join(TEST_DATA_DIR, "actor50", "cell-phone-tstrm.pak")
        pak = PakFile(pak_path)
        mb = MeshBuilder(pak)
        self.assertGreater(len(mb.models), 0)

        submeshes = mb.models[0].submeshes
        self.assertGreater(len(submeshes), 0)
        sm = submeshes[0]
        self.assertGreater(len(sm.positions), 0)
        self.assertGreater(len(sm.indices), 0)
        self.assertGreater(len(sm.normals), 0)
        self.assertGreater(len(sm.uv0), 0)

    def test_skeleton_reader(self):
        skel_pak_path = os.path.join(TEST_DATA_DIR, "actor50", "sarah-skel-tstrm.pak")
        pak = PakFile(skel_pak_path)
        skel = SkeletonReader.read_skeleton(pak)
        self.assertIsNotNone(skel)
        self.assertGreater(len(skel.bones), 0)
        self.assertEqual(skel.bones[0].name, "root")

    def test_skeleton_bone_parenting(self):
        skel_pak_path = os.path.join(TEST_DATA_DIR, "actor50", "sarah-skel-tstrm.pak")
        pak = PakFile(skel_pak_path)
        skel = SkeletonReader.read_skeleton(pak)
        self.assertIsNotNone(skel)

        # 1. Eyeballs are parented to headb (not ankle)
        l_eyeball = skel.bone_by_name['l_eyeball']
        self.assertEqual(skel.bones[l_eyeball.parent_index].name, 'headb')
        l_eyeball_pupil = skel.bone_by_name['l_eyeball_pupil']
        self.assertEqual(skel.bones[l_eyeball_pupil.parent_index].name, 'l_eyeball')

        # 2. Face bones (jaw, lips) are parented to headb / jaw (not root)
        jaw = skel.bone_by_name['jaw']
        self.assertEqual(skel.bones[jaw.parent_index].name, 'headb')
        l_lip = skel.bone_by_name['l_lip_corner']
        self.assertIn(skel.bones[l_lip.parent_index].name, ('headb', 'jaw'))

        # 3. Hand/fingers are parented to l_wrist / l_palm (not root)
        pinky = next(b for b in skel.bones if 'pinky' in b.name.lower() and 'l' in b.name.lower())
        self.assertIn(skel.bones[pinky.parent_index].name, ('l_palm', 'l_wrist', 'pinky_a_l'))

        # 4. Verify young-joel skeleton
        joel_skel_pak = PakFile(os.path.join(TEST_DATA_DIR, "actor50", "young-joel-skel-tstrm.pak"))
        joel_skel = SkeletonReader.read_skeleton(joel_skel_pak)
        self.assertIsNotNone(joel_skel)
        self.assertEqual(joel_skel.bones[joel_skel.bone_by_name['l_eyeball'].parent_index].name, 'headb')
        self.assertEqual(joel_skel.bones[joel_skel.bone_by_name['jaw'].parent_index].name, 'headb')
        self.assertEqual(joel_skel.bones[joel_skel.bone_by_name['l_palm'].parent_index].name, 'l_wrist')

        # 5. Verify small prop skeleton does not get inflated to 11 bones
        cab_skel_pak = PakFile(os.path.join(TEST_DATA_DIR, "actor50", "cabinet-door-skel-l-tstrm.pak"))
        cab_skel = SkeletonReader.read_skeleton(cab_skel_pak)
        self.assertIsNotNone(cab_skel)
        self.assertEqual(len(cab_skel.bones), 2)
        self.assertEqual(cab_skel.bones[1].parent_index, 0)

    def test_anim_reader(self):
        anim_pak_path = os.path.join(TEST_DATA_DIR, "actor50", "anim-sarah-player-tstrm.pak")
        pak = PakFile(anim_pak_path)
        clips = AnimationReader.read_animations(pak)
        self.assertGreater(len(clips), 0)
        self.assertGreater(len(clips[0].tracks), 0)

    def test_spine_bone_rotations_natural_bounds(self):
        import math
        skel_pak = PakFile(os.path.join(TEST_DATA_DIR, "actor50", "sarah-skel-tstrm.pak"))
        skel = SkeletonReader.read_skeleton(skel_pak)
        anim_pak = PakFile(os.path.join(TEST_DATA_DIR, "actor50", "anim-sarah-player-tstrm.pak"))
        clips = AnimationReader.read_animations(anim_pak, skeleton=skel)
        self.assertGreater(len(clips), 0)

        def quat_angle_deg(q1, q2):
            dot = abs(sum(a * b for a, b in zip(q1, q2)))
            dot = min(1.0, max(-1.0, dot))
            return 2.0 * math.acos(dot) * 180.0 / math.pi

        spine_bones = ['spinea', 'spineb', 'spinec', 'spined', 'neck', 'heada', 'headb']
        # Test first clip plus representative locomotion clips
        test_clip_names = {"sar-p-tired-walk-fw", "sar-p-walk-fw", "sar-p-stairs-run-fw-down", "sar-p-tired-walk-bw"}
        tested_clips = [c for c in clips if c.name in test_clip_names or c == clips[0]]

        for clip in tested_clips:
            tested_bones = []
            for tr in clip.tracks:
                b_name = skel.bones[tr.node_index].name.lower()
                if b_name in spine_bones and tr.target_path == 'rotation':
                    rest_q = skel.bones[tr.node_index].rotation
                    diff = quat_angle_deg(tr.values[0], rest_q)
                    self.assertLess(diff, 35.0, f"Spine bone {b_name} in clip {clip.name} frame 0 rotation error too large: {diff:.1f} deg")
                    tested_bones.append(b_name)
            self.assertGreaterEqual(len(tested_bones), 5, f"At least 5 spine bones should have rotation tracks in {clip.name}")

    def test_animation_mesh_stability(self):
        import numpy as np
        skel_pak = PakFile(os.path.join(TEST_DATA_DIR, "actor50", "sarah-skel-tstrm.pak"))
        skel = SkeletonReader.read_skeleton(skel_pak)
        mesh_pak = PakFile(os.path.join(TEST_DATA_DIR, "actor50", "sarah-tstrm.pak"))
        mb = MeshBuilder(mesh_pak)
        anim_pak = PakFile(os.path.join(TEST_DATA_DIR, "actor50", "anim-sarah-player-tstrm.pak"))
        clips = AnimationReader.read_animations(anim_pak, skeleton=skel)
        self.assertGreater(len(clips), 0)

        clip = clips[0]
        for tr in clip.tracks:
            self.assertGreaterEqual(tr.node_index, 0)
            self.assertLess(tr.node_index, len(skel.bones))
            self.assertTrue(np.isfinite(np.array(tr.values)).all())

        # Check deformed foot vertices do not explode or spike into floor
        world_mats = []
        for bone in skel.bones:
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

        ibms = [np.linalg.inv(wm) for wm in world_mats]
        all_positions = []
        head_vert_indices = []
        foot_vert_indices = []
        headb_idx = skel.bone_by_name['headb'].index
        l_ankle_idx = skel.bone_by_name['l_ankle'].index
        r_ankle_idx = skel.bone_by_name['r_ankle'].index

        for m in mb.models:
            for sm in m.submeshes:
                if not sm.positions or not sm.bone_indices:
                    continue
                base_v = len(all_positions)
                for i, (p, bi, bw) in enumerate(zip(sm.positions, sm.bone_indices, sm.bone_weights)):
                    all_positions.append((p, bi, bw))
                    if any(b in (l_ankle_idx, r_ankle_idx) for b, w in zip(bi, bw) if w > 0.3):
                        foot_vert_indices.append(base_v + i)
                    if any(b == headb_idx for b, w in zip(bi, bw) if w > 0.3):
                        head_vert_indices.append(base_v + i)

        for frame in [0, 10, 30]:
            anim_local_mats = []
            for b in skel.bones:
                t = list(b.translation)
                r = list(b.rotation)
                s = list(b.scale)
                for tr in clip.tracks:
                    if tr.node_index == b.index:
                        val = tr.values[frame]
                        if tr.target_path == 'translation': t = val
                        elif tr.target_path == 'rotation': r = val
                        elif tr.target_path == 'scale': s = val
                qx, qy, qz, qw = r
                x2, y2, z2 = qx + qx, qy + qy, qz + qz
                xx, xy, xz = qx * x2, qx * y2, qx * z2
                yy, yz, zz = qy * y2, qy * z2, qz * z2
                wx, wy, wz = qw * x2, qw * y2, qw * z2
                sx, sy, sz = s
                tx, ty, tz = t
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
                anim_local_mats.append(loc_m)

            anim_world_mats = []
            for b in skel.bones:
                if 0 <= b.parent_index < len(anim_world_mats):
                    wm = anim_world_mats[b.parent_index] @ anim_local_mats[b.index]
                else:
                    wm = anim_local_mats[b.index]
                anim_world_mats.append(wm)

            skin_mats = [wm @ ibm for wm, ibm in zip(anim_world_mats, ibms)]

            # Feet Y range check
            foot_pts = []
            for idx in foot_vert_indices:
                p, bi, bw = all_positions[idx]
                vp = np.array([p[0], p[1], p[2], 1.0], dtype=np.float32)
                sp = np.zeros(4, dtype=np.float32)
                for b, w in zip(bi, bw):
                    if w > 0:
                        sp += w * (skin_mats[b] @ vp)
                foot_pts.append(sp[:3])
            foot_pts = np.array(foot_pts)
            min_y = foot_pts[:, 1].min()
            self.assertGreater(min_y, -0.2, f"Exploding foot spike at frame {frame}: min_y={min_y}")

            # Head shape retention check
            head_pts = []
            for idx in head_vert_indices:
                p, bi, bw = all_positions[idx]
                vp = np.array([p[0], p[1], p[2], 1.0], dtype=np.float32)
                sp = np.zeros(4, dtype=np.float32)
                for b, w in zip(bi, bw):
                    if w > 0:
                        sp += w * (skin_mats[b] @ vp)
                head_pts.append(sp[:3])
            head_pts = np.array(head_pts)
            head_size = head_pts.max(axis=0) - head_pts.min(axis=0)
            self.assertLess(max(head_size), 0.6, f"Head deformed into elongated shape: {head_size}")

        # Validate Joel channels without excluding legitimate root/toe animation.
        j_skel = SkeletonReader.read_skeleton(PakFile(os.path.join(
            TEST_DATA_DIR, "actor50", "young-joel-skel-tstrm.pak")))
        j_clips = AnimationReader.read_animations(PakFile(os.path.join(
            TEST_DATA_DIR, "actor50", "anim-joel-tstrm.pak")), skeleton=j_skel)
        self.assertGreater(len(j_clips), 0)
        for tr in j_clips[0].tracks:
            self.assertGreaterEqual(tr.node_index, 0)
            self.assertLess(tr.node_index, len(j_skel.bones))
            self.assertTrue(np.isfinite(np.array(tr.values)).all())

    def test_level_chunk_assembly(self):
        assembler = LevelAssembler(TEST_DATA_DIR)
        out_test_dir = "./tests_temp_out"
        report = assembler.assemble_chunk("hom-house-interior", out_test_dir, all_lods=True)
        self.assertEqual(report["chunk_name"], "hom-house-interior")
        self.assertGreater(report["static_submeshes"], 0)
        self.assertGreater(report["placed_actor_instances"], 0)
        self.assertTrue(os.path.exists(report["output_glb"]))
        self.assertTrue(os.path.exists(report["output_gltf"]))

if __name__ == "__main__":
    unittest.main()
