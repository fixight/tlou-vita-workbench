import unittest
from tlou_extractor.cinematic_control import control_track

class ControlTrackTest(unittest.TestCase):
    def test_permissions_and_pose_ownership(self):
        track = control_track(30, [(0, 'full_cinematic'), (20, 'camera_only')])
        locked, look = track['events']
        self.assertFalse(locked['camera_look'])
        self.assertEqual(look['character_pose'], 'cinematic')
        self.assertFalse(look['movement'])
        self.assertTrue(look['camera_look'])
        self.assertEqual(track['on_exit'], 'restore_previous')
        self.assertEqual(track['source'], 'port_authored_not_recovered_script')
    def test_invalid_timeline_is_rejected(self):
        for changes in ([], [(1,'gameplay')], [(0,'unknown')],
                [(0,'gameplay'), (0,'camera_only')], [(0,'gameplay'), (30,'camera_only')]):
            with self.assertRaises(ValueError):
                control_track(30, changes)
    def test_edits_do_not_mutate_other_exports(self):
        first = control_track(1)
        first['events'][0]['movement'] = True
        self.assertFalse(control_track(1)['events'][0]['movement'])
