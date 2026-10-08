import unittest
from pathlib import Path
from tlou_extractor.pak_reader import PakFile
from tlou_extractor.door_interaction_data import spawner_records, rig_anchors, paired_clips, symbol_references

ROOT = Path('D:/TLOUPS4/Extracted')

@unittest.skipUnless(ROOT.exists(), 'Native assets unavailable')
class NativeDoorEvidenceTests(unittest.TestCase):
    def test_door_controller_and_animation_locator_are_distinct(self):
        records = spawner_records(PakFile(str(ROOT/'pak32/hom-house-interior-ingame14.pak')))
        by_name = {r['name']: r for r in records}
        bedroom = by_name['hom-hdr-bedroom-door-1']
        self.assertIn('ss-hom-house-door-open', [p.get('string') for p in bedroom['properties']])
        locator = by_name['ap-hom-house-joel-room-door-1']
        self.assertAlmostEqual(locator['position'][0], 10.10388, places=4)
        self.assertNotEqual(locator['position'], by_name['ss-hom-house-push-door-1']['position'])
        self.assertAlmostEqual(next(p['value'] for p in bedroom['properties'] if p['key']=='0xa7527a3b'), .6, places=6)

    def test_hand_targets_and_paired_rig_identity(self):
        folder = ROOT/'actor50'
        rig = folder/'door-l-skel-realskel-tstrm.pak'
        anchors = rig_anchors(rig)['anchors']
        self.assertEqual({a['name'] for a in anchors}, {'handle_ik_l_pull', 'handle_ik_l_push'})
        pair = paired_clips(folder/'anim-sarah-player-tstrm.pak', folder/'sarah-skel-tstrm.pak', rig,
                            'sar-p-open-pull-l--sarah', 'sar-p-open-pull-l--door')
        self.assertEqual([c['rig_id'] for c in pair['clips']], ['0xc203141a','0xa2e614f5'])
        self.assertAlmostEqual(pair['clips'][0]['duration'], pair['clips'][1]['duration'])

    def test_references_use_native_crc_and_byte_offsets(self):
        data = bytes.fromhex('1142154c000000001142154c')
        ref = symbol_references(data, ['ap-hom-house-joel-room-door-1'])[0]
        self.assertEqual(ref['offsets'], [0, 8])
        self.assertEqual(ref['symbol_id'], '0x4c154211')

    def test_native_entry_offsets_and_inverse_composition(self):
        import numpy as np
        from tools.export_vita_character import compose_transform
        from tlou_extractor.door_interaction_data import compose_rigid
        folder = ROOT/'actor50'
        for bank, rig, char_name, door_name, expected in [
            ('anim-sarah-player', 'door-l', 'sar-p-open-pull-l--sarah', 'sar-p-open-pull-l--door',
             [.67808259, -.032, .65262097]),
            ('hom1', 'door-r', 'hom1-house-door-push--sarah', 'hom1-house-door-push--door',
             [-.48254442, -.033599, .25468656])]:
            pair = paired_clips(folder/(bank+'-tstrm.pak'), folder/'sarah-skel-tstrm.pak',
                folder/(rig+'-skel-realskel-tstrm.pak'), char_name, door_name)
            entry = pair['clips'][0]['animation_entry']
            np.testing.assert_allclose(entry['relative_to_shared_locator']['position'], expected, atol=1e-7)
            ap = entry['ap_reference']; inv = entry['relative_to_shared_locator']
            matrix = compose_transform(ap['position'],ap['rotation_xyzw'],[1,1,1])
            inverse = compose_transform(inv['position'],inv['rotation_xyzw'],[1,1,1])
            np.testing.assert_allclose(matrix @ inverse, np.eye(4), atol=1e-12)

    def test_pull_alignment_brings_hand_to_native_handle(self):
        import numpy as np
        from tools.export_vita_character import compose_transform
        from tlou_extractor.skeleton_reader import SkeletonReader
        folder = ROOT/'actor50'
        pair = paired_clips(folder/'anim-sarah-player-tstrm.pak', folder/'sarah-skel-tstrm.pak',
            folder/'door-l-skel-realskel-tstrm.pak','sar-p-open-pull-l--sarah','sar-p-open-pull-l--door')
        samples = []
        for clip, rig, target in zip(pair['clips'], ['sarah', 'door-l-skel-real'],
                                    ['l_hand_prop_attachment','handle_ik_l_pull']):
            path = folder/('sarah-skel-tstrm.pak' if rig=='sarah' else 'door-l-skel-realskel-tstrm.pak')
            skeleton = SkeletonReader.read_skeleton(PakFile(str(path)))
            values = {(t['bone'],t['path']):t['values'][9] for t in clip['tracks']}
            world = {}
            def calculate(index):
                if index not in world:
                    bone=skeleton.bones[index]
                    local=compose_transform(values.get((bone.name,'translation'),bone.translation),
                        values.get((bone.name,'rotation'),bone.rotation),values.get((bone.name,'scale'),bone.scale))
                    world[index]=calculate(bone.parent_index)@local if bone.parent_index>=0 else local
                return world[index]
            samples.append(calculate(skeleton.bone_by_name[target].index)[:3,3])
        relative=pair['character_relative_to_door_actor']
        matrix=compose_transform(relative['position'],relative['rotation_xyzw'],[1,1,1])
        aligned=(matrix @ np.append(samples[0],1))[:3]
        self.assertGreater(np.linalg.norm(samples[0]-samples[1]), .5)
        self.assertLess(np.linalg.norm(aligned-samples[1]), .08)
