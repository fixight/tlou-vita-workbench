import unittest, math
from tlou_extractor.region_runtime import convex_volume, contains, segment_intersects, select_active_sets

class PositionPreview(unittest.TestCase):
    def test_rotated_volume_and_fast_crossing(self):
        # Long box rotated 45 degrees: its AABB contains points outside the actual box.
        c=math.sqrt(.5)
        vertices=[((x-y)*c,(x+y)*c,z) for x,y,z in
                  [(-2,-.5,-1),(2,-.5,-1),(2,.5,-1),(-2,.5,-1),
                   (-2,-.5,1),(2,-.5,1),(2,.5,1),(-2,.5,1)]]
        shape=convex_volume(vertices,[[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]])
        self.assertTrue(contains(shape,(0,0,0)))
        self.assertTrue(contains(shape,vertices[0]))
        self.assertFalse(contains(shape,(1.5,-1.5,0)))
        self.assertTrue(segment_intersects(shape,(-10,0,0),(10,0,0)))
        self.assertFalse(segment_intersects(shape,(-10,0,3),(10,0,3)))

    def test_shared_resource_is_retained_and_display_wins(self):
        records=[{'id':'a','selector':{'kind':'constant','value':1},
                  'sets':{'1':{'display':['road'],'resident_only':['house']}}},
                 {'id':'b','selector':{'kind':'script_requires_game_state'},
                  'sets':{'2':{'display':['house'],'resident_only':['audio']}}}]
        result=select_active_sets(records,{'a':9,'b':2})
        self.assertEqual(result['display'],['house','road'])
        self.assertEqual(result['resident_only'],['audio'])
        self.assertEqual(result['required'],['audio','house','road'])
        self.assertEqual(result['conditions'][0]['variant'],2)
        # A missing scenario state is reported rather than falling back to a different set.
        invalid=select_active_sets(records,{'b':9})
        self.assertFalse(invalid['conditions'][0]['valid'])
        self.assertEqual(invalid['display'],['road'])
        zero=select_active_sets([records[1]],{'b':0})
        self.assertEqual(zero['required'],[])

if __name__=='__main__':unittest.main()
