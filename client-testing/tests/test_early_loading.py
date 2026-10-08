import copy
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from early_w_loading import locked_idle, loading_connection
from ashes_testing.telemetry import Unavailable


class EarlyLoadingGuards(unittest.TestCase):
    def setUp(self):
        self.sample = {'pawn_state': {'Role': 1}, 'controller': {'address': '0x10000', 'serial': 9},
                       'observed_at': time.time(), 'movement': {'MovementMode': 3,
                       'Velocity': [0., 0., 0.], 'Acceleration': [0., 0., 0.]}}
        self.counter = {'counter': 1, 'controller': copy.deepcopy(self.sample['controller']),
                        'observed_at': time.time()}

    def test_role_becomes_autonomous(self):
        self.sample['pawn_state']['Role'] = 2
        with self.assertRaises(Unavailable):
            locked_idle(self.sample, self.counter)

    def test_counter_released(self):
        self.counter['counter'] = 0
        with self.assertRaises(Unavailable):
            locked_idle(self.sample, self.counter)

    def test_same_address_reused_serial(self):
        self.counter['controller']['serial'] = 10
        with self.assertRaises(Unavailable):
            locked_idle(self.sample, self.counter)

    def test_old_counter(self):
        self.counter['observed_at'] -= 1
        with self.assertRaises(Unavailable):
            locked_idle(self.sample, self.counter)

    def test_old_pawn(self):
        self.sample['observed_at'] -= 1
        with self.assertRaises(Unavailable):
            locked_idle(self.sample, self.counter)

    def test_nonfinite_or_moving_pawn(self):
        for velocity in (float('nan'), .2):
            with self.subTest(velocity=velocity):
                self.sample['movement']['Velocity'][0] = velocity
                with self.assertRaises(Unavailable):
                    locked_idle(self.sample, self.counter)

    def test_grounded_input_window_is_not_required_for_loading(self):
        locked_idle(self.sample, self.counter)

    def test_server_ready_or_duplicate_connection_refused(self):
        c = {'id': 'joined', 'phase': 'joined', 'possession': True,
             'selected_character_name': 'LabExplorer', 'stages': ['LoadingInputRelocked']}
        class Server:
            def get(self, kind):
                return {'data': self.data}
        class Bridge:
            server = Server()
        bridge = Bridge()
        for data in ([{**c, 'stages': c['stages'] + ['PawnAutonomous']}],
                     [{**c, 'stages': c['stages'] + ['WorldReady']}], [c, c]):
            bridge.server.data = data
            with self.subTest(data=data), self.assertRaises(Unavailable):
                loading_connection(bridge)


if __name__ == '__main__':
    unittest.main()
