import unittest
from pathlib import Path
import numpy as np
import tempfile,json,struct
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.static_lighting import extract, read_streams


class StaticLightingTests(unittest.TestCase):
    def test_gltf_and_glb_keep_lighting_sidecar_reference(self):
        from tlou_extractor.gltf_writer import GLTFWriter
        writer=GLTFWriter()
        value={'uri':'static_lighting/lighting.json','reconstruction':'experimental','records':393}
        writer.asset_extras['nd_static_lighting']=value
        with tempfile.TemporaryDirectory() as tmp:
            glb=Path(tmp)/'scene.glb'; gltf=Path(tmp)/'scene.gltf'
            writer.export_glb(str(glb)); writer.export_gltf(str(gltf))
            raw=glb.read_bytes(); length=struct.unpack_from('<I',raw,12)[0]
            self.assertEqual(json.loads(raw[20:20+length])['asset']['extras']['nd_static_lighting'],value)
            self.assertEqual(json.loads(gltf.read_text())['asset']['extras']['nd_static_lighting'],value)

    def test_invalid_table_rejected(self):
        class Fake:
            data=bytes(64)
        with self.assertRaises(ValueError): read_streams(Fake(),60,2,4)

    def test_house_instance_lighting_is_not_prototype_placeholder(self):
        path=Path('D:/TLOUPS4/Extracted/pak32/hom-house-interior-tstrm.pak')
        if not path.exists(): self.skipTest('Native PS4 fixture unavailable')
        records,warnings=extract(PakFile(str(path)))
        self.assertFalse(warnings)
        self.assertEqual(len(records),393)
        self.assertEqual(sum(8 in r['arrays'] for r in records),381)
        self.assertTrue(any(np.max(r['arrays'][8])>0 for r in records if 8 in r['arrays']))
        self.assertTrue(any(r['slots'].get('g_tLmLightColor')=='89e7dcee4bb72644' for r in records))
        for r in records:
            for array in r['arrays'].values():
                self.assertEqual(len(array),r['vertex_count'])
                self.assertTrue(np.isfinite(array).all())
        # Preserve non-normalized coordinates. They must not silently become wrapped UVs.
        self.assertTrue(any(np.max(r['arrays'][5])>1 for r in records if 5 in r['arrays']))

    def test_other_level_uses_its_own_lightmaps(self):
        path=Path('D:/TLOUPS4/Extracted/pak32/hom-woods-hill-tstrm.pak')
        if not path.exists(): self.skipTest('Native PS4 fixture unavailable')
        records,warnings=extract(PakFile(str(path)))
        self.assertFalse(warnings)
        self.assertGreater(len(records),50)
        self.assertTrue(any('g_tLightMap' in r['slots'] for r in records))
        hashes={h for r in records for h in r['slots'].values()}
        self.assertNotIn('89e7dcee4bb72644',hashes)


if __name__=='__main__': unittest.main()
