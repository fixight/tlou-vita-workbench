import tempfile, unittest
from pathlib import Path
from PIL import Image
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.mesh_builder import MeshBuilder
from tlou_extractor.material_transparency import shader_masks, export_mask, transparency_extras

class NativeOpacity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path('D:/TLOUPS4/Extracted/pak32/hom-house-interior-tstrm.pak')
        if not path.is_file():raise unittest.SkipTest('PS4 fixture unavailable')
        cls.pak=PakFile(str(path))
        cls.meshes=[s for model in MeshBuilder(cls.pak).models for s in model.submeshes]

    def test_native_slot_is_not_albedo_or_synthesized_alpha(self):
        plants=[m for m in self.meshes if m.material_name=='hom-houseplant-02']
        self.assertTrue(plants)
        self.assertTrue(all(m.transparency_hash=='a1d0d8e29dc316ac' for m in plants))
        self.assertTrue(all(m.diffuse_hash=='be424c35a59028cd' for m in plants))
        glass=[m for m in self.meshes if m.material_name=='hom-house-glass-sarahs']
        self.assertTrue(glass)
        self.assertTrue(all(m.transparency_hash=='4a3dabb6ee604134' for m in glass))
        self.assertTrue(any(v['transparency_hash']==plants[0].transparency_hash for v in shader_masks(self.pak).values()))

    def test_highest_mip_and_linear_red_are_preserved(self):
        with tempfile.TemporaryDirectory(dir='D:/TLOUPS4') as folder:
            path=export_mask('a1d0d8e29dc316ac',folder)
            with Image.open(path) as image:
                self.assertEqual(image.mode,'L');self.assertEqual(image.size,(512,512))
                self.assertEqual(image.getextrema(),(0,255))
            path=export_mask('4a3dabb6ee604134',folder)
            with Image.open(path) as image:self.assertEqual(image.getextrema(),(3,42))
            mesh=next(m for m in self.meshes if m.material_name=='hom-houseplant-02')
            props=transparency_extras(mesh,folder)
            self.assertFalse(props['nd_transparency_missing'])
            self.assertEqual(props['nd_transparency_uri'],'textures/opacity_a1d0d8e29dc316ac.png')

if __name__=='__main__':unittest.main()
