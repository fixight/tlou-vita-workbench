import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tlou_extractor import editor_export as export


class TestMeshUpload(unittest.TestCase):
    def test_staged_meshes_keep_order_and_owner_without_combined_json(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(export,'ROOT',Path(tmp)), patch.object(export,'MESH_UPLOADS',{}):
            token = export.begin_mesh_upload()
            for n in range(3):
                self.assertEqual(export.append_mesh_upload(token, {'positions':[n,0,0], 'indices':[],
                                                                   'sourceFile':f'level{n}-tstrm.pak'}),n+1)
            payload = {'_mesh_paths':tuple(export.MESH_UPLOADS[token])}
            meshes = list(export.input_meshes(payload))
            self.assertEqual([m['positions'][0] for m in meshes],[0,1,2])
            self.assertEqual(meshes[2]['sourceFile'],'level2-tstrm.pak')
            with self.assertRaises(ValueError):
                export.append_mesh_upload(token, {'positions':'bad', 'indices':[]})


if __name__ == '__main__':
    unittest.main()
