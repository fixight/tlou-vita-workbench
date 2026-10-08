import json
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_audio_bank import HEADER, build, atrac9_xvag, sound_id

class AudioBankTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        with wave.open(str(self.root / 'tone.wav'), 'wb') as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(48000)
            output.writeframes(struct.pack('<64h', *([100, -100] * 32)))
    def tearDown(self):
        self.temporary.cleanup()
    def config(self, sounds, budget=1024):
        path = self.root / 'audio.json'
        path.write_text(json.dumps({'sounds': sounds, 'resident_budget_bytes': budget}), encoding='utf-8')
        return path
    def test_stereo_format_and_shared_asset_paths(self):
        config = self.config([{'name':'door.open','source':'tone.wav'},
                              {'name':'music','source':'tone.wav','storage':'stream','bus':'music'}])
        result = build(config, self.root / 'output')
        self.assertEqual(result['resident_bytes'], 128)
        item = result['sounds'][0]
        data = (self.root / 'output' / item['file']).read_bytes()
        fields = HEADER.unpack(data[:64])
        self.assertEqual(HEADER.size, 64)
        self.assertEqual(fields[:6], (b'VAS1', 1, 1, 48000, 2, 32))
        self.assertEqual(fields[10], 128)
        second = build(config, self.root / 'output', bank_name='city.vabk')
        self.assertEqual(item['file'], second['sounds'][0]['file'])
        self.assertEqual(int(item['id'], 16), sound_id('door.open'))
    def test_invalid_bank_does_not_publish(self):
        for sounds, budget in [([{'name':'x','source':'tone.wav'}], 10),
                ([{'name':'x','source':'tone.wav'}, {'name':'x','source':'tone.wav'}], 1024),
                ([{'name':'x','source':'tone.wav','volume': float('nan')}], 1024)]:
            with self.assertRaises(ValueError):
                build(self.config(sounds, budget), self.root / 'output')
            self.assertFalse((self.root / 'output' / 'level.vabk').exists())
    def test_xvag_preserves_encoded_blocks_and_priming(self):
        fmt = struct.pack('<9I', 1, 9, 1792, 1792, 1, 48000, 512, 1, 1)
        info = struct.pack('<II4sIII', 256, 1024, bytes.fromhex('fe7007f0'), 1792, 256, 256)
        chunks = b'fmat' + struct.pack('<I',len(fmt)) + fmt + b'a9in' + struct.pack('<I',len(info)) + info
        start = 32 + len(chunks)
        source = b'XVAG' + struct.pack('<I',start) + bytes(24) + chunks + bytes([0x35]) * 512
        result = atrac9_xvag(source)
        fields = HEADER.unpack(result[:64])
        self.assertEqual(fields[2],2)
        self.assertEqual(fields[6:9], (256, 1024, 256))
        self.assertEqual(result[64:],source[start:])
        padded = source[:start] + bytes(128) + b'RIFF' + bytes(124) + source[start:]
        self.assertEqual(atrac9_xvag(padded), result)
        with self.assertRaises(ValueError):
            atrac9_xvag(source[:start] + bytes(512))
        # Interleaved streams must not be treated as a continuous single voice.
        damaged = bytearray(source)
        struct.pack_into('<I',damaged,40+28,2)
        with self.assertRaises(ValueError): atrac9_xvag(damaged)

if __name__ == '__main__':
    unittest.main()
