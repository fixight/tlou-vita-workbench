import copy
import math
import struct
import unittest
from tlou_extractor.trigger_aabb import encode_aabb_triggers


def region(name='door', source='hom-house-interior', **extra):
    return dict(id=source+':'+name, name=name, source_level=source, type='region',
                callbacks=[{}], shapes=[{'bounds_min':[0,0,0], 'bounds_max':[1,2,3]}], **extra)


class TriggerAabbTests(unittest.TestCase):
    def test_chapter_and_category_filter(self):
        a=region(); audio=region('sound','hom-house-audio'); reflection=region('reflection')
        other=region('door','mil-test'); manual=region('manual',port_binding={'name':'test'})
        manual['callbacks']=[]
        empty=region('empty');empty['callbacks']=[]
        blob=encode_aabb_triggers({'regions':[a,audio,reflection,other,manual,empty]}, {'hom-house-interior':'chunk.bin'})
        self.assertEqual(struct.unpack_from('<4sII',blob), (b'VTGR',1,2))
        self.assertIn(b'door',blob); self.assertIn(b'manual',blob)
        self.assertNotIn(b'mil-test',blob);self.assertNotIn(b'reflection',blob)

    def test_disjoint_and_edited_bounds(self):
        a=region();a['shapes'].append({'bounds_min':[10,11,12],'bounds_max':[13,14,15]})
        blob=encode_aabb_triggers({'regions':[a]})
        offset=12
        for value in (a['id'],a['name']):
            size=struct.unpack_from('<I',blob,offset)[0];offset+=4
            self.assertEqual(blob[offset:offset+size].decode(),value);offset+=size
        self.assertEqual(struct.unpack_from('<I',blob,offset)[0],2)
        self.assertEqual(struct.unpack_from('<12f',blob,offset+4),(0,0,0,1,2,3,10,11,12,13,14,15))
        self.assertEqual(len(blob),offset+4+48)

    def test_invalid_bounds_and_names(self):
        for value in (float('nan'),float('inf'),2):
            a=region();a['shapes'][0]['bounds_min'][0]=value
            with self.assertRaises(ValueError):encode_aabb_triggers({'regions':[a]})
        a=region('a'*4097)
        with self.assertRaises(ValueError):encode_aabb_triggers({'regions':[a]})
        a=region();a['shapes']=[]
        self.assertEqual(struct.unpack_from('<I',encode_aabb_triggers({'regions':[a]}),8)[0],0)

if __name__=='__main__':unittest.main()
