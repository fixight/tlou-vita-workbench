import unittest,struct,os
from pathlib import Path
import numpy as np
from tlou_extractor.anim_codec import decode_primary,AnimationDecodeError
from tlou_extractor.anim_reader import AnimationReader
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.skeleton_reader import SkeletonReader
from tests.test_anim_codec import synthetic_section,TestOtherCharacterRawReferences

class TestDirectCurves(unittest.TestCase):
 def section(self,opcode,width,map_opcode):
  s=bytearray(96)
  struct.pack_into('<7H',s,0,1547,0x8001,3,64,0,0,1)
  struct.pack_into('<5H',s,14,opcode,1,3,72,0)
  struct.pack_into('<5H',s,24,map_opcode,1,3,80,0)
  s[64]=width;struct.pack_into('<H',s,80,16 if map_opcode==1040 else 32)
  return s
 def test_half_vector_wire_axis_order(self):
  result,unknown=decode_primary(self.section(1050,48,1039),bytes.fromhex('4300b8003d00'),6,1,1)
  self.assertFalse(unknown);self.assertEqual(result[(0,'translation')][0],(1.25,-.5,3.5))
 def test_direct_quaternion_wire_largest_swap(self):
  s=self.section(1052,11,1040);s[72:76]=bytes([3,3,6,3])
  # Midpoint in each stored component, missing X. MSB-first frame, 5 pad bits.
  result,unknown=decode_primary(s,bytes.fromhex('9200'),2,1,1)
  self.assertFalse(unknown);np.testing.assert_allclose(result[(0,'rotation')][0],(1,0,0,0),atol=1e-12)
 def test_uniform_descriptors_are_shared(self):
  s=synthetic_section();struct.pack_into('<H',s,2,2);struct.pack_into('<H',s,16,2)
  s[97]=255;s[148:152]=bytes([255]*4) # padding must not be read as another descriptor
  result,unknown=decode_primary(s,bytes([0b01001000]),1,1,2)
  self.assertFalse(unknown);np.testing.assert_allclose(result[(0,'rotation')],result[(1,'rotation')],atol=1e-12)

class TestRealRigBinding(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=Path(os.environ.get('TLOU_TEST_DATA','D:/TLOUPS4/Extracted'))/'actor50'
  if not cls.root.exists():raise unittest.SkipTest('PS4 assets unavailable')
 def skeleton(self,name):return SkeletonReader.read_skeleton(PakFile(str(self.root/(name+'-tstrm.pak'))))
 def test_door_is_decoded_on_its_own_skeleton(self):
  pak=PakFile(str(self.root/'anim-sarah-player-tstrm.pak'));sarah=self.skeleton('sarah-skel');door=self.skeleton('door-l-skel-realskel')
  item=next(i for i in pak.get_items('ANIM') if i.name=='sar-p-open-pull-l--door')
  with self.assertRaises(AnimationDecodeError):AnimationReader._parse_clip(pak,item,sarah)
  clip=AnimationReader._parse_clip(pak,item,door);self.assertEqual(clip.source_rig_id,door.native_rig_id)
  self.assertTrue(any(door.bones[t.node_index].name=='door' for t in clip.tracks))
  clips=AnimationReader.read_animations(pak,sarah)
  self.assertNotIn(item.name,[c.name for c in clips]);self.assertIn('sar-p-open-pull-l--sarah',[c.name for c in clips])
 def test_variant_source_is_resolved_without_bank_name_rules(self):
  target=self.skeleton('young-joel-skel');source=self.skeleton('joel-skel');pak=PakFile(str(self.root/'anim-joel-tstrm.pak'))
  clips=AnimationReader.read_animations(pak,target)
  self.assertTrue(clips);self.assertTrue(all(c.source_rig_id==source.native_rig_id and c.target_rig_id==target.native_rig_id for c in clips))
  self.assertFalse(any('backpack' in c.name for c in clips if c.source_rig_id!=source.native_rig_id))
 def test_new_direct_codecs_match_independent_raw_foot_channels(self):
  TestOtherCharacterRawReferences().check_character('joel','joel',['run-jump-up-2m^ledge-chest-end', 'run-jump-up-2m^ledge-chest-begin', 'stealth-run-jump-up-2m^ledge-chest-begin', 'walk-jump-up-0-5m', 'idle-jump-up-2m^ledge-chest-mid', 'run-jump-up-2m^ledge-chest-mid', 'idle-jump-up-2m^ledge-chest-begin', 'idle-jump-up-2m^ledge-chest-end'])

 def test_mixed_bank_keeps_shared_and_exact_female_clips(self):
  target=self.skeleton('infected-fem-skel');source=self.skeleton('infected-skel')
  clips=AnimationReader.read_animations(PakFile(str(self.root/'anim-inf-shared-tstrm.pak')),target)
  self.assertGreater(len(clips),160)
  self.assertIn(source.native_rig_id,{c.source_rig_id for c in clips})
  self.assertIn(target.native_rig_id,{c.source_rig_id for c in clips})
  self.assertTrue(all(c.target_rig_id==target.native_rig_id for c in clips))
