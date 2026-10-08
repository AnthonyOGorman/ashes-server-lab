import copy
import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stationary_jump import jump_guard, fixed_profile_guard
from ashes_testing.telemetry import Unavailable


class JumpGuards(unittest.TestCase):
    def setUp(self):
        cert = json.loads((Path(__file__).resolve().parents[1] /
                          'runs/resume-readiness-6c44f696a2df4a1b9207f049ced8fdb5.json').read_text())
        self.before = cert['native_final']
        self.sample = copy.deepcopy(self.before)
        self.sample['observed_at'] = time.time()
        self.counter = {'counter': 0, 'observed_at': time.time(), 'controller': self.sample['controller']}

    def test_airborne_falling_with_no_cached_floor_is_allowed(self):
        self.sample['movement']['MovementMode'] = 3
        self.sample['position_cm'][2] += 50
        self.sample['movement']['Velocity'][2] = 400
        self.sample['floor'] = {'status': 'unavailable'}
        jump_guard(self.before, self.sample, self.counter)
        with self.assertRaises(Unavailable):
            jump_guard(self.before, self.sample, self.counter, stationary=True)

    def test_relock_or_old_counter_refused(self):
        for value in ('locked', 'stale'):
            c = copy.deepcopy(self.counter)
            if value == 'locked':
                c['counter'] = 1
            else:
                c['observed_at'] -= 1
            with self.subTest(value=value), self.assertRaises(Unavailable):
                jump_guard(self.before, self.sample, c)

    def test_reused_component_controller_and_world_refused(self):
        for key in ('pawn', 'movement_component', 'controller', 'world'):
            s = copy.deepcopy(self.sample)
            target = s[key]['identity'] if key == 'world' else s[key]
            target['serial'] += 1
            with self.subTest(key=key), self.assertRaises(Unavailable):
                jump_guard(self.before, s, self.counter)

    def test_fall_horizontal_drift_or_nonfinite_refused(self):
        for axis, value in ((2, -51), (2, 601), (0, 6), (2, float('nan'))):
            s = copy.deepcopy(self.sample)
            s['position_cm'][axis] += value
            with self.subTest(value=value), self.assertRaises(Unavailable):
                jump_guard(self.before, s, self.counter)

    def test_changed_playerstate_and_penetration_refused(self):
        for kind in ('playerstate', 'penetration'):
            s = copy.deepcopy(self.sample)
            if kind == 'playerstate':
                s['pawn_player_state']['address'] = '0xBAD'
            else:
                s['floor']['hit']['bStartPenetrating'] = True
            with self.subTest(kind=kind), self.assertRaises(Unavailable):
                jump_guard(self.before, s, self.counter)


class FixedGravityProfileGuards(unittest.TestCase):
    def test_old_gravity_or_missing_provenance_refused(self):
        profile = {'effective_gravity': -1225., 'jump_velocity': 900., 'world_gravity': -980.,
                   'movement_gravity_scale': 2.5, 'character_gravity_scale': .5, 'slow_falling': False,
                   'animation_modifiers': 0, 'source': 'current native getter bindings, reflected settings and accepted stat cache'}
        fixed_profile_guard({'movement_comparison': {'falling_profile': profile}})
        for key, value in (('effective_gravity', -2450), ('character_gravity_scale', 1), ('source', 'guess'), ('slow_falling', True)):
            with self.subTest(key=key), self.assertRaises(Unavailable):
                fixed_profile_guard({'movement_comparison': {'falling_profile': {**profile, key: value}}})


if __name__ == '__main__':
    unittest.main()
