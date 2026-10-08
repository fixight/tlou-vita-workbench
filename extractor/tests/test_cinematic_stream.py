"""Real cinematic streams: full frames, chunk seams, motion, unusual codecs."""
import os
from pathlib import Path
import struct
import unittest
import numpy as np
from research.streaming.psarc import Psarc
from tlou_extractor.animation_binding import skeleton_library,clip_rig_id
from tlou_extractor.anim_reader import AnimationReader
from tlou_extractor.anim_stream_reader import read_streamed_clip,stream_packages
from tlou_extractor.animation_placement import placement_motion
from tlou_extractor.door_interaction_data import animation_entry
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.skeleton_reader import SkeletonReader


class CinematicStreams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actor=Path(os.environ.get('TLOU_TEST_DATA','D:/TLOUPS4/Extracted'))/'actor50'
        mains=list(Path('D:/').glob('*/The Last of Us*/build/Image0/build/ps4/main'))
        if not mains or not cls.actor.exists():
            raise unittest.SkipTest('Original PS4 cinematic assets are not installed')
        cls.archive=Psarc(mains[0]/'core.psarc')
        cls.rigs=skeleton_library(cls.actor)

    def decode(self,bank_name,name,stream_name):
        bank=PakFile(str(self.actor/(bank_name+'-tstrm.pak')))
        item=next(i for i in bank.get_items('ANIM') if i.name==name)
        stream=self.archive.read('animstream14/igc-stream-'+stream_name+'.stm')
        clip=read_streamed_clip(bank,item,self.rigs[clip_rig_id(bank,item)],stream)
        frames=struct.unpack_from('<H',bank.data,bank.read_ptr(item.abs_offset+0x28)+14)[0]
        self.assertFalse(clip.unsupported_opcodes)
        self.assertTrue(clip.tracks)
        self.assertLess(clip.stream_overlap_max_error,.002)
        for track in clip.tracks:
            self.assertEqual(len(track.values),frames)
            self.assertEqual(len(track.timestamps),frames)
            self.assertEqual(track.timestamps[-1],clip.duration)
            self.assertTrue(all(a<b for a,b in zip(track.timestamps,track.timestamps[1:])))
        return bank,item,clip,stream

    def test_joel_full_study_and_multiple_width_groups(self):
        _,_,clip,_=self.decode('hom1-house-study','hom1-house-study--joel','hom1-house-study')
        self.assertEqual(len(clip.stream_chunks),30)
        self.assertAlmostEqual(clip.duration,898/30)

    def test_sarah_float32_constants_and_raw_dynamic_curves(self):
        bank,item,clip,_=self.decode('hom1-house-study-and-escape','hom1-house-study-and-escape-outro--sarah','hom1-house-study-and-escape-outro')
        root=next(t for t in clip.tracks if t.node_index==0 and t.target_path=='translation')
        # Independent first-sample float wire values (Z,Y,X) in cached chunk 0.
        chunk=next(i for i in bank.get_items('ANIM') if i.name==item.name+'-chunk-0')
        ac=bank.read_ptr(chunk.abs_offset+0x28)
        stream=ac+struct.unpack_from('<I',bank.data,ac+0x38)[0]
        np.testing.assert_allclose(root.values[0],tuple(reversed(struct.unpack_from('>3f',bank.data,stream))),atol=0)
        self.assertEqual(len(clip.stream_chunks),51)

    def test_tommy_zero_stride_constant_quantizers(self):
        self.decode('hom1-house-study-and-escape','hom1-house-study-and-escape-outro--tommy','hom1-house-study-and-escape-outro')

    def test_world_motion_reads_entire_reference_not_only_entry(self):
        bank,item,clip,_=self.decode('hom1-house-study','hom1-house-study--joel','hom1-house-study')
        locator={'position':[0,0,0],'rotation_xyzw':[0,0,0,1]}
        motion=placement_motion(bank,item,locator,clip.fps,899)
        entry=animation_entry(bank,item)['relative_to_shared_locator']
        np.testing.assert_allclose(motion['samples'][0][:3],entry['position'],atol=1e-12)
        self.assertGreater(np.linalg.norm(np.array(motion['samples'][-1][:3])-motion['samples'][0][:3]),4)

    def test_bedroom_pillow_constant_placement_and_full_stream(self):
        bank = PakFile(str(self.actor / 'hom1-tstrm.pak'))
        item = next(i for i in bank.get_items('ANIM')
                    if i.name == 'hom1-house-sarah-bedroom-phone--pillow')
        skeleton = SkeletonReader.read_skeleton(PakFile(str(self.actor / 'hom-twin-pillow-tstrm.pak')))
        stream = self.archive.read('animstream14/igc-stream-hom1-house-sarah-bedroom-phone.stm')
        clip = read_streamed_clip(bank, item, skeleton, stream)
        self.assertFalse(clip.unsupported_opcodes)
        self.assertEqual(len(clip.stream_chunks), 31)
        self.assertTrue(all(len(track.values) == 912 for track in clip.tracks))
        locator = {'position': [16.9, 31.4, -26.9], 'rotation_xyzw': [0, 0, 0, 1]}
        motion = placement_motion(bank, item, locator, clip.fps, 912)
        self.assertEqual(motion['flags'], '0x01fe')
        self.assertEqual(len(motion['samples']), 912)
        np.testing.assert_array_equal(motion['samples'], [motion['samples'][0]] * 912)

    def test_truncated_stream_refused(self):
        stream=self.archive.read('animstream14/igc-stream-hom1-house-study.stm')
        with self.assertRaises(ValueError):
            list(stream_packages(stream[:-1]))


if __name__=='__main__':
    unittest.main()
