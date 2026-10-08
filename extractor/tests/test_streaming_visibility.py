import unittest
from pathlib import Path

from research.streaming.visibility_base import (
    COMMON_DISPLAY_KEY, build, evaluate_selector, select_levels, string_id,
)


def prop(key, value):
    return {'key_raw': f'0x{key:08x}', 'value_type': 3, 'value': value}


class TestVisibilitySelection(unittest.TestCase):
    def test_native_hash_evidence(self):
        self.assertEqual(string_id('regionshape-4746'), 0x7ff6d6ae)
        self.assertEqual(string_id('regionshape-4747'), 0x7b37cb19)
        self.assertEqual(string_id('level-1'), 0xdf0bad70)
        self.assertEqual(string_id('level-no-display-1'), 0xb7747086)

    def test_hidden_duplicate_wins_in_both_orders(self):
        rows = [prop(COMMON_DISPLAY_KEY, 'a'), prop(string_id('level-no-display-2'), 'a')]
        for order in (rows, rows[::-1]):
            self.assertEqual(select_levels(order, 2), {'display': [], 'resident_only': ['a']})

    def test_state_gates_and_legacy_state_one(self):
        rows = [prop(string_id('level'), 'legacy'), prop(string_id('level-2'), 'second'),
                prop(COMMON_DISPLAY_KEY, 'common')]
        self.assertEqual(select_levels(rows, 1)['display'], ['legacy', 'common'])
        self.assertEqual(select_levels(rows, 2)['display'], ['second', 'common'])
        self.assertEqual(select_levels(rows, 0), {'display': [], 'resident_only': []})
        with self.assertRaises(ValueError):
            select_levels(rows, None)

    def test_real_house_lod_switch_remains_conditional(self):
        root = Path(__file__).resolve().parents[1] / 'research/streaming/output'
        source = Path(r'D:\TLOUPS4\Extracted\pak32\world-home-ingame14.pak')
        if not source.exists() or not (root / 'manifest_dependencies.json').exists():
            self.skipTest('Local game fixture absent')
        result = build(root / 'world-home-ingame14.json', root / 'manifest_dependencies.json')
        self.assertEqual(len(result['regions']), 15)
        self.assertEqual(sum(r['selector']['kind'] == 'constant' for r in result['regions']), 10)
        house = next(r for r in result['regions'] if r['name'] == 'regionshape-4747')
        self.assertEqual(house['selector']['kind'], 'script_requires_game_state')
        self.assertIn('hom-house-interior', house['sets']['1']['display'])
        self.assertIn('hom-house-interior-low', house['sets']['1']['resident_only'])
        self.assertNotIn('hom-house-interior', house['sets']['2']['display'])
        self.assertIn('hom-house-interior-low', house['sets']['2']['display'])
        # Real bytecode, controlled inputs: ensure all three return branches work.
        selector = house['selector']
        queries = {('call_script', '0x4d2bf414'): lambda *args: True}
        self.assertEqual(evaluate_selector(selector, queries), 1)
        queries[('call_script', '0x4d2bf414')] = lambda *args: False
        queries[('call_script', '0xf1360136')] = lambda *args: True
        self.assertEqual(evaluate_selector(selector, queries), 2)
        queries[('call_script', '0xf1360136')] = lambda *args: False
        queries[('call_native', '0xa93d2926')] = lambda *args: False
        self.assertEqual(evaluate_selector(selector, queries), 3)
        queries[('call_native', '0xa93d2926')] = lambda *args: True
        queries[('call_native', '0xf307e431')] = lambda *args: True
        self.assertEqual(evaluate_selector(selector, queries), 2)
        queries[('call_native', '0xf307e431')] = lambda *args: False
        self.assertEqual(evaluate_selector(selector, queries), 3)
        with self.assertRaisesRegex(ValueError, 'Unresolved game-state query'):
            evaluate_selector(selector, {})


if __name__ == '__main__':
    unittest.main()
