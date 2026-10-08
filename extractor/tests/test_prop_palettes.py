"""Validate placed prop geometry against independently stored instance bounds."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import unittest

import numpy as np

from tlou_extractor.pak_reader import PakFile
from tlou_extractor.mesh_builder import MeshBuilder


class TestPropPalettes(unittest.TestCase):
    def check_level(self, name):
        path = Path(os.environ.get('TLOU_TEST_DATA', r'D:\TLOUPS4\Extracted')) / 'pak32' / (name + '-tstrm.pak')
        if not path.exists():
            self.skipTest('PS4 reference assets not installed')
        pak = PakFile(str(path))
        model = MeshBuilder(pak).models[0]
        geom = pak.get_first_item('GEOMETRY_1').abs_offset
        count = struct.unpack_from('<I', pak.data, geom + 0x48)[0]
        array = pak.read_ptr(geom + 0x50)
        checked = 0
        for index in range(1, count):
            instance = pak.read_ptr(array + index * 8)
            if not pak.read_ptr(instance + 0x38):
                continue
            meshes = [m for m in model.submeshes if m.name.endswith('#' + str(index))]
            self.assertTrue(meshes)
            points = np.array([v for m in meshes for v in m.positions])
            world = np.array(struct.unpack_from('<16f', pak.data, instance + 0x80)).reshape(4, 4).T
            local = (np.column_stack((points, np.ones(len(points)))) @ np.linalg.inv(world).T)[:, :3]
            expected = [struct.unpack_from('<3f', pak.data, instance + offset) for offset in (0x60, 0x70)]
            np.testing.assert_allclose([local.min(0), local.max(0)], expected, atol=0.00002, rtol=0,
                                       err_msg=f'{name}/instance {index}')
            for mesh in meshes:
                self.assertFalse(mesh.bone_indices, 'baked props must not be skinned twice')
            checked += 1
        self.assertGreater(checked, 0)
        return pak

    def test_house_instance_bounds(self):
        self.check_level('hom-house-interior')

    def test_freeway_instance_bounds(self):
        self.check_level('hom-town-freeway')

    def test_browser_books_match_source_bounds(self):
        if not shutil.which('node'):
            self.skipTest('Node.js not installed')
        root = Path(__file__).resolve().parents[1]
        viewer = (root / 'viewer.html').read_text(encoding='utf-8')
        helper = viewer[viewer.index('    function bakePropPalette('):viewer.index('    function parsePAKBuffer(')]
        generator = (root / 'build_viewer.py').read_text(encoding='utf-8')
        self.assertIn(helper.replace('{', '{{').replace('}', '}}'), generator)
        path = Path(os.environ.get('TLOU_TEST_DATA', r'D:\TLOUPS4\Extracted')) / 'pak32/hom-house-interior-tstrm.pak'
        if not path.exists():
            self.skipTest('PS4 reference assets not installed')
        pak = PakFile(str(path))
        geom = pak.get_first_item('GEOMETRY_1').abs_offset
        array = pak.read_ptr(geom + 0x50)
        # Obtain unplaced source meshes without baking any instances.
        original = pak.data
        data = bytearray(original)
        struct.pack_into('<I', data, geom + 0x48, 0)
        pak.data = bytes(data)
        meshes = MeshBuilder(pak).models[0].submeshes
        pak.data = original
        collections = pak.read_ptr(geom + 0x40)
        start = 0
        for index in range(struct.unpack_from('<I', original, geom + 0x38)[0]):
            collection = pak.read_ptr(collections + index*8)
            name = pak.read_str_at(pak.read_ptr(collection + 0x10))
            if 'hom-books-mod.ma' in name:
                break
            start += struct.unpack_from('<I', original, collection + 4)[0]
        raw = meshes[start]
        submeshes = pak.read_ptr(geom + 0x30)
        skin = pak.read_ptr(submeshes + start*136 + 0x60)
        for index in (127, 161):
            instance = pak.read_ptr(array + index*8)
            addresses = [instance + 0x38] + [skin + offset for offset in (8, 16, 24, 32)]
            payload = dict(path=str(path), instance=instance, pointers={a: pak.read_ptr(a) for a in addresses},
                           raw=dict(positions=[v for p in raw.positions for v in p],
                                    normals=[v for n in raw.normals for v in n], skinPtr=skin))
            script = helper + """
const fs=require('fs'); const input=JSON.parse(fs.readFileSync(0,'utf8'));
const data=fs.readFileSync(input.path), view=new DataView(data.buffer,data.byteOffset,data.byteLength);
const result=bakePropPalette(input.raw,input.instance,view,a=>input.pointers[a]||0);
const min=[Infinity,Infinity,Infinity], max=[-Infinity,-Infinity,-Infinity];
result.positions.forEach((v,i)=>{min[i%3]=Math.min(min[i%3],v);max[i%3]=Math.max(max[i%3],v)});
process.stdout.write(JSON.stringify([min,max]));
"""
            result = subprocess.run(['node', '-e', script], input=json.dumps(payload), text=True,
                                    capture_output=True, check=True)
            expected = [struct.unpack_from('<3f', original, instance+offset) for offset in (0x60, 0x70)]
            np.testing.assert_allclose(json.loads(result.stdout), expected, atol=0.00002, rtol=0)


if __name__ == '__main__':
    unittest.main()
