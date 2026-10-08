import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import serve


class TestTextureLookup(unittest.TestCase):
    def test_missing_hash_never_uses_same_name(self):
        index = {'brick-color': {'pak': 'wrong-chapter.pak'}}
        self.assertIsNone(serve.resolve_texture(index, '0123456789abcdef', 'brick-color'))

    def test_exact_hash_can_resolve_another_chapter(self):
        entry = {'pak': 'Extracted2/pak32/bil-town-tstrm.pak'}
        self.assertIs(serve.resolve_texture({'0123456789abcdef': entry}, '0123456789ABCDEF'), entry)

    def test_name_only_requires_exact_match(self):
        entry = {'pak': 'correct.pak'}
        index = {'brick-color': entry}
        self.assertIs(serve.resolve_texture(index, tex_name='BRICK-COLOR.dds'), entry)
        self.assertIsNone(serve.resolve_texture(index, tex_name='brick'))
        self.assertIsNone(serve.resolve_texture(index))

    def test_new_chapter_invalidates_source_inventory(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, TLOU_ASSET_ROOT=directory):
            first = Path(directory) / 'Extracted/texturedict1'
            first.mkdir(parents=True)
            (first / 'shared.pak').write_bytes(b'first')
            before = serve.texture_sources(serve.texture_directories())
            second = Path(directory) / 'Extracted2/pak32'
            second.mkdir(parents=True)
            (second / 'bil-town-tstrm.pak').write_bytes(b'second')
            after = serve.texture_sources(serve.texture_directories())
            self.assertIn(str(second), serve.texture_directories())
            self.assertNotEqual(before, after)
            self.assertEqual(len(after), 2)


if __name__ == '__main__':
    unittest.main()
