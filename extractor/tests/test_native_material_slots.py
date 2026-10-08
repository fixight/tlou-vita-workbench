from pathlib import Path
import struct
import unittest
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.mesh_builder import MeshBuilder


class TestNativeMaterialSlots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(r'D:\TLOUPS4\Extracted\actor50\ambulance-tstrm.pak')
        if not path.exists(): raise unittest.SkipTest('Native ambulance fixture unavailable')
        cls.pak=PakFile(str(path))
        cls.meshes=[sm for model in MeshBuilder(cls.pak).models for sm in model.submeshes]

    def test_shader_texture_count_matches_next_array_boundary(self):
        data=self.pak.data
        resource=self.pak.get_items('GEOMETRY_1')[0].abs_offset
        count=struct.unpack_from('<I',data,resource+0x68)[0]
        shaders=self.pak.read_ptr(resource+0x70)
        arrays=[self.pak.read_ptr(shaders+i*72+0x28) for i in range(count)]
        # Glass, siren-head, siren-body, tires: exactly adjacent texture arrays.
        for i in (2,3,4,5,6):
            actual=struct.unpack_from('<I',data,shaders+i*72+0x38)[0]
            self.assertEqual(arrays[i]+actual*40,arrays[i+1])

    def test_glass_does_not_take_neighbors_normal(self):
        meshes=[m for m in self.meshes if m.material_name=='homtown-ambulance-glass']
        self.assertTrue(meshes)
        for mesh in meshes:
            self.assertEqual(mesh.diffuse_hash,'bda06158edf3e33c')
            self.assertEqual(mesh.normal_hash,'')
            self.assertNotIn('638576769843de40',mesh.texture_hashes)

    def test_wheels_use_their_own_color_and_normal(self):
        meshes=[m for m in self.meshes if m.material_name=='homtown-ambulance-tires']
        self.assertTrue(meshes)
        for mesh in meshes:
            self.assertEqual(mesh.diffuse_hash,'4eb78fd4c48c180d')
            self.assertEqual(mesh.normal_hash,'228d72a2811278e7')

    def test_color1_wins_over_color4_specular(self):
        path=Path(r'D:\TLOUPS4\Extracted\pak32\hom-road-suburb-tstrm.pak')
        if not path.exists(): self.skipTest('Native road fixture unavailable')
        meshes=[m for model in MeshBuilder(PakFile(str(path))).models for m in model.submeshes
                if m.material_name=='hom-road-signs-text']
        self.assertTrue(meshes)
        self.assertTrue(all(m.diffuse_hash=='fa3dfd2a2f4c1054' for m in meshes))

    def test_primary_and_secondary_uv_do_not_concatenate(self):
        meshes=[m for m in self.meshes if m.material_name=='homtown-ambulance-body-box-ao']
        self.assertTrue(meshes)
        for mesh in meshes:
            self.assertEqual(len(mesh.uv0),len(mesh.positions))
            self.assertEqual(len(mesh.uv12),len(mesh.positions))
            self.assertAlmostEqual(mesh.uv0[0][0],2.57698392868)
            self.assertAlmostEqual(mesh.uv12[0][0],.43821799755)
        from tlou_extractor.gltf_writer import GLTFWriter
        writer=GLTFWriter()
        writer.add_submesh(meshes[0])
        self.assertIn('TEXCOORD_0',writer.meshes[0]['primitives'][0]['attributes'])
        self.assertIn('TEXCOORD_2',writer.meshes[0]['primitives'][0]['attributes'])


if __name__=='__main__': unittest.main()
