import importlib.util,numpy as np,unittest,struct
from pathlib import Path
spec=importlib.util.spec_from_file_location('sky',Path(__file__).resolve().parents[1]/'tlou_extractor/blender_vita_sky.py');sky=importlib.util.module_from_spec(spec);spec.loader.exec_module(sky)
class SkyTests(unittest.TestCase):
 def test_large_dome_uses_independent_scale(self):
  points=np.array([[11096,0,0],[-11096,4000,23.2],[1,11096,-7000]])
  packed,step=sky.pack_positions(points)
  self.assertLessEqual(np.abs(packed.astype(float)*step-points).max(),step*.50001)
  self.assertEqual(packed.dtype,np.dtype('<i2'));self.assertLessEqual(np.abs(packed.astype(int)).max(),32760)
 def test_bad_positions_rejected(self):
  for p in ([[0,0,0]],[[float('nan'),1,0]]):
   with self.assertRaises(ValueError):sky.pack_positions(p)
 def test_seam_split_preserves_area(self):
  points=np.array([[0,0,0],[2,0,0],[0,2,0]],float)
  parts=sky.split_uv_seam(points,np.array([[.98,0],[.02,0],[.02,1]]))
  self.assertGreater(len(parts),1)
  total=0
  for p,uv in parts:
   self.assertGreaterEqual(uv.min(),0);self.assertLessEqual(uv.max(),1)
   self.assertLessEqual(np.ptp(uv[:,0]),.040001)
   total+=np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0]))*.5
  self.assertAlmostEqual(total,2)
 def test_atlas_edges_repeat_and_alpha_survives(self):
  a=np.array([[[1,2,3,64],[4,5,6,192]]],np.uint8)
  atlas,rects=sky.make_atlas([a,np.array([[[20,30,40,0]]],np.uint8)])
  self.assertTrue(np.array_equal(atlas[2,2:4],a[0]))
  self.assertTrue(np.array_equal(atlas[0,0],a[0,0]));self.assertTrue(np.array_equal(atlas[4,5],a[0,1]))
  self.assertEqual(len(rects),2)
 def test_descriptor_records_one_mesh_and_atlas(self):
  b=sky.descriptor(.1,'app0:/assets/models/a.bin','app0:/assets/textures/a.bin',['app0:/assets/models/old.bin'])
  self.assertEqual(b[:4],b'SKY1');self.assertAlmostEqual(struct.unpack_from('<f',b,4)[0],.1)
  off=8
  for expected in ('app0:/assets/models/a.bin','app0:/assets/textures/a.bin'):
   size=struct.unpack_from('<H',b,off)[0];off+=2;self.assertEqual(b[off:off+size].decode(),expected);off+=size
  self.assertEqual(struct.unpack_from('<I',b,off)[0],1)
if __name__=='__main__':unittest.main()
