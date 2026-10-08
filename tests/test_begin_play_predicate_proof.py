"""Negative coverage for read-only driver predicate inference; no live inputs."""
import sys
import copy
import json
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inspect_begin_play_serialization import infer_driver_is_server
from lab.game_state_begin_play import _validate_reviewed_override


class DriverPredicateInferenceTests(unittest.TestCase):
    leaf = bytes.fromhex('48 83 b9 38 01 00 00 00 0f 94 c0 c3')

    def test_nonnull_server_connection_proves_false_for_exact_leaf(self):
        self.assertIs(infer_driver_is_server(self.leaf, 0x100000), False)
        self.assertIs(infer_driver_is_server(b'\x33\xc0'+self.leaf, 0x100000), False)

    def test_null_connection_is_server_and_cannot_prove_client_branch(self):
        self.assertIs(infer_driver_is_server(self.leaf, 0), True)

    def test_wrong_offset_condition_and_truncated_code_are_unknown(self):
        for code in (self.leaf[:8], self.leaf.replace(b'\x38', b'\x40', 1),
                     self.leaf.replace(b'\x94', b'\x95', 1), b'\xe9\x00\x00\x00\x00', b''):
            self.assertIsNone(infer_driver_is_server(code, 0x100000))


class ReviewedOverrideGuardTests(unittest.TestCase):
    def fixture(self):
        return json.loads((Path(__file__).resolve().parents[1]/'evidence'/
            'begin_play_override_guard_fixture_28500.json').read_text())

    def validate(self, data):
        _validate_reviewed_override(data['serializer'], data['lifecycle'],
            data['lifecycle']['game_state']['identity'], data['actors'])

    def test_historical_fixture_with_synthetic_chain_fields_passes_offline(self):
        self.validate(self.fixture())

    def test_unknown_or_misbound_predicates_are_refused(self):
        mutations = {
            'unknown_predicate': lambda p,d: p.update(status='unverified_driver_virtual'),
            'missing_chain_code': lambda p,d: p['reviewed_code_ranges'].pop('0x41861f0'),
            'wrong_actor': lambda p,d: p['actor'].update(address='0x1234'),
            'wrong_world': lambda p,d: p['world'].update(address='0x1234'),
            'wrong_level': lambda p,d: p['owning_level'].update(address='0x1234'),
            'wrong_driver': lambda p,d: p['driver'].update(address='0x1234'),
            'wrong_connection': lambda p,d: p['driver_server_connection'].update(address='0x1234'),
            'server_leaf': lambda p,d: p['driver_virtual_4b0'].update(inferred_return=True),
            'unknown_driver_virtual': lambda p,d: p['driver_virtual_4b0'].update(rva='0x423d730'),
            'wrong_leaf_field': lambda p,d: p['driver_virtual_4b0'].update(code_hex='4883b940010000000f94c0c3'),
            'wrong_name': lambda p,d: p['net_driver_name'].update(number=1),
            'wrong_builtin': lambda p,d: p['net_driver_name'].update(builtin_11a_index=12),
            'wrong_settings_outer': lambda p,d: p['world_settings'].update(outer_address='0x1234'),
            'wrong_callback': lambda p,d: p['world_settings_callbacks']['0x870'].update(rva='0x47bb140'),
            'wrong_callback_code': lambda p,d: p['world_settings_callbacks']['0x878'].update(code_prefix_hex='c3'),
            'different_process': lambda p,d: d['actors']['client_proof'].update(process_created_filetime=1),
            'wrong_driver_guid_cache': lambda p,d: d['actors']['net_drivers'][0].update(guid_cache='0x1234'),
            'missing_actors': lambda p,d: d.update(actors={}),
        }
        for name, mutate in mutations.items():
            data = copy.deepcopy(self.fixture())
            mutate(data['serializer']['game_specific_predicate'], data)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.validate(data)


if __name__ == '__main__':
    unittest.main()
