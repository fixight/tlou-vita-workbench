import os
from pathlib import Path
import unittest

from tlou_extractor.collision_reader import decode_havok_mesh, extract_collisions, CollisionFormatError
from tlou_extractor.pak_reader import PakFile


class TestCollisionReader(unittest.TestCase):
    def test_rejects_non_havok(self):
        with self.assertRaises(CollisionFormatError):
            decode_havok_mesh(b'not a collision')

    def check_asset(self, name, triangles):
        path = Path(os.environ.get('TLOU_TEST_DATA', r'D:\TLOUPS4\Extracted')) / 'pak32' / (name+'-tstrm.pak')
        if not path.exists():
            self.skipTest('PS4 fixtures unavailable')
        meshes, raw, warnings = extract_collisions(PakFile(str(path)))
        self.assertFalse(warnings)
        self.assertEqual(len(meshes), 1)
        mesh = meshes[0]
        # Matches native Havok numPrimitiveKeys (triangles including split quads).
        self.assertEqual(len(mesh['faces']), triangles)
        lo, hi = mesh['bounds']
        for point in mesh['vertices']:
            for axis in range(3):
                self.assertGreaterEqual(point[axis], lo[axis]-0.02)
                self.assertLessEqual(point[axis], hi[axis]+0.02)
        for face in mesh['faces']:
            self.assertEqual(len(set(face)), 3)
            self.assertTrue(all(0<=v<len(mesh['vertices']) for v in face))
        with self.assertRaises(CollisionFormatError):
            decode_havok_mesh(raw[0][1][:-64])

    def test_house_original_collision(self):
        self.check_asset('hom-house-interior', 9561)

    def test_freeway_original_collision(self):
        self.check_asset('hom-town-freeway', 5910)


if __name__ == '__main__':
    unittest.main()
