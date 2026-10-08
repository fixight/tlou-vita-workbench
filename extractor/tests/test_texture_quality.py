import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from tlou_extractor.texture_dds import build_dds
from tlou_extractor.texture_handler import TextureHandler, TextureInfo


class TestTextureQuality(unittest.TestCase):
    def test_bgra_pixels_are_not_bc7(self):
        data = build_dds(bytes([11,22,33,255])*4,2,2,87,is_pc=True)
        image = Image.open(io.BytesIO(data))
        self.assertEqual(image.getpixel((0,0)),(33,22,11,255))
        self.assertEqual(image.size,(2,2))

    def test_bc3_color_and_alpha_survive(self):
        block = bytes([255,255])+bytes(6)+struct.pack('<HHI',0xf800,0xf800,0)
        for fmt in (77,78):
            data = build_dds(block,4,4,fmt,is_pc=True)
            self.assertEqual(data[84:88],b'DXT5')
            self.assertEqual(Image.open(io.BytesIO(data)).getpixel((0,0)),(255,0,0,255))

    def test_unknown_format_does_not_guess(self):
        with self.assertRaisesRegex(ValueError,'Unsupported'):
            build_dds(bytes(64),4,4,12345,is_pc=True)

    def test_highest_exact_hash_wins_for_int_and_string(self):
        high = TextureInfo('test',512,512,71,131072,0,0x1234,raw_bytes=bytes(131072),hex_hash='0000000000001234')
        low = TextureInfo('test',64,64,71,2048,0,0x1234,raw_bytes=bytes(2048),hex_hash=high.hex_hash)
        handler = TextureHandler()
        handler.textures_by_hash[low.tex_hash]=low
        handler.textures_by_hex[low.hex_hash]=low
        with patch('tlou_extractor.texture_quality.indexed_texture',return_value=high):
            self.assertIs(handler.get_texture_by_hash(high.tex_hash),high)
            self.assertIs(handler.get_texture_by_hash(high.hex_hash),high)

    def test_later_resident_mip_cannot_overwrite_high_png(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.png'
            Image.new('RGB',(512,512),(1,2,3)).save(path)
            low=TextureInfo('test',64,64,71,2048,0,0,raw_bytes=bytes(2048))
            _,png=TextureHandler().export_texture(low,folder)
            self.assertEqual(Path(png),path)
            self.assertEqual(Image.open(png).size,(512,512))


if __name__ == '__main__':
    unittest.main()
