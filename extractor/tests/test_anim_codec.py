"""Codec invariants and independent PS4 raw-ankle reference comparisons."""
import math
import os
from pathlib import Path
import struct
import unittest

import numpy as np

from tlou_extractor.anim_codec import (
    AnimationDecodeError, commands, decode_primary, quaternion48,
    quaternion_exp, unpack_vector64,
)
from tlou_extractor.anim_reader import AnimationReader, q_mul
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.skeleton_reader import SkeletonReader
from tests.test_animations import run_fk, quat_angle_deg


def vector64(values, signed):
    bits = 0
    shift = 0
    for value, width in zip(reversed(values), (21,21,22)):
        raw = struct.unpack('<I', struct.pack('<f', value))[0]
        bits |= (raw >> ((32 if signed else 31)-width)) << shift
        shift += width
    return bits.to_bytes(8, 'little')


def synthetic_section():
    """Two quantized log vectors; second X predicts the first vector's Y."""
    section = bytearray(256)
    struct.pack_into('<4H', section, 0, 1547, 0x8002, 3, 96)
    struct.pack_into('<3H', section, 8, 0, 0, 1)
    struct.pack_into('<5H', section, 14, 1051, 0x8002, 3, 112, 0)
    struct.pack_into('<5H', section, 24, 1054, 2, 3, 160, 0)
    struct.pack_into('<5H', section, 34, 1040, 2, 3, 192, 0)
    section[96:98] = bytes([3,3])
    for i in range(2):
        section[112+i*16:120+i*16] = vector64((0.125,0.25,0.5), False)
        section[120+i*16:128+i*16] = vector64((0,0,0), True)
    section[144:152] = bytes([1,1,2,1, 0x81,1,2,1])
    for i in range(2):
        struct.pack_into('<8h', section, 160+16*i, 0,0,0,0,0,0,32767,32767)
    struct.pack_into('<2H', section, 192, 16, 64)
    return section


class TestPredictiveCodec(unittest.TestCase):
    def test_quantization_ranges(self):
        # A fixed wire example, distinct from the synthetic packer.
        wire = bytes.fromhex('bc97eecad0b1c3740db19723fd7846bd')
        self.assertAlmostEqual(unpack_vector64(wire,0,False)[1],0.000585019588470459)
        self.assertAlmostEqual(unpack_vector64(wire,8,True)[1],0.78466796875)

    def test_command_lengths_are_not_scanned_for_tag_patterns(self):
        section=synthetic_section()
        self.assertEqual([c.opcode for c in commands(section)], [1547,1051,1054,1040])

    def test_predictor_selects_previous_component_and_keeps_endpoints(self):
        # First frame: vectors 010,100. Second: 000,000. No cyclic filtering.
        result, unknown = decode_primary(synthetic_section(), bytes([0b01010000,0]),1,2,2)
        self.assertFalse(unknown)
        expected = quaternion_exp((0.375,0,0))  # .125 residual + predecessor Y=.25
        np.testing.assert_allclose(result[(1,'rotation')][0],expected,atol=1e-12)
        np.testing.assert_allclose(result[(1,'rotation')][1],(0,0,0,1),atol=1e-12)

    def test_log_quaternion_is_exponential_not_drop_w(self):
        np.testing.assert_allclose(quaternion_exp((math.pi/2,0,0)),(1,0,0,0),atol=1e-12)
        self.assertEqual(quaternion_exp((0,0,0)),(0,0,0,1))

    def test_static_quaternion_identity_and_y_half_turn(self):
        self.assertEqual(quaternion48(bytes.fromhex('030001800080'),0),(0,0,0,1))
        self.assertEqual(quaternion48(bytes.fromhex('010001800080'),0),(0,1,0,0))

    def test_truncated_frame_rejected(self):
        with self.assertRaises(AnimationDecodeError):
            decode_primary(synthetic_section(), b'\0',1,2,2)

    def test_width_overflow_rejected(self):
        section=synthetic_section();section[96]=9
        with self.assertRaises(AnimationDecodeError):
            decode_primary(section,b'\0',1,1,2)

    def test_first_curve_cannot_predict_missing_predecessor(self):
        section=synthetic_section();section[144]=0x41
        with self.assertRaises(AnimationDecodeError):
            decode_primary(section,b'\0',1,1,2)

    def test_single_frame_is_retained(self):
        result,_=decode_primary(synthetic_section(),b'\0',1,1,2)
        self.assertEqual(len(result[(0,'rotation')]),1)

    def test_1053_quaternions_are_interleaved_in_pairs(self):
        section=synthetic_section()
        struct.pack_into('<H',section,24,1053)
        struct.pack_into('<8h',section,160,0,32767,0,0,0,0,32767,0)
        result,_=decode_primary(section,b'\0',1,1,2)
        self.assertEqual(result[(0,'rotation')][0],(0,0,0,1))
        self.assertEqual(result[(1,'rotation')][0],(1,0,0,0))

    def test_unknown_rotation_codec_is_reported_not_guessed(self):
        section=synthetic_section();struct.pack_into('<H',section,24,1055)
        result,unknown=decode_primary(section,b'\0',1,1,2)
        self.assertEqual(unknown,{1055})
        self.assertEqual(result,{})

    def test_export_constants_keep_duration_and_coverage(self):
        from tlou_extractor.anim_reader import AnimationClip, AnimationTrack
        from tlou_extractor.gltf_writer import GLTFWriter
        clip=AnimationClip('constant',2,1)
        clip.has_secondary_stream=True
        track=AnimationTrack(0,'translation')
        track.timestamps=[0,1,2];track.values=[[1,2,3]]*3;clip.tracks=[track]
        writer=GLTFWriter('constant');writer.add_animation(clip,[0])
        self.assertEqual(writer.accessors[0]['count'],2)
        self.assertEqual(writer.accessors[0]['max'],[2])
        self.assertFalse(writer.animations[0]['extras']['decoding']['secondaryStreamDecoded'])

    def test_export_rejects_mismatched_samples(self):
        from tlou_extractor.anim_reader import AnimationClip, AnimationTrack
        from tlou_extractor.gltf_writer import GLTFWriter
        clip=AnimationClip('bad');track=AnimationTrack(0)
        track.timestamps=[0,1];track.values=[[0,0,0,1]];clip.tracks=[track]
        with self.assertRaises(ValueError): GLTFWriter('bad').add_animation(clip,[0])

    def test_viewer_interpolates_z_using_z(self):
        # Check both the generator and delivered viewer to prevent regeneration regressions.
        root=Path(__file__).resolve().parents[1]
        for name in ('build_viewer.py','viewer.html'):
            text=(root/name).read_text(encoding='utf-8')
            line=next(line for line in text.splitlines() if 'targetTRS.t[2] = vals' in line)
            self.assertIn('vals[k1 * 3 + 2]',line)
            self.assertNotIn('vals[k1 * 3 + 1]',line)


class TestSarahRawReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=os.environ.get('TLOU_TEST_DATA',r'D:\TLOUPS4\Extracted')
        actor=Path(root)/'actor50'
        if not (actor/'anim-sarah-player-tstrm.pak').exists():
            raise unittest.SkipTest('PS4 reference assets not installed')
        cls.pak=PakFile(str(actor/'anim-sarah-player-tstrm.pak'))
        cls.skel=SkeletonReader.read_skeleton(PakFile(str(actor/'sarah-skel-tstrm.pak')))

    def compare(self,name):
        pak=self.pak
        item=next(a for a in pak.get_items('ANIM') if a.name==name)
        clip=AnimationReader._parse_clip(pak,item,self.skel)
        self.assertFalse(clip.unsupported_opcodes)
        count=len(clip.tracks[0].values)
        self.assertAlmostEqual(clip.duration,(count-1)/clip.fps)
        self.assertTrue(all(tr.timestamps[-1]==clip.duration for tr in clip.tracks))
        extra=pak.read_ptr(item.abs_offset+0x30)
        hashes=pak.read_ptr(extra+8); pointers=pak.read_ptr(extra+16)
        channels=struct.unpack_from('<I',pak.data,extra)[0]
        matrices=[run_fk(self.skel,clip.tracks,f) for f in range(count)]
        rotation_tracks={t.node_index:t.values for t in clip.tracks if t.target_path=='rotation'}
        checked=0
        for channel in range(channels):
            h=struct.unpack_from('<I',pak.data,hashes+channel*4)[0]
            bone_name={0x14643f16:'l_ankle',0x2195b1f1:'r_ankle'}.get(h)
            if not bone_name:
                continue
            ptr=pak.read_ptr(pointers+channel*8)
            self.assertEqual(struct.unpack_from('<2H',pak.data,ptr),(count,0x1e2))
            expected=np.array([struct.unpack_from('<7f',pak.data,ptr+16 if f==0 else ptr+56+(f-1)*28)
                               for f in range(count)])
            index=self.skel.bone_by_name[bone_name].index
            actual=np.array([m[index][:3,3] for m in matrices])
            errors=np.linalg.norm(actual-expected[:,4:],axis=1)
            self.assertLess(float(errors.max()),0.002,f'{name}/{bone_name}: source-position error')
            # Match velocities as well: smoothing can pass broad anatomical bounds but fails this.
            velocity_error=np.linalg.norm(np.diff(actual,axis=0)-np.diff(expected[:,4:],axis=0),axis=1)
            self.assertLess(float(velocity_error.max()),0.003,f'{name}/{bone_name}: source-velocity error')
            chain=[];current=index
            while current>=0:
                chain.append(current);current=self.skel.bones[current].parent_index
            for f in range(count):
                q=(0,0,0,1)
                for bone in reversed(chain):
                    q=q_mul(q,rotation_tracks[bone][f] if bone in rotation_tracks else self.skel.bones[bone].rotation)
                self.assertLess(quat_angle_deg(q,expected[f,:4]),0.25,
                                f'{name}/{bone_name}/{f}: source-orientation error')
            checked+=1
        self.assertEqual(checked,2,'Both independent raw foot references must be present')

    def test_forward_walk(self): self.compare('sar-p-walk-fw')
    def test_tired_forward_walk(self): self.compare('sar-p-tired-walk-fw')
    def test_backward_walk(self): self.compare('sar-p-walk-bw')

    def test_static_heel_matches_native_rest_orientation(self):
        # Walk's right heel is stored in quaternion48, whereas tired-walk uses
        # the independent log-quaternion codec and starts near the rest pose.
        for name in ['sar-p-walk-fw', 'sar-p-tired-walk-fw']:
            item = next(a for a in self.pak.get_items('ANIM') if a.name == name)
            clip = AnimationReader._parse_clip(self.pak, item, self.skel)
            for bone_name in ['l_heel', 'r_heel']:
                bone = self.skel.bone_by_name[bone_name]
                track = next(t for t in clip.tracks if t.node_index == bone.index and t.target_path == 'rotation')
                samples = track.values if name == 'sar-p-walk-fw' else track.values[:1]
                for q in samples:
                    self.assertLess(quat_angle_deg(q, bone.rotation), 0.03, f'{name}/{bone_name}')


