import copy
import json
import math
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ashes_testing.bridge import Bridge, InputGate, bounded_duration, displacement
from ashes_testing.telemetry import Unavailable

PROOF = {'pid': 42, 'exe': 'game', 'sha256': 'hash', 'process_created_filetime': 100}


def sample(x=0, z=0):
    return {'client_proof': dict(PROOF), 'pawn': {'serial': 10}, 'root': {'serial': 11},
            'movement_component': {'serial': 12}, 'position_cm': [x, 0, z], 'world': {}, 'observed_at': time.time()}


class Native:
    def __init__(self):
        self.x, self.z = 0, 0
    def proof(self):
        return dict(PROOF)
    def sample(self):
        return sample(self.x, self.z)


class Server:
    def get(self, kind):
        return {'data': [], 'source': 'server_observation'}


class Driver:
    last_input_proof = {'desktop_focus_unchanged': True}
    def __init__(self, native, failure=False):
        self.native, self.released, self.failure = native, False, failure
    def key(self, key, duration, cancel):
        if self.failure:
            raise RuntimeError('Disconnected input IPC')
        self.native.x += 10
    def release_all(self):
        self.released = True
    def screenshot(self, path):
        path.write_bytes(b'fixture')
        return {'path': str(path), 'pid': 42}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lease = self.root / 'lease.json'
        self.grant()
        self.native = Native()
        self.drivers = []
        def factory(pid, attached):
            d = Driver(self.native)
            self.drivers.append(d)
            return d
        self.bridge = Bridge(native=self.native, server=Server(), output=self.root / 'runs',
                             driver_factory=factory, gate=InputGate(True, self.lease))

    def grant(self, **overrides):
        value = {'mode': 'client-testing-exclusive', 'coordinated_window': True,
                 'owner_thread': '01a116ae-2ec4-7de0-b563-31251b0c4533',
                 'expires_at': time.time() + 60, **PROOF, **overrides}
        self.lease.write_text(json.dumps(value))

    def test_readonly_default_refuses_input(self):
        self.bridge.gate.enabled = False
        with self.assertRaises(Unavailable):
            self.bridge.press_key('w')
        self.assertEqual(self.drivers, [])

    def test_gate_requires_matching_lifetime(self):
        self.grant(process_created_filetime=101)
        with self.assertRaises(Unavailable):
            self.bridge.press_key('w')

    def test_expired_window_refuses(self):
        self.grant(expires_at=time.time() - 1)
        with self.assertRaises(Unavailable):
            self.bridge.press_key('w')

    def test_other_owner_refuses(self):
        self.grant(owner_thread='other')
        with self.assertRaises(Unavailable):
            self.bridge.press_key('w')

    def test_uncoordinated_window_refuses(self):
        self.grant(coordinated_window=False)
        with self.assertRaises(Unavailable):
            self.bridge.press_key('w')

    def test_input_cleanup_and_evidence(self):
        result = self.bridge.press_key('w', .1)
        self.assertTrue(self.drivers[-1].released)
        self.assertEqual(result['comparison']['horizontal_cm'], 10)
        self.assertTrue(Path(result['evidence_path']).exists())

    def test_failed_input_cleans_up(self):
        d = Driver(self.native, failure=True)
        self.bridge.driver_factory = lambda *args: d
        with self.assertRaises(RuntimeError):
            self.bridge.press_key('w', .1)
        self.assertTrue(d.released)
        self.assertEqual(len(list((self.root / 'runs').glob('input-error*.json'))), 1)

    def test_nonfinite_and_excessive_duration_refused(self):
        for duration in [True, math.nan, math.inf, 0, -1, 3, '1']:
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                bounded_duration(duration)

    def test_unavailable_keys_refused(self):
        for key in ['shift', 'enter', 'escape', 'F8', '..']:
            with self.assertRaises(ValueError):
                self.bridge.press_key(key)
        self.assertEqual(self.drivers, [])

    def test_pawn_or_component_swap_refuses_comparison(self):
        for key in ['pawn', 'root', 'movement_component']:
            after = sample(10)
            after[key]['serial'] += 1
            with self.assertRaises(Unavailable):
                displacement(sample(), after)

    def test_pid_reuse_refuses_comparison(self):
        after = sample(10)
        after['client_proof']['process_created_filetime'] += 1
        with self.assertRaises(Unavailable):
            displacement(sample(), after)

    def test_vertical_only_motion_does_not_pass(self):
        self.bridge._press = lambda **kwargs: setattr(self.native, 'z', self.native.z + 20) or {}
        result = self.bridge.run_scenario([{'key': 'w', 'duration': .1}])
        self.assertEqual(result['status'], 'failed')

    def test_scenario_produces_screenshots_and_assertions(self):
        result = self.bridge.run_scenario([{'key': 'w', 'duration': .1}])
        self.assertEqual(result['status'], 'passed')
        self.assertTrue(Path(result['before']['path']).exists())
        self.assertTrue(Path(result['after']['path']).exists())

    def test_scenario_budget_and_schema(self):
        for steps in [[], [{'key': 'w', 'duration': .1, 'address': 123}],
                      [{'key': 'w', 'duration': 2}] * 6]:
            with self.assertRaises(ValueError):
                self.bridge.run_scenario(steps)
        self.assertEqual(self.drivers, [])

    def test_lease_revoked_between_steps(self):
        press = self.bridge._press
        def wrapped(**kwargs):
            result = press(**kwargs)
            self.grant(coordinated_window=False)
            return result
        self.bridge._press = wrapped
        result = self.bridge.run_scenario([{'key': 'w', 'duration': .1}] * 2)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(len(result['steps']), 1)

    def test_cancel_signal(self):
        self.bridge.cancel_test()
        self.assertTrue(self.bridge.cancel.is_set())

    def test_cancelled_queued_request_never_sends_input(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Unavailable):
            self.bridge.press_key('w', .1, cancel=cancel)
        self.assertEqual(self.drivers, [])

    def test_capture_does_not_require_input_window(self):
        self.bridge.gate.enabled = False
        self.assertTrue(Path(self.bridge.capture_screen()['path']).exists())


    def test_ui_only_window_refuses_movement_before_driver(self):
        self.grant(allowed_actions=['adapter-setup', 'ui-entry'])
        with self.assertRaises(Unavailable):
            self.bridge.press_key('w', .5)
        self.assertEqual(self.drivers, [])

    def test_ui_only_window_accepts_ui_gate(self):
        self.grant(allowed_actions=['adapter-setup', 'ui-entry'])
        self.bridge.gate.verify(PROOF, action='ui-entry')

    def test_forward_only_window_refuses_other_keys(self):
        self.grant(allowed_actions=['movement'], allowed_keys=['w'])
        for key in ('a', 's', 'd', 'space'):
            with self.assertRaises(Unavailable):
                self.bridge.press_key(key, .1)
        self.assertEqual(self.drivers, [])

    def test_scoped_duration_and_reserved_pulse_refuse_before_driver(self):
        self.grant(max_key_seconds=.5)
        with self.assertRaises(Unavailable):
            self.bridge.press_key('w', 1)
        self.grant(remaining_pulses=0)
        with self.assertRaises(Unavailable):
            self.bridge.press_key('w', .1)
        self.assertEqual(self.drivers, [])


if __name__ == '__main__':
    unittest.main()
