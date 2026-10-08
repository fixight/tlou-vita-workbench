import struct
import unittest
from pathlib import Path
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.cinematic_audio import animation_notes, voice_resource, subtitle_metadata
from research.streaming.visibility_base import string_id

ROOT=Path(__file__).resolve().parents[1]

class NativeCinematicAudioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required=[ROOT.parent/'Extracted/actor50/hom1-tstrm.pak',
                  ROOT/'research/cinematics/vox-igc-hometown.bin',
                  ROOT/'research/cinematics/russian-F188.xvag',
                  ROOT/'research/cinematics/russian-F189.xvag']
        if not all(path.exists() for path in required):
            raise unittest.SkipTest('Requires locally extracted native cinematic audio fixtures')

    def test_phone_note_has_native_frame_not_guessed_start(self):
        pak=PakFile(str(ROOT.parent/'Extracted/actor50/hom1-tstrm.pak'))
        item=next(i for i in pak.get_items('ANIM') if i.name=='hom1-house-sarah-bedroom-phone--sarah')
        notes=animation_notes(pak,item,30)
        sound=next(n for n in notes if n['properties'].get(string_id('name'))==string_id('sfx-sarah-bedroom-phone-call'))
        self.assertEqual(sound['frame'],154)
        self.assertAlmostEqual(sound['time'],5.133333333333334)
        self.assertEqual(animation_notes(pak,next(i for i in pak.get_items('ANIM') if i.name=='hom1-house-sarah-bedroom-phone--bed'),30),[])

    def test_localized_voice_identity_and_preroll_marks(self):
        data=(ROOT/'research/cinematics/vox-igc-hometown.bin').read_bytes()
        for role,ident,frames in [('sar','F189',[326,424,575]),('tmy','F188',[348,471])]:
            binding=voice_resource(data,'vox-igc-'+role+'-igc-hom-bedroom-phone-001')
            self.assertEqual(binding['speech_id'],ident)
            metadata=subtitle_metadata((ROOT/('research/cinematics/russian-'+ident+'.xvag')).read_bytes())
            self.assertEqual(metadata['speech_id'],ident)
            self.assertEqual(metadata['language_id'],17)
            self.assertEqual([e['start_frame'] for e in metadata['entries']],frames)
        with self.assertRaises(ValueError):voice_resource(data,'vox-igc-missing')

    def test_bad_subtitle_count_is_rejected(self):
        data=bytearray((ROOT/'research/cinematics/russian-F189.xvag').read_bytes())
        header=data.find(b'SUBT')
        struct.pack_into('<I',data,header+28,100000)
        with self.assertRaises(ValueError):subtitle_metadata(data)

if __name__=='__main__':unittest.main()
