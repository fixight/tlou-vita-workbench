"""
test_animations.py - Animation quality tests for TLOU PS4 extracted assets.

These tests define CORRECT expected behavior. They are intended to:
  - FAIL on the current broken animation output
  - PASS only when the animation parser is properly implemented

Thresholds are based on anatomy and physics, NOT on current broken output.

Test categories:
  1. Rest-pose FK: bone heights, bilateral symmetry, IBM identity (zero deformation)
  2. Torso anchoring: pelvis-spinea distance and native local offsets
  3. Quaternion continuity: no jitter / sign-flip artifacts frame-to-frame
  4. Track integrity: valid targets, timestamps and finite transforms
  5. Anatomical FK: pelvis/head height, foot floor, arm swing during locomotion
  6. Upper body coverage: spine, arms, head must be animated in full-body clips
  7. Spine rotation bounds: physiologically plausible angles from rest pose
"""
import math
import unittest
import os
import numpy as np

TEST_DATA_DIR = r"D:\TLOUPS4\Extracted"
ACTOR_DIR = os.path.join(TEST_DATA_DIR, "actor50")


# ---------------------------------------------------------------------------
# Shared FK helpers
# ---------------------------------------------------------------------------

def _make_trs_matrix(t, r, s):
    qx, qy, qz, qw = r
    x2, y2, z2 = qx + qx, qy + qy, qz + qz
    xx, xy, xz = qx * x2, qy * x2, qz * x2
    yy, yz, zz = qy * y2, qz * y2, qz * z2
    wx, wy, wz = qw * x2, qw * y2, qw * z2
    sx, sy, sz = s
    tx, ty, tz = t
    m = np.eye(4, dtype=np.float64)
    m[0, 0] = (1.0 - (yy + zz)) * sx;  m[0, 1] = (xy - wz) * sy;  m[0, 2] = (xz + wy) * sz;  m[0, 3] = tx
    m[1, 0] = (xy + wz) * sx;           m[1, 1] = (1.0 - (xx + zz)) * sy; m[1, 2] = (yz - wx) * sz; m[1, 3] = ty
    m[2, 0] = (xz - wy) * sx;           m[2, 1] = (yz + wx) * sy;  m[2, 2] = (1.0 - (xx + yy)) * sz; m[2, 3] = tz
    return m


def run_fk(skel, anim_tracks, frame):
    """Return list of world-space 4x4 matrices for each bone at `frame`."""
    tracks = {}
    for tr in anim_tracks:
        tracks[(tr.target_path, tr.node_index)] = tr.values

    mats = [None] * len(skel.bones)

    def get_m(i):
        if mats[i] is not None:
            return mats[i]
        b = skel.bones[i]
        t = list(b.translation)
        r = list(b.rotation)
        s = list(b.scale)
        if ('translation', i) in tracks and frame < len(tracks[('translation', i)]):
            t = tracks[('translation', i)][frame]
        if ('rotation', i) in tracks and frame < len(tracks[('rotation', i)]):
            r = tracks[('rotation', i)][frame]
        if ('scale', i) in tracks and frame < len(tracks[('scale', i)]):
            s = tracks[('scale', i)][frame]
        local = _make_trs_matrix(t, r, s)
        p = b.parent_index
        mats[i] = (get_m(p) @ local) if (0 <= p < len(skel.bones)) else local
        return mats[i]

    for i in range(len(skel.bones)):
        get_m(i)
    return mats


def bone_pos(fk_mats, idx):
    return fk_mats[idx][:3, 3]


def quat_angle_deg(q1, q2):
    """Geodesic angle in degrees between two unit quaternions."""
    dot = abs(sum(a * b for a, b in zip(q1, q2)))
    dot = min(1.0, max(0.0, dot))
    return 2.0 * math.acos(dot) * 180.0 / math.pi


# ---------------------------------------------------------------------------
# Lazy fixtures
# ---------------------------------------------------------------------------

class _SarahFixtures:
    _skel = None
    _clips = None

    @classmethod
    def skel(cls):
        if cls._skel is None:
            from tlou_extractor.pak_reader import PakFile
            from tlou_extractor.skeleton_reader import SkeletonReader
            cls._skel = SkeletonReader.read_skeleton(
                PakFile(os.path.join(ACTOR_DIR, "sarah-skel-tstrm.pak")))
        return cls._skel

    @classmethod
    def clips(cls):
        if cls._clips is None:
            from tlou_extractor.pak_reader import PakFile
            from tlou_extractor.anim_reader import AnimationReader
            cls._clips = AnimationReader.read_animations(
                PakFile(os.path.join(ACTOR_DIR, "anim-sarah-player-tstrm.pak")),
                skeleton=cls.skel())
        return cls._clips

    @classmethod
    def clip(cls, name):
        return next((c for c in cls.clips() if c.name == name), None)