class TestInfectedSkeletonBinding(unittest.TestCase):
    def test_upper_body_matches_source_rig_after_binding(self):
        root = Path(os.environ.get('TLOU_TEST_DATA', r'D:\TLOUPS4\Extracted')) / 'actor50'
        banks = {'runner': 'runr-idle-stnd-sleep',
                 'infected-hom': 'inf-hom-sprint-01',
                 'clicker': 'idle-awr^move-lt^run--fw',
                 'inf-shared': 'canvas-fire-idle'}
        required = ['infected-skel-tstrm.pak', 'infected-fem-skel-tstrm.pak']
        required += [f'anim-{name}-tstrm.pak' for name in banks]
        if not all((root / name).exists() for name in required):
            self.skipTest('PS4 reference assets not installed')
        source = SkeletonReader.read_skeleton(PakFile(str(root / required[0])))
        target = SkeletonReader.read_skeleton(PakFile(str(root / required[1])))
        self.assertNotEqual(source.bone_by_name['neck'].index, target.bone_by_name['neck'].index)
        names = ['neck', 'heada', 'headb', 'l_clavicle', 'r_clavicle',
                 'l_shoulder', 'r_shoulder', 'l_elbow', 'r_elbow', 'l_wrist', 'r_wrist']
        for bank, name in banks.items():
            with self.subTest(bank=bank, clip=name):
                pak = PakFile(str(root / f'anim-{bank}-tstrm.pak'))
                item = next(i for i in pak.get_items('ANIM') if i.name == name)
                clip = AnimationReader._parse_clip(pak, item, source)
                count = len(clip.tracks[0].values)
                expected = [run_fk(source, clip.tracks, f) for f in range(count)]
                AnimationReader.remap_tracks(clip, source, target)
                self.assertEqual(len({(t.node_index, t.target_path) for t in clip.tracks}), len(clip.tracks))
                for frame in range(count):
                    actual = run_fk(target, clip.tracks, frame)
                    for joint in names:
                        np.testing.assert_allclose(actual[target.bone_by_name[joint].index],
                                                   expected[frame][source.bone_by_name[joint].index],
                                                   atol=1e-7, rtol=0, err_msg=f'{name}/{joint}/{frame}')


class TestOtherCharacterRawReferences(unittest.TestCase):
    compare = TestSarahRawReferences.compare

    def check_character(self, actor, animation, names):
        root = Path(os.environ.get('TLOU_TEST_DATA', r'D:\TLOUPS4\Extracted')) / 'actor50'
        animation_path = root / f'anim-{animation}-tstrm.pak'
        skeleton_path = root / f'{actor}-skel-tstrm.pak'
        if not animation_path.exists() or not skeleton_path.exists():
            self.skipTest('PS4 reference assets not installed')
        self.pak = PakFile(str(animation_path))
        self.skel = SkeletonReader.read_skeleton(PakFile(str(skeleton_path)))
        for name in names:
            with self.subTest(character=actor, clip=name):
                self.compare(name)

    def test_joel_source_fidelity(self):
        self.check_character('joel', 'joel', [
            't1-walk-crouch-fwd', 't1-balance-walk-fwd', 'stair-walk-fwd-up'])

    def test_tommy_source_fidelity(self):
        self.check_character('young-tommy', 'young-tommy', [
            'tom-stairs-walk-up', 'tom-aggr-fist-walk-fw^idle-bw'])


if __name__=='__main__':
    unittest.main()
