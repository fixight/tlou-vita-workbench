import json
import tempfile
import unittest
from pathlib import Path
from tlou_extractor.streaming_native import GameState, StreamPlanner, candidates, native_contains, select_native
from tlou_extractor.streaming_package import encode_runtime
from research.streaming.visibility_base import evaluate_selector

FIXTURE=Path(r'D:\TLOUPS4\AustinStreaming\streaming_runtime.json')


class NativeStreamingTests(unittest.TestCase):
    def test_grid_xyz_and_outside(self):
        grid={'lower':[0,0,0],'extent':[10,20,30],'dimensions':[2,2,3],
              'cells':[{'0x89335b6e':[str(i)]} for i in range(13)]}
        self.assertEqual(candidates(grid,[8,17,25]),['11'])
        self.assertEqual(candidates(grid,[10,17,25]),['12'])
        self.assertEqual(candidates(grid,[-1,0,0]),['12'])

    def test_sphere_and_cylinder_are_analytic(self):
        sphere={'shapes':[{'analytic':{'kind':'sphere','center':[1,2,3],'radius':2}}]}
        self.assertTrue(native_contains(sphere,[1,2,4.9]));self.assertFalse(native_contains(sphere,[3,4,3]))
        cylinder={'shapes':[{'analytic':{'kind':'cylinder','base':[1,2,3],'axis':[1,0,0],'radius':2,'height':5}}]}
        self.assertTrue(native_contains(cylinder,[5,2,3]));self.assertFalse(native_contains(cylinder,[0,2,3]))

    def test_edited_convex_uses_strict_runtime_boundary(self):
        box={'shapes':[{'vertices':[[x,y,z] for x,y,z in
            [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]],
            'faces':[[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]}]}
        self.assertFalse(native_contains(box,[-0.000001,0.5,0.5]))
        self.assertFalse(native_contains(box,[0,0.5,0.5]))
        self.assertTrue(native_contains(box,[0.000001,0.5,0.5]))

    def test_readiness_barrier_and_shared_dependency(self):
        doc={'levels':{'a':{'cache_dependencies':['shared']},'b':{'cache_dependencies':['shared']},'shared':{'cache_dependencies':['a']}}}
        p=StreamPlanner(doc)
        a={'region_id':'r','display':['a'],'resident_only':[]}
        b={'region_id':'s','display':['b'],'resident_only':[]}
        self.assertEqual(p.update(a,set())['load'],['a','shared'])
        self.assertFalse(p.visible)
        self.assertEqual(p.update(a,{'a','shared'})['show'],['a'])
        self.assertEqual(p.update(b,{'a','shared'})['hide'],[])
        result=p.update(b,{'a','b','shared'})
        self.assertEqual(result['show'],['b']);self.assertEqual(result['hide'],['a'])
        self.assertEqual(result['release'],[]) # cycle keeps a resident, but not visible
        self.assertEqual(p.update({'region_id':None},set())['status'],'outside_regions_hold')

    def test_missing_state_is_not_false(self):
        state=GameState()
        with self.assertRaisesRegex(ValueError,'Missing task'):state.status('c','t')
        for status,before in [('pending',True),('active',False),('complete',False)]:
            state.tasks['c','t']=status
            self.assertEqual(state.queries()['call_script','0x4d2bf414']('c','t'),before)

    @unittest.skipUnless(FIXTURE.exists(),'Original game fixture absent')
    def test_real_world_and_task_graph(self):
        doc=json.loads(FIXTURE.read_text(encoding='utf-8'))
        home=doc['task_graphs']['home'];self.assertEqual(len(home['nodes']),27)
        links={(home['nodes'].get(e['from'],{}).get('name'),home['nodes'].get(e['to'],{}).get('name')) for e in home['edges']}
        self.assertIn(('hom-house-escape','hom-road-suburbs-start'),links)
        world=[r for r in doc['regions'] if r['source_level']=='world-home']
        self.assertEqual(len(world),15)
        self.assertFalse(doc['warnings'])
        for region in world:
            shape=region['shapes'][0]
            point=[(a+b)/2 for a,b in zip(shape['bounds_min'],shape['bounds_max'])]
            self.assertTrue(native_contains(region,point),region['name'])
            self.assertIn(region['name'],candidates(doc['native_grids']['world-home'],point))
        state=GameState({(home['id'],task):'pending' for task in home['nodes']}, {'0x69c85a6d':False})
        house=next(r for r in world if r['name']=='regionshape-4747')
        self.assertEqual(evaluate_selector(house['selector'],state.queries()),1)
        state.tasks[home['id'],'0xa6b62704']='active'
        self.assertEqual(evaluate_selector(house['selector'],state.queries()),3)
        state.spawned['0x69c85a6d']=True
        with self.assertRaisesRegex(ValueError,'Missing object boolean'):evaluate_selector(house['selector'],state.queries())
        state.booleans['0x4f12da44','0x69c85a6d']=True
        self.assertEqual(evaluate_selector(house['selector'],state.queries()),2)
        self.assertEqual(encode_runtime(doc,'world-home')[:8],b'TLTR\x01\0\0\0')

    @unittest.skipUnless(FIXTURE.exists(),'Original game fixture absent')
    def test_first_match_not_union_and_zero_continues(self):
        doc=json.loads(FIXTURE.read_text(encoding='utf-8'))
        grid=doc['native_grids']['world-home']
        regions=[r for r in doc['regions'] if r['source_level']=='world-home']
        # Deliberately overlap two real volumes. Force their candidate order.
        a,b=regions[:2];b['shapes']=a['shapes']
        a['selector']={'kind':'constant','value':1};b['selector']={'kind':'constant','value':2}
        for cell in grid['cells']:cell['0x89335b6e']=[b['name'],a['name']]
        shape=a['shapes'][0];point=[(x+y)/2 for x,y in zip(shape['bounds_min'],shape['bounds_max'])]
        selected=select_native(doc,'world-home',point,GameState())
        self.assertEqual(selected['region_id'],b['id'])
        self.assertEqual(selected['display'],b['sets']['2']['display'])
        b['selector']['value']=0
        self.assertEqual(select_native(doc,'world-home',point,GameState())['region_id'],a['id'])


if __name__=='__main__':unittest.main()