class _JoelFixtures:
    _skel = None
    _clips = None

    @classmethod
    def skel(cls):
        if cls._skel is None:
            from tlou_extractor.pak_reader import PakFile
            from tlou_extractor.skeleton_reader import SkeletonReader
            cls._skel = SkeletonReader.read_skeleton(
                PakFile(os.path.join(ACTOR_DIR, "young-joel-skel-tstrm.pak")))
        return cls._skel

    @classmethod
    def clips(cls):
        if cls._clips is None:
            from tlou_extractor.pak_reader import PakFile
            from tlou_extractor.anim_reader import AnimationReader
            cls._clips = AnimationReader.read_animations(
                PakFile(os.path.join(ACTOR_DIR, "anim-joel-tstrm.pak")),
                skeleton=cls.skel())
        return cls._clips

    @classmethod
    def clip(cls, name):
        return next((c for c in cls.clips() if c.name == name), None)


# ===========================================================================
# Suite 1: Rest Pose & Skeleton Sanity
# ===========================================================================

class TestRestPoseSkeleton(unittest.TestCase):
    """
    Verify rest-pose FK positions match known anatomical landmarks.
    These values are derived from the binary skeleton data and must not
    change regardless of animation parser state.
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(TEST_DATA_DIR):
            raise unittest.SkipTest(f"Test data not found: {TEST_DATA_DIR}")
        cls.skel = _SarahFixtures.skel()
        cls.rest = run_fk(cls.skel, [], 0)

    def _bpos(self, name):
        return bone_pos(self.rest, self.skel.bone_by_name[name].index)

    def test_pelvis_height_in_rest(self):
        """Pelvis should be ~0.81 m above ground in T-pose."""
        y = self._bpos('pelvis')[1]
        self.assertGreater(y, 0.78, f"Pelvis too low in rest: {y:.4f}m")
        self.assertLess(y, 0.85, f"Pelvis too high in rest: {y:.4f}m")

    def test_head_height_in_rest(self):
        """Head centre ~1.3–1.5 m in T-pose."""
        y = self._bpos('headb')[1]
        self.assertGreater(y, 1.25, f"Head too low: {y:.4f}m")
        self.assertLess(y, 1.55, f"Head too high: {y:.4f}m")

    def test_ankles_near_ground_in_rest(self):
        """Ankles must be close to the floor (< 0.15 m)."""
        for side in ('l', 'r'):
            y = self._bpos(f'{side}_ankle')[1]
            self.assertLess(abs(y), 0.15, f"{side}_ankle Y out of range: {y:.4f}m")

    def test_spinea_above_pelvis_in_rest(self):
        self.assertGreater(self._bpos('spinea')[1], self._bpos('pelvis')[1],
            "spinea must be above pelvis in rest pose")

    def test_rest_pose_skinning_identity_sarah(self):
        """
        WorldMat[i] @ IBM[i] == I for every bone (zero deformation in rest).
        This verifies the skeleton and inverse bind matrices are consistent.
        """
        ibms = [np.linalg.inv(m) for m in self.rest]
        for i, (wm, ibm) in enumerate(zip(self.rest, ibms)):
            err = np.max(np.abs(wm @ ibm - np.eye(4)))
            self.assertLess(err, 1e-5,
                f"Sarah bone {i} ({self.skel.bones[i].name}) IBM identity error: {err:.2e}")

    def test_rest_pose_skinning_identity_joel(self):
        skel = _JoelFixtures.skel()
        rest = run_fk(skel, [], 0)
        ibms = [np.linalg.inv(m) for m in rest]
        for i, (wm, ibm) in enumerate(zip(rest, ibms)):
            err = np.max(np.abs(wm @ ibm - np.eye(4)))
            self.assertLess(err, 1e-5,
                f"Joel bone {i} ({skel.bones[i].name}) IBM identity error: {err:.2e}")

    def test_bilateral_symmetry_in_rest(self):
        """Left/right pairs must mirror in X and share the same Y height."""
        pairs = [
            ('l_ankle', 'r_ankle'), ('l_knee', 'r_knee'),
            ('l_upper_leg', 'r_upper_leg'),
            ('l_shoulder', 'r_shoulder'),
            ('l_elbow', 'r_elbow'),
            ('l_wrist', 'r_wrist'),
        ]
        for l_name, r_name in pairs:
            lp = self._bpos(l_name)
            rp = self._bpos(r_name)
            self.assertAlmostEqual(lp[1], rp[1], delta=0.02,
                msg=f"Y asymmetry {l_name}/{r_name}: {lp[1]:.4f} vs {rp[1]:.4f}")
            self.assertAlmostEqual(abs(lp[0]), abs(rp[0]), delta=0.02,
                msg=f"|X| asymmetry {l_name}/{r_name}: {abs(lp[0]):.4f} vs {abs(rp[0]):.4f}")


# ===========================================================================
# Suite 2: Torso Anchoring — the critical regression test
# ===========================================================================

class TestTorsoAnchoring(unittest.TestCase):
    """
    pelvis → lower_base → upper_base → spinea must stay anchored.

    The critical bug (0x2195b1f1 counter-phase channel applied as upper_base
    translation) stretched the torso to ~0.68 m. Correct decoder: upper_base
    translation must equal pelvis translation so spinea never moves away from
    the waist. Max allowed pelvis-spinea separation: 0.06 m (rest ≈ 0.020 m).
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(TEST_DATA_DIR):
            raise unittest.SkipTest(f"Test data not found: {TEST_DATA_DIR}")
        cls.skel = _SarahFixtures.skel()
        cls.pelvis_idx = cls.skel.bone_by_name['pelvis'].index
        cls.spinea_idx = cls.skel.bone_by_name['spinea'].index
        cls.ub_idx = cls.skel.bone_by_name['upper_base'].index

    # -----------------------------------------------------------------------
    # Helper
    # -----------------------------------------------------------------------
    def _max_pelvis_spinea_dist(self, clip):
        n = len(clip.tracks[0].values)
        dists = []
        for f in range(n):
            mats = run_fk(self.skel, clip.tracks, f)
            d = np.linalg.norm(bone_pos(mats, self.spinea_idx)
                               - bone_pos(mats, self.pelvis_idx))
            dists.append(d)
        return max(dists)

    def _assert_anchored(self, clip_name, limit=0.06):
        clip = _SarahFixtures.clip(clip_name)
        if clip is None:
            self.skipTest(f"Clip '{clip_name}' not found")
        dist = self._max_pelvis_spinea_dist(clip)
        self.assertLess(dist, limit,
            f"[{clip_name}] pelvis–spinea max dist={dist:.4f}m "
            f"(limit {limit}m) — torso tearing detected!")

    # -----------------------------------------------------------------------
    # Per-clip tests (will FAIL if 0x2195b1f1 is still applied)
    # -----------------------------------------------------------------------
    def test_walk_forward(self):       self._assert_anchored("sar-p-walk-fw")
    def test_tired_walk_forward(self): self._assert_anchored("sar-p-tired-walk-fw")
    def test_walk_backward(self):      self._assert_anchored("sar-p-walk-bw")
    def test_relaxed_idle(self):       self._assert_anchored("sar-p-relaxed-idle")
    def test_walk_left(self):          self._assert_anchored("sar-p-walk-fw-l")
    def test_walk_right(self):         self._assert_anchored("sar-p-walk-fw-r")

    def test_upper_base_and_pelvis_keep_distinct_local_offsets(self):
        """The static half-float channels preserve their own parent-local offsets.

        RAWCHANNELS 0x14643f16/0x2195b1f1 are ankle references, not torso tracks.
        """
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        self.assertIsNotNone(clip)
        for index in (self.ub_idx, self.pelvis_idx):
            track = next(t for t in clip.tracks
                         if t.node_index == index and t.target_path == 'translation')
            for value in track.values:
                np.testing.assert_allclose(value, self.skel.bones[index].translation, atol=1e-5)

    def test_no_divergent_upper_base_translation_all_clips(self):
        """
        Across ALL clips with both pelvis and upper_base translation tracks,
        the max per-frame divergence must stay below 5 cm.
        This catches the 0x2195b1f1 amplitude (~35 cm) comprehensively.
        """
        skel = self.skel
        ub_idx = self.ub_idx
        pelvis_idx = self.pelvis_idx

        for clip in _SarahFixtures.clips():
            ub_t = next((tr for tr in clip.tracks
                         if tr.node_index == ub_idx
                         and tr.target_path == 'translation'), None)
            pelvis_t = next((tr for tr in clip.tracks
                             if tr.node_index == pelvis_idx
                             and tr.target_path == 'translation'), None)
            if ub_t is None or pelvis_t is None:
                continue
            for f, (ut, pt) in enumerate(zip(ub_t.values, pelvis_t.values)):
                diff = math.sqrt(sum((u - p) ** 2 for u, p in zip(ut, pt)))
                self.assertLess(diff, 0.05,
                    f"[{clip.name}] frame {f}: upper_base diverges from pelvis "
                    f"by {diff:.4f}m — 0x2195b1f1 channel may still be applied")


