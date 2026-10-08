import copy
import sys
import unittest
import tempfile
import json
from unittest.mock import Mock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coordinated_traversal import native_guard, run
from ashes_testing.telemetry import Unavailable

SAMPLE = {'movement': {'MovementMode': 1, 'Velocity': [0, 0, 0], 'Acceleration': [0, 0, 0]},
          'pawn_state': {'Role': 2}, 'player_state': {'address': '0x1000'},
          'pawn_player_state': {'address': '0x1000'},
          'floor': {'status': 'read', 'fields': {'bBlockingHit': True, 'bWalkableFloor': True},
                    'hit': {'bStartPenetrating': False}, 'component': {'serial': 7}}}


class TraversalGuardTests(unittest.TestCase):
    def test_postready_control_reaches_current_state_without_historical_admission(self):
        bridge = Mock()
        bridge.native.proof.return_value = {'pid': 42, 'process_created_filetime': 84}
        bridge.gate.verify.return_value = {'remaining_pulses': 1, 'allowed_keys': ['w'],
                                          'test_phase': 'postready-loading-control'}
        bridge.server.get.side_effect = RuntimeError('current state reached')
        bridge.record.side_effect = lambda name, result: result
        with tempfile.TemporaryDirectory() as directory:
            bridge.gate.path = Path(directory) / 'lease.json'
            bridge.gate.path.write_text(json.dumps({'pid': 0}))
            with patch('coordinated_traversal.Bridge', return_value=bridge):
                result = run(42, 84, 'current', .5, postready_loading_control=True)
        self.assertEqual(result['error'], 'current state reached')
        self.assertFalse(result['movement_sent'])

    def test_falling_zero_velocity_refuses(self):
        sample = copy.deepcopy(SAMPLE)
        sample['movement']['MovementMode'] = 3
        with self.assertRaises(Unavailable):
            native_guard(sample)

    def test_penetrating_contact_refuses_during_pulse(self):
        sample = copy.deepcopy(SAMPLE)
        sample['floor']['hit']['bStartPenetrating'] = True
        with self.assertRaises(Unavailable):
            native_guard(sample)

    def test_missing_contact_or_motion_refuses_stationary_gate(self):
        for change in ('floor', 'velocity'):
            sample = copy.deepcopy(SAMPLE)
            if change == 'floor':
                sample['floor'] = {'status': 'unavailable'}
            else:
                sample['movement']['Velocity'][0] = 10
            with self.subTest(change=change), self.assertRaises(Unavailable):
                native_guard(sample, stationary=True)

    def test_playerstate_mismatch_refuses(self):
        sample = copy.deepcopy(SAMPLE)
        sample['pawn_player_state']['address'] = '0x2000'
        with self.assertRaises(Unavailable):
            native_guard(sample)


if __name__ == '__main__':
    unittest.main()
