"""Independent wire samples and original camera/actor alignment checks."""
import math
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest

import numpy as np

from tlou_extractor.anim_codec import AnimationDecodeError
from tlou_extractor.animation_placement import placement_motion
from tlou_extractor.cinematic_camera import (
    ALIGN_CHANNEL, CAMERA_CHANNEL, channel_curve, extract_camera,
    read_transform_curve, horizontal_fov, vertical_fov, DOF_CHANNEL,
)
from tlou_extractor.door_interaction_data import animation_entry, compose_rigid
from tlou_extractor.pak_reader import PakFile


def wire_curve(flags, first, following, frames=2):
    data = struct.pack('<HHIQ', frames, flags, 0, 16) + first + following
    return SimpleNamespace(data=data, pointer_page_ids={8}, read_ptr=lambda _: 16)


class TransformPacking(unittest.TestCase):
    def test_half_float_scale_y_is_constant(self):
        first = struct.pack('<10e', 0, 0, 0, 1, 2, 3, 4, 35, 0, 1)
        following = struct.pack('<9e', 0, 1, 0, 0, 5, 6, 7, 40, 2)
        curve = read_transform_curve(wire_curve(0x40, first, following), 0)
        self.assertEqual(curve['sample_stride'], 18)
        self.assertEqual(curve['samples'][1]['position'], [5, 6, 7])
        self.assertEqual(curve['samples'][1]['rotation_xyzw'], [0, 1, 0, 0])
        self.assertEqual(curve['samples'][1]['scale'], [40, 0, 2])

    def test_float_constant_quaternion_and_translation_y(self):
        first = struct.pack('<10f', 0, 0, 0, 1, 2, 3, 4, 1, 1, 1)
        following = struct.pack('<2f', 5, 7)
        curve = read_transform_curve(wire_curve(0x1fa, first, following), 0)
        self.assertEqual(curve['sample_stride'], 8)
        self.assertEqual(curve['samples'][1]['position'], [5, 3, 7])
        self.assertEqual(curve['samples'][1]['rotation_xyzw'], [0, 0, 0, 1])

    def test_half_float_quaternion_with_bit_two_set(self):
        # 00e2 is all half-float, despite bit 0x2. Precision is bit 0x100.
        first = struct.pack('<10e', 0, 0, 0, 1, 2, 3, 4, 1, 1, 1)
        following = struct.pack('<7e', 0, 1, 0, 0, 5, 6, 7)
        curve = read_transform_curve(wire_curve(0xe2, first, following), 0)
        self.assertEqual(curve['sample_stride'], 14)
        self.assertEqual(curve['samples'][1]['rotation_xyzw'], [0, 1, 0, 0])
        self.assertEqual(curve['samples'][1]['position'], [5, 6, 7])

    def test_truncated_samples_and_unsupported_packing_are_refused(self):
        first = struct.pack('<10e', 0, 0, 0, 1, 2, 3, 4, 35, 0, 1)
        for flags in (0x40, 0x41, 0x240):
            with self.subTest(flags=flags), self.assertRaises(AnimationDecodeError):
                read_transform_curve(wire_curve(flags, first, b''), 0)

    def test_missing_channel_is_not_a_fabricated_camera(self):
        pak = SimpleNamespace(pointer_page_ids=set())
        self.assertIsNone(channel_curve(pak, SimpleNamespace(abs_offset=0), CAMERA_CHANNEL))


class NativeLensMath(unittest.TestCase):
    def test_focal_length_and_film_gate_not_degrees(self):
        self.assertAlmostEqual(horizontal_fov([50, 0, 1]), 39.597752709, places=7)
        self.assertAlmostEqual(horizontal_fov([23.458, 0, 0]), 75, places=2)
        self.assertAlmostEqual(horizontal_fov([50, 1, 0]), 75)
        self.assertAlmostEqual(horizontal_fov([0, 0, 0]), horizontal_fov([23.458, 0, 0]))
        self.assertAlmostEqual(horizontal_fov([50, .5, 1]), (39.597752709+75)/2)

    def test_horizontal_projection_matches_native_film_width(self):
        angle = horizontal_fov([50, 0, 1])
        vertical = vertical_fov(angle, 960/544)
        # glm/Three vertical projection must produce horizontal extent 36/(2*50).
        self.assertAlmostEqual(math.tan(math.radians(vertical)/2) * (960/544), .36)
        with self.assertRaises(ValueError): vertical_fov(angle, 0)