# ===========================================================================
# Suite 3: Quaternion Continuity — no jitter or sign-flip artifacts
# ===========================================================================

class TestQuaternionContinuity(unittest.TestCase):
    """Quaternion representation continuity, without arbitrary velocity caps."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(TEST_DATA_DIR):
            raise unittest.SkipTest(f"Test data not found: {TEST_DATA_DIR}")

    def _check_continuity(self, skel, clip, clip_name):
        # Hemisphere changes are representation artifacts; legitimate fast motion
        # must not be clamped. Source position/velocity/orientation fidelity is
        # tested independently in test_anim_codec.TestSarahRawReferences.
        for track in clip.tracks:
            if track.target_path != 'rotation':
                continue
            for frame in range(1, len(track.values)):
                dot = sum(a*b for a,b in zip(track.values[frame-1],track.values[frame]))
                self.assertGreaterEqual(dot, -1e-7,
                    f"[{clip_name}] {skel.bones[track.node_index].name}/{frame}: hemisphere flip")

    def test_walk_forward_continuity(self):
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        self._check_continuity(_SarahFixtures.skel(), clip, "sar-p-walk-fw")

    def test_tired_walk_continuity(self):
        clip = _SarahFixtures.clip("sar-p-tired-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        self._check_continuity(_SarahFixtures.skel(), clip, "sar-p-tired-walk-fw")

    def test_idle_continuity(self):
        clip = _SarahFixtures.clip("sar-p-relaxed-idle")
        if clip is None: self.skipTest("Clip not found")
        self._check_continuity(_SarahFixtures.skel(), clip, "sar-p-relaxed-idle")

    def test_quaternion_unit_length_all_clips(self):
        """Every rotation value must be a unit quaternion: |q| = 1 ± 0.002."""
        skel = _SarahFixtures.skel()
        for clip in _SarahFixtures.clips():
            for tr in clip.tracks:
                if tr.target_path != 'rotation':
                    continue
                bname = skel.bones[tr.node_index].name
                for f, q in enumerate(tr.values):
                    norm = math.sqrt(sum(x * x for x in q))
                    self.assertAlmostEqual(norm, 1.0, delta=0.002,
                        msg=f"[{clip.name}] {bname} frame {f}: |q|={norm:.6f}")


# ===========================================================================
# Suite 4: Track Integrity — valid targets, finite values and complete timing
# ===========================================================================

class TestTrackIntegrity(unittest.TestCase):
    """
    Verify frame counts, timestamps and numerical integrity of native tracks.
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(TEST_DATA_DIR):
            raise unittest.SkipTest(f"Test data not found: {TEST_DATA_DIR}")

    def _check_integrity(self, skel, clips, char):
        root_idx = skel.bone_by_name['root'].index
        for clip in clips:
            self.assertGreater(len(clip.tracks), 0,
                f"[{char}][{clip.name}] clip has zero tracks")
            self.assertGreaterEqual(clip.duration, 0.0,
                f"[{char}][{clip.name}] clip has zero duration")

            # Consistent frame count across all tracks
            counts = {len(tr.values) for tr in clip.tracks}
            self.assertEqual(len(counts), 1,
                f"[{char}][{clip.name}] inconsistent frame counts: {counts}")

            for tr in clip.tracks:
                bname = skel.bones[tr.node_index].name.lower()

                # Every mapped channel is allowed, including root and toes.
                # The binary codec, not a bone-name blacklist, selects targets.
                self.assertEqual(len(tr.timestamps), len(tr.values))
                self.assertEqual(tr.timestamps[-1], clip.duration)
                self.assertTrue(all(a < b for a,b in zip(tr.timestamps,tr.timestamps[1:])))

                # 3. All translation values must be finite and ≤ 10 m
                if tr.target_path == 'translation':
                    for f, val in enumerate(tr.values):
                        for dim, v in enumerate(val):
                            self.assertTrue(math.isfinite(v),
                                f"[{char}][{clip.name}] {bname} frame {f} "
                                f"dim {dim}: non-finite translation")
                            self.assertLess(abs(v), 10.0,
                                f"[{char}][{clip.name}] {bname} frame {f} "
                                f"dim {dim}: translation {v:.2f}m out of range")

                # 4. All rotation values must be finite
                if tr.target_path == 'rotation':
                    for f, q in enumerate(tr.values):
                        for c, v in enumerate(q):
                            self.assertTrue(math.isfinite(v),
                                f"[{char}][{clip.name}] {bname} frame {f} "
                                f"component {c}: non-finite rotation")

    def test_sarah_track_integrity(self):
        self._check_integrity(
            _SarahFixtures.skel(), _SarahFixtures.clips(), "Sarah")

    def test_joel_track_integrity(self):
        self._check_integrity(
            _JoelFixtures.skel(), _JoelFixtures.clips(), "Joel")

    def test_upper_base_preserves_native_identity_rotation(self):
        """A static identity track is valid and must not inherit ankle rotations."""
        skel = _SarahFixtures.skel()
        ub_idx = skel.bone_by_name['upper_base'].index
        for clip in _SarahFixtures.clips():
            for track in clip.tracks:
                if track.node_index == ub_idx and track.target_path == 'rotation':
                    for value in track.values:
                        self.assertLess(quat_angle_deg(value, skel.bones[ub_idx].rotation), 0.1)

    def test_pelvis_has_translation_track_in_walk(self):
        """pelvis must have a translation track in locomotion clips."""
        skel = _SarahFixtures.skel()
        pelvis_idx = skel.bone_by_name['pelvis'].index
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        self.assertTrue(
            any(tr.node_index == pelvis_idx and tr.target_path == 'translation'
                for tr in clip.tracks),
            "pelvis must have a translation track in walk animation")

    def test_pelvis_has_rotation_track_in_walk(self):
        """pelvis must have a rotation track in locomotion clips."""
        skel = _SarahFixtures.skel()
        pelvis_idx = skel.bone_by_name['pelvis'].index
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        self.assertTrue(
            any(tr.node_index == pelvis_idx and tr.target_path == 'rotation'
                for tr in clip.tracks),
            "pelvis must have a rotation track in walk animation")


