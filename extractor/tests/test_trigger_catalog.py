import copy
import json
import tempfile
import unittest
from pathlib import Path
from tlou_extractor.trigger_catalog import callback_calls,binding_from_properties,build_catalog
from tlou_extractor.streaming_package import upgrade_document,write_package

FIXTURE=Path(r'D:\TLOUPS4\AustinStreaming\streaming_runtime.json')


class ObjectProperties(dict):
    name='Test trigger'


class TriggerCatalogTests(unittest.TestCase):
    def test_conditional_calls_keep_both_guards(self):
        code=[{'operation':'resolve_symbol','destination':0,'symbol_id':'0xb3189857'},
              {'operation':'symbol_id','destination':24,'symbol_id':'0x11111111'},
              {'operation':'symbol_id','destination':25,'symbol_id':'0x22222222'},
              {'operation':'jump_if_zero','condition_register':2,'target':6},
              {'operation':'call_native','destination':0,'function_register':0,'argument_count':2},
              {'operation':'return','source':0},
              {'operation':'call_native','destination':0,'function_register':0,'argument_count':2},
              {'operation':'return','source':0}]
        for i,inst in enumerate(code):inst['offset']=i*4
        result=callback_calls({'instructions':code},{'0xb3189857':{'name':'send-event','source':'fixture'}})
        self.assertEqual(len(result['calls']),2)
        self.assertEqual({c['guards'][0]['nonzero'] for c in result['calls']},{True,False})
        self.assertTrue(all(c['target']['id']=='0x22222222' for c in result['calls']))

    def test_unknown_instruction_never_reuses_stale_arguments(self):
        code=[{'operation':'resolve_symbol','destination':0,'symbol_id':'0xb3189857','offset':0},
              {'operation':'unknown','opcode':'0x41','offset':4},
              {'operation':'call_native','destination':0,'function_register':0,'argument_count':2,'offset':8}]
        result=callback_calls({'instructions':code},{'0xb3189857':{'name':'send-event','source':'fixture'}})
        self.assertEqual(result['calls'][0]['function']['kind'],'unresolved')
        self.assertNotIn('target',result['calls'][0]);self.assertTrue(result['limitations'])

    def test_port_binding_is_explicit_and_validated(self):
        props=ObjectProperties(nd_cpp_action='JoelRoomExplosion',nd_cpp_phase='enter',nd_cpp_once=True,
                               nd_cpp_parameters='{"delay":2.5}')
        self.assertIsNone(binding_from_properties(props))
        props['nd_cpp_enabled']=True
        self.assertEqual(binding_from_properties(props)['parameters'],{'delay':2.5})
        for key,bad in [('nd_cpp_phase','tick'),('nd_cpp_action','open-door'),('nd_cpp_parameters','[]'),('nd_cpp_parameters','{"x":NaN}')]:
            previous=props.get(key);props[key]=bad
            with self.assertRaises(ValueError):binding_from_properties(props)
            props[key]=previous

    def test_binding_survives_editor_merge_and_package(self):
        region={'id':'test:r','name':'r','name_id_raw':'0x12345678','source_level':'test',
                'source_file':'test.pak','offset':8,'type':'gameplay_region','shapes':[],
                'properties':[],'callbacks':[]}
        base={'regions':[region],'native_grids':{},'levels':{},'coverage':{}}
        edited=copy.deepcopy(base);edited['regions'][0]['port_binding']={'action':'OpenDoor','phase':'enter','once':True}
        merged=upgrade_document(edited,base)
        with tempfile.TemporaryDirectory() as folder:
            result=write_package(merged,folder)
            bindings=json.loads((Path(folder)/'trigger_bindings.json').read_text(encoding='utf-8'))
        self.assertEqual(bindings['bindings'][0]['action']['action'],'OpenDoor')
        self.assertEqual(result['trigger_catalog']['triggers'][0]['port_binding']['action'],'OpenDoor')
        self.assertFalse(result['runtime_ready'])

    @unittest.skipUnless(FIXTURE.exists(),'Original game data absent')
    def test_original_prologue_event_and_controller_spelling(self):
        doc=json.loads(FIXTURE.read_text(encoding='utf-8'))
        cards={c['id']:c for c in build_catalog(doc)['triggers']}
        door=cards['hom-house-interior:vox-reg-house-leave-joelroom-1']
        call=door['callbacks'][0]['calls'][0]
        self.assertEqual(call['event']['name'],'left-joels-room')
        self.assertEqual(call['target']['name'],'ss-home-house-vox-controller-1')
        self.assertEqual(door['callbacks'][0]['phase'],'enter')
        self.assertTrue(door['controller_contexts'][0]['handlers'])
        explosion=cards['hom-house-interior:hom-house-rgn-explosion-downstairs-1']
        self.assertEqual(explosion['callbacks'][0]['calls'][0]['target']['name'],'ss-hom-house-joel-room-1')
        states={h['state'] for c in explosion['controller_contexts'] for h in c['handlers']}
        self.assertIn('explosion-one-inside',states)
        self.assertIsNone(explosion['port_binding'])


if __name__=='__main__':unittest.main()