class OriginalCameras(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actor = Path(os.environ.get('TLOU_TEST_DATA', 'D:/TLOUPS4/Extracted')) / 'actor50'
        if not cls.actor.exists():
            raise unittest.SkipTest('Original PS4 camera assets are not installed')

    def test_bedroom_lens_and_depth_planes(self):
        pak = PakFile(str(self.actor/'hom1-tstrm.pak'))
        item = next(i for i in pak.get_items('ANIM') if i.name == 'hom1-house-sarah-bedroom-phone--sarah')
        locator = {'position':[0,0,0], 'rotation_xyzw':[0,0,0,1]}
        camera = extract_camera(pak,item,locator,30,912)
        lens = camera['lens']
        self.assertEqual(len(lens['samples']),912)
        self.assertAlmostEqual(lens['samples'][0][1],50)
        self.assertAlmostEqual(lens['samples'][0][0],39.597752709,places=6)
        self.assertEqual(lens['depth_of_field']['channel_id'],f'0x{DOF_CHANNEL:08x}')
        np.testing.assert_allclose(lens['depth_of_field']['samples'][0],
            [4,0,3.039513588,5.84795332,23.462293625,1],atol=1e-5)
        cuts = [i for i in range(1,912) if abs(lens['samples'][i][3]-lens['samples'][i-1][3])>.5]
        self.assertEqual(cuts,[757])

    def test_camera_tracks_and_alignment_match_native_actor_motion(self):
        locator = {'position': [-1.8, 28.4, -37], 'rotation_xyzw': [0, 0, 0, 1]}
        clips = [
            ('hom1-house-study', 'hom1-house-study--joel', 899, '0x01e2'),
            ('hom1-house-study', 'hom1-house-study-backup--joel', 157, '0x0060'),
            ('hom1-house-study-and-escape', 'hom1-house-study-and-escape-04-sick--joel', 334, '0x00e2'),
            ('hom1-house-study-and-escape', 'hom1-house-study-and-escape-05-inf-reveal--joel', 129, '0x0040'),
            ('hom1-house-study-and-escape', 'hom1-house-study-and-escape-outro--joel', 1523, '0x0040'),
        ]
        for bank_name, name, count, flags in clips:
            with self.subTest(clip=name):
                pak = PakFile(str(self.actor / (bank_name + '-tstrm.pak')))
                item = next(i for i in pak.get_items('ANIM') if i.name == name)
                camera = extract_camera(pak, item, locator, 30, count)
                self.assertEqual(len(camera['samples']), count)
                self.assertEqual(camera['camera_curve']['flags'], flags)
                self.assertAlmostEqual(camera['duration'], (count - 1) / 30)
                if 'backup' in name:
                    sarah = next(i for i in pak.get_items('ANIM') if i.name == name.replace('--joel', '--sarah'))
                    other = extract_camera(pak, sarah, locator, 30, count)
                    np.testing.assert_allclose(
                        np.array(camera['samples'])[:, :3],
                        np.array(other['samples'])[:, :3], atol=.004,
                    )
                for sample in camera['samples']:
                    self.assertTrue(all(math.isfinite(x) for x in sample))
                    self.assertAlmostEqual(math.hypot(*sample[3:]), 1, places=5)
                # Independently decoded apReference motion must equal entry*align.
                entry = compose_rigid(locator, animation_entry(pak, item)['relative_to_shared_locator'])
                align = channel_curve(pak, item, ALIGN_CHANNEL)
                motion = placement_motion(pak, item, locator, 30, count)
                for frame in [0, min(100, count - 1), count - 1]:
                    expected = compose_rigid(entry, align['samples'][frame])
                    np.testing.assert_allclose(expected['position'], motion['samples'][frame][:3], atol=2e-5)
                    # Quaternions q/-q represent the same rotation.
                    dot = np.dot(expected['rotation_xyzw'], motion['samples'][frame][3:])
                    self.assertAlmostEqual(abs(dot), 1, places=5)
                with self.assertRaises(AnimationDecodeError):
                    extract_camera(pak, item, locator, 30, count - 1)


if __name__ == '__main__':
    unittest.main()