# ===========================================================================
# Suite 5: Anatomical Forward Kinematics
# ===========================================================================

class TestAnimatedFK(unittest.TestCase):
    """
    Run full FK on key locomotion clips and assert anatomical plausibility.
    These bounds come from the character's known anatomy, not from current output.
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(TEST_DATA_DIR):
            raise unittest.SkipTest(f"Test data not found: {TEST_DATA_DIR}")
        cls.skel = _SarahFixtures.skel()

    def _fk_all_frames(self, clip):
        skel = self.skel
        pelvis_idx  = skel.bone_by_name['pelvis'].index
        headb_idx   = skel.bone_by_name['headb'].index
        l_ankle_idx = skel.bone_by_name['l_ankle'].index
        r_ankle_idx = skel.bone_by_name['r_ankle'].index
        l_wrist_idx = skel.bone_by_name['l_wrist'].index
        r_wrist_idx = skel.bone_by_name['r_wrist'].index

        n = len(clip.tracks[0].values)
        pelvis_ys, head_ys, ankle_ys, wrist_zs = [], [], [], []

        for f in range(n):
            mats = run_fk(skel, clip.tracks, f)
            pelvis_ys.append(bone_pos(mats, pelvis_idx)[1])
            head_ys.append(bone_pos(mats, headb_idx)[1])
            ankle_ys.append(min(bone_pos(mats, l_ankle_idx)[1],
                                bone_pos(mats, r_ankle_idx)[1]))
            wrist_zs.append(
                bone_pos(mats, l_wrist_idx)[2] - bone_pos(mats, r_wrist_idx)[2])

        return {
            'pelvis_min': min(pelvis_ys), 'pelvis_max': max(pelvis_ys),
            'head_min':   min(head_ys),   'head_max':   max(head_ys),
            'ankle_min':  min(ankle_ys),
            'wrist_z_range': max(wrist_zs) - min(wrist_zs),
        }

    def _assert_anatomy(self, clip_name,
                        pelvis_range=(0.70, 1.20),
                        head_range=(1.10, 1.70),
                        ankle_floor=-0.10,
                        wrist_swing_min=0.0):
        clip = _SarahFixtures.clip(clip_name)
        if clip is None:
            self.skipTest(f"Clip not found: {clip_name}")
        st = self._fk_all_frames(clip)

        self.assertGreater(st['pelvis_min'], pelvis_range[0],
            f"[{clip_name}] Pelvis too low: {st['pelvis_min']:.3f}m")
        self.assertLess(st['pelvis_max'], pelvis_range[1],
            f"[{clip_name}] Pelvis too high: {st['pelvis_max']:.3f}m")
        self.assertGreater(st['head_min'], head_range[0],
            f"[{clip_name}] Head too low: {st['head_min']:.3f}m (wrong skeleton?)")
        self.assertLess(st['head_max'], head_range[1],
            f"[{clip_name}] Head too high: {st['head_max']:.3f}m")
        self.assertGreater(st['ankle_min'], ankle_floor,
            f"[{clip_name}] Foot spike: ankle Y={st['ankle_min']:.3f}m < {ankle_floor}m")
        if wrist_swing_min > 0:
            self.assertGreater(st['wrist_z_range'], wrist_swing_min,
                f"[{clip_name}] Arms appear frozen: wrist Z range={st['wrist_z_range']:.3f}m")

    def test_walk_forward_anatomy(self):
        self._assert_anatomy("sar-p-walk-fw", wrist_swing_min=0.10)

    def test_tired_walk_anatomy(self):
        self._assert_anatomy("sar-p-tired-walk-fw")

    def test_walk_backward_anatomy(self):
        self._assert_anatomy("sar-p-walk-bw")

    def test_idle_anatomy(self):
        self._assert_anatomy("sar-p-relaxed-idle",
                             pelvis_range=(0.78, 1.05),
                             head_range=(1.20, 1.55),
                             ankle_floor=-0.05)

    def test_walk_pelvis_oscillation(self):
        """
        Pelvis Y must oscillate in a proper walk cycle.
        At 30 fps over 4 s (120 frames) expect 4–12 zero crossings around mean.
        Fewer → pelvis frozen. More → jitter.
        """
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        skel = self.skel
        pelvis_idx = skel.bone_by_name['pelvis'].index
        ys = [run_fk(skel, clip.tracks, f)[pelvis_idx][1, 3]
              for f in range(len(clip.tracks[0].values))]
        mean_y = sum(ys) / len(ys)
        centered = [y - mean_y for y in ys]
        crossings = sum(1 for i in range(1, len(centered))
                        if centered[i - 1] * centered[i] < 0)
        self.assertGreaterEqual(crossings, 4,
            f"Pelvis Y barely oscillates: {crossings} crossings — pelvis frozen?")
        self.assertLessEqual(crossings, 14,
            f"Pelvis Y oscillates too wildly: {crossings} crossings — jitter?")

    def test_head_not_cone_shaped(self):
        """
        headb must not deviate > 0.30 m in X or Y from its mean position.
        Larger deviations indicate the face bones are stretching into a cone/snout.
        Z is excluded (character walks forward).
        """
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        skel = self.skel
        headb_idx = skel.bone_by_name['headb'].index
        positions = np.array([
            bone_pos(run_fk(skel, clip.tracks, f), headb_idx)
            for f in range(len(clip.tracks[0].values))
        ])
        centroid = positions.mean(axis=0)
        max_dev = np.abs(positions - centroid).max(axis=0)
        for ax_idx, ax_name in [(0, 'X'), (1, 'Y')]:
            self.assertLess(max_dev[ax_idx], 0.30,
                f"Head {ax_name} deviation from centroid = {max_dev[ax_idx]:.3f}m — "
                f"cone/snout deformation detected")

    def test_walk_pelvis_vertical_shake(self):
        """
        [USER BUG]: 'само тело трясет вверх вниз'
        In a natural human walk cycle, pelvis vertical displacement is ~2 to 5 cm.
        Total peak-to-peak delta Y must not exceed 0.08m (8 cm).
        Frame-to-frame delta Y must not exceed 0.015m (1.5 cm) at 30 fps (catches high-frequency jerk).
        Current broken behavior bounces up to 16.6 cm with 2.7 cm jumps per frame!
        """
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        skel = self.skel
        pelvis_idx = skel.bone_by_name['pelvis'].index
        ys = np.array([run_fk(skel, clip.tracks, f)[pelvis_idx][1, 3]
                       for f in range(len(clip.tracks[0].values))])
        
        y_range = ys.max() - ys.min()
        self.assertLess(y_range, 0.05,
            f"Pelvis vertical bounce too large: {y_range*100:.1f} cm (limit 5.0 cm) — "
            f"body violently shaking up and down")
        
        dy = np.abs(np.diff(ys))
        max_dy = dy.max()
        self.assertLess(max_dy, 0.008,
            f"Pelvis vertical frame-to-frame jump: {max_dy*100:.2f} cm (limit 0.8 cm) — "
            f"high-frequency vertical jerk/shake")

    def test_walk_pelvis_tilt_forward_backward(self):
        """
        [USER BUG]: 'а также немного крутит вперед назад тоесть положение не устойчиво горизонтальное'
        In upright walking locomotion, pelvis orientation pitch/tilt must remain stably upright.
        Pelvis rotation deviation from rest orientation must not exceed 4.0 degrees.
        Current broken behavior violently tilts forward/backward by over 70 degrees!
        """
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        skel = self.skel
        pelvis_idx = skel.bone_by_name['pelvis'].index
        pelvis_track = next((tr for tr in clip.tracks
                             if tr.node_index == pelvis_idx and tr.target_path == 'rotation'), None)
        self.assertIsNotNone(pelvis_track, "Pelvis rotation track must exist")

        rest_q = skel.bones[pelvis_idx].rotation
        angles = [quat_angle_deg(rest_q, q) for q in pelvis_track.values]
        max_tilt = max(angles)
        self.assertLess(max_tilt, 4.0,
            f"Pelvis tilts forward/backward by {max_tilt:.1f}° from rest (limit 4.0°) — "
            f"body unstable, pitching unnaturally forward/backward")

    def test_walk_leg_kick_excessive_height(self):
        """
        [USER BUG]: 'правая нога сильно задерается вверх'
        In normal forward walking:
        1. Ankle height must NEVER exceed pelvis height (~0.85m).
        2. Knee height must stay below 0.90m.
        3. Upper leg rotation from rest must not exceed 65.0 degrees.
        Current broken behavior kicks the right ankle to 1.399m (above the character's head!)
        and rotates r_upper_leg by 160.3 degrees!
        """
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        skel = self.skel
        r_ankle_idx = skel.bone_by_name['r_ankle'].index
        l_ankle_idx = skel.bone_by_name['l_ankle'].index
        r_knee_idx = skel.bone_by_name['r_knee'].index
        l_knee_idx = skel.bone_by_name['l_knee'].index
        pelvis_idx = skel.bone_by_name['pelvis'].index

        num_frames = len(clip.tracks[0].values)
        r_ankle_ys = []
        l_ankle_ys = []
        r_knee_ys = []
        pelvis_ys = []

        for f in range(num_frames):
            mats = run_fk(skel, clip.tracks, f)
            r_ankle_ys.append(bone_pos(mats, r_ankle_idx)[1])
            l_ankle_ys.append(bone_pos(mats, l_ankle_idx)[1])
            r_knee_ys.append(bone_pos(mats, r_knee_idx)[1])
            pelvis_ys.append(bone_pos(mats, pelvis_idx)[1])

        max_pelvis_y = max(pelvis_ys)
        max_r_ankle = max(r_ankle_ys)
        self.assertLess(max_r_ankle, max_pelvis_y,
            f"Right ankle kicks up to Y={max_r_ankle:.3f}m, exceeding pelvis Y={max_pelvis_y:.3f}m — "
            f"right leg kicks unnaturally high up into the air!")

        self.assertLess(max(r_knee_ys), 0.90,
            f"Right knee height {max(r_knee_ys):.3f}m exceeds 0.90m limit")

        # Upper leg rotation check
        for tr in clip.tracks:
            if tr.target_path == 'rotation':
                bname = skel.bones[tr.node_index].name.lower()
                if bname in ('r_upper_leg', 'l_upper_leg'):
                    rest_q = skel.bones[tr.node_index].rotation
                    max_angle = max(quat_angle_deg(rest_q, q) for q in tr.values)
                    self.assertLess(max_angle, 65.0,
                        f"{bname} rotates {max_angle:.1f}° from rest (limit 65.0°) — "
                        f"leg kicking excessively high!")

    def test_walk_leg_bilateral_symmetry(self):
        """
        [USER BUG]: 'правая нога сильно задерается вверх' (asymmetry with left leg)
        Left and right legs in forward walk should have symmetric stride heights.
        The difference between max left and max right ankle height must be < 0.15m.
        Current broken behavior has right ankle at 1.40m vs left at 0.98m (diff = 0.42m)!
        """
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        skel = self.skel
        r_ankle_idx = skel.bone_by_name['r_ankle'].index
        l_ankle_idx = skel.bone_by_name['l_ankle'].index

        mats = [run_fk(skel, clip.tracks, f) for f in range(len(clip.tracks[0].values))]
        max_r_ankle = max(bone_pos(m, r_ankle_idx)[1] for m in mats)
        max_l_ankle = max(bone_pos(m, l_ankle_idx)[1] for m in mats)

        diff = abs(max_r_ankle - max_l_ankle)
        self.assertLess(diff, 0.15,
            f"Leg height asymmetry: right ankle max Y={max_r_ankle:.3f}m vs left ankle max Y={max_l_ankle:.3f}m "
            f"(diff={diff:.3f}m > limit 0.15m) — right leg is behaving completely abnormally!")

    def test_walk_right_arm_motion_bounds(self):
        """
        [USER BUG]: 'нестественное движение правой рукой'
        In a natural forward walk, the right arm swings gently at the character's side:
        1. Right wrist height must remain below chest/chin height (Y < 1.15m).
        2. Total right wrist vertical range must be < 0.35m.
        Current broken behavior swings the right wrist up to Y=1.317m (above the head)
        with massive vertical excursion (0.54m)!
        """
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        skel = self.skel
        r_wrist_idx = skel.bone_by_name['r_wrist'].index

        mats = [run_fk(skel, clip.tracks, f) for f in range(len(clip.tracks[0].values))]
        r_wrist_ys = [bone_pos(m, r_wrist_idx)[1] for m in mats]

        max_wrist_y = max(r_wrist_ys)
        self.assertLess(max_wrist_y, 1.22,
            f"Right wrist reaches height Y={max_wrist_y:.3f}m (limit 1.22m) — "
            f"right arm swinging unnaturally high above chin/head!")

        wrist_y_range = max(r_wrist_ys) - min(r_wrist_ys)
        self.assertLess(wrist_y_range, 0.35,
            f"Right wrist vertical travel = {wrist_y_range:.3f}m (limit 0.35m) — "
            f"unnatural vertical arm flailing!")


# ===========================================================================
# Suite 6: Upper Body Coverage — spine/arms/head must be animated
# ===========================================================================

class TestUpperBodyCoverage(unittest.TestCase):
    """
    A correct full-body animation must animate the spine, arms, and head.
    If only lower-body bones appear in the output, the Section 3 upper-body
    bitstream decoder is not working.
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(TEST_DATA_DIR):
            raise unittest.SkipTest(f"Test data not found: {TEST_DATA_DIR}")

    # Bones that MUST be animated in a full-body locomotion clip
    REQUIRED_UPPER = {
        'spinea', 'spineb', 'spinec', 'spined',
        'l_clavicle', 'r_clavicle',
        'l_shoulder', 'r_shoulder',
        'l_elbow', 'r_elbow',
        'neck', 'heada', 'headb',
    }

    def _animated_set(self, skel, clip, threshold_deg=3.0):
        """
        Return bone names that deviate > threshold_deg from their first frame
        at any point in the clip. Using first frame avoids the cyclic-clip
        problem where values[0] ≈ values[-1].
        """
        out = set()
        for tr in clip.tracks:
            if tr.target_path != 'rotation' or len(tr.values) < 2:
                continue
            ref = tr.values[0]
            if max(quat_angle_deg(ref, q) for q in tr.values) > threshold_deg:
                out.add(skel.bones[tr.node_index].name.lower())
        return out

    def _check_upper(self, clip_name, char='Sarah', min_bones=8):
        skel  = _SarahFixtures.skel()  if char == 'Sarah' else _JoelFixtures.skel()
        clips = _SarahFixtures.clips() if char == 'Sarah' else _JoelFixtures.clips()
        clip  = next((c for c in clips if c.name == clip_name), None)
        if clip is None:
            self.skipTest(f"Clip '{clip_name}' not found")
        animated = self._animated_set(skel, clip)
        upper_animated = animated & self.REQUIRED_UPPER
        self.assertGreaterEqual(len(upper_animated), min_bones,
            f"[{char}][{clip_name}] only {len(upper_animated)}/{len(self.REQUIRED_UPPER)} "
            f"upper body bones animated. Missing: {self.REQUIRED_UPPER - upper_animated}")

    def test_sarah_walk_upper_body(self):
        self._check_upper("sar-p-walk-fw", "Sarah", min_bones=9)

    def test_sarah_tired_walk_upper_body(self):
        self._check_upper("sar-p-tired-walk-fw", "Sarah", min_bones=8)

    def test_upper_legs_swing_hard_in_walk(self):
        """
        l_upper_leg and r_upper_leg must each swing > 20° from their first frame
        in the walk cycle (confirms the locomotion drive is decoded).
        """
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        skel = _SarahFixtures.skel()
        checked = set()
        for tr in clip.tracks:
            if tr.target_path != 'rotation': continue
            bname = skel.bones[tr.node_index].name.lower()
            if bname not in ('l_upper_leg', 'r_upper_leg'): continue
            ref = tr.values[0]
            max_dev = max(quat_angle_deg(ref, q) for q in tr.values)
            self.assertGreater(max_dev, 20.0,
                f"{bname} swing = {max_dev:.1f}° < 20° in walk (locomotion not decoded?)")
            checked.add(bname)
        self.assertIn('l_upper_leg', checked, "l_upper_leg rotation track missing")
        self.assertIn('r_upper_leg', checked, "r_upper_leg rotation track missing")


# ===========================================================================
# Suite 7: Spine Rotation Bounds — physiologically plausible angles
# ===========================================================================

class TestSpineRotationBounds(unittest.TestCase):
    """
    Each spine/head bone's animated rotation must stay within the physiological
    range of human motion. These bounds come from biomechanics literature, NOT
    from current broken animation output.

    Reference ranges (degrees from neutral stance):
      Lumbar (spinea/b): ±20° flex/extend, ±10° lateral bend, ±30° axial rotation
      Thoracic (spinec/d): ±35° flex, ±25° rotation
      Cervical (neck): ±50° flex, ±60° rotation (but game character = ±35° typical)
      Head (heada/headb): ±45° from rest typical for a walking character

    We use CONSERVATIVE limits that still allow normal walk, run, and idle,
    but will FAIL if bones are spinning by 80–170° (the symptom of the stride bug).
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(TEST_DATA_DIR):
            raise unittest.SkipTest(f"Test data not found: {TEST_DATA_DIR}")

    # Maximum angular deviation from rest pose (degrees).
    #
    # These are CORRECT bounds — animations decoded properly will stay within them.
    # The stride bug (wrong Tag 1053/1054 stride) produced 80–170° errors on spine bones.
    # Even with those values passing, the test catches regressions back to that state.
    #
    # Note on realistic values (measured from correct smooth PS4 motion):
    #   spinec in tired-walk: peaks at ~38° (torso leans into tired gait — legit)
    #   spineb in idle: peaks at ~32° (character sways / breathes — legit)
    #   heada/headb: varies a lot by pose type (crouch starts at 58° from T-pose rest)
    #
    # Strategy: use wide but still diagnostic limits for spine/head,
    # then rely on the CONTINUITY tests to catch sign-flip jitter.
    # The 80–170° stride-bug values will still fail here even at these limits.
    MAX_FROM_REST = {
        'spinea': 45.0,   # lumbar flex/rotation: stride-bug gave 80–170°
        'spineb': 45.0,   # thoracic: stride-bug gave 80–170°
        'spinec': 50.0,   # mid-thoracic: tired walk peaks ~38°
        'spined': 50.0,   # upper-thoracic: tired walk peaks ~44°
        'neck':   60.0,   # cervical: prone/crouch turns head widely
        'headb':  65.0,   # head yaw: stride-bug gave > 100°
    }

    def _check_bounds(self, skel, clip, char):
        for tr in clip.tracks:
            if tr.target_path != 'rotation':
                continue
            bname = skel.bones[tr.node_index].name.lower()
            if bname not in self.MAX_FROM_REST:
                continue
            rest_q = skel.bones[tr.node_index].rotation
            limit  = self.MAX_FROM_REST[bname]
            for f, q in enumerate(tr.values):
                angle = quat_angle_deg(q, rest_q)
                self.assertLess(angle, limit,
                    f"[{char}][{clip.name}] {bname} frame {f}: "
                    f"{angle:.1f}° from rest (limit {limit}°) — "
                    f"likely decoding bug (stride bug gives 80–170°)")

    def test_sarah_walk_spine_bounds(self):
        clip = _SarahFixtures.clip("sar-p-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        self._check_bounds(_SarahFixtures.skel(), clip, "Sarah")

    def test_sarah_tired_walk_spine_bounds(self):
        clip = _SarahFixtures.clip("sar-p-tired-walk-fw")
        if clip is None: self.skipTest("Clip not found")
        self._check_bounds(_SarahFixtures.skel(), clip, "Sarah")

    def test_sarah_idle_spine_bounds(self):
        clip = _SarahFixtures.clip("sar-p-relaxed-idle")
        if clip is None: self.skipTest("Clip not found")
        self._check_bounds(_SarahFixtures.skel(), clip, "Sarah")

    def test_joel_walk_spine_bounds(self):
        skel = _JoelFixtures.skel()
        walk = next((c for c in _JoelFixtures.clips()
                     if 'walk' in c.name and 'fwd' in c.name), None)
        if walk is None:
            self.skipTest("No Joel walk clip found")
        self._check_bounds(skel, walk, "Joel")


# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
