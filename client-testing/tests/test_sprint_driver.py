import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sprint_driver import SprintDriver, sprint_scope
from ashes_testing.telemetry import Unavailable


class SprintDriverGuards(unittest.TestCase):
    def test_unreserved_or_wrong_scope_or_key_refused(self):
        base = {'test_phase': 'sprint-comparison', 'allowed_keys': ['lshift', 'w'],
                'remaining_pulses': 0, 'pulse_reserved_at': 123, 'max_key_seconds': 1}
        sprint_scope(base, ('lshift', 'w'), .5)
        for field, value in (('remaining_pulses', 1), ('allowed_keys', ['w']),
                             ('test_phase', 'ui-entry'), ('max_key_seconds', .1)):
            with self.subTest(field=field), self.assertRaises(Unavailable):
                sprint_scope({**base, field: value}, ('lshift', 'w'), .5)
        with self.assertRaises(Unavailable):
            sprint_scope(base, ('lshift', 'space'), .5)

    def test_partial_release_failure_still_releases_other_key_and_deactivates(self):
        driver = object.__new__(SprintDriver)
        driver.lock = threading.RLock()
        driver.virtual_held = ['lshift', 'w']
        driver.adapter = Mock()
        driver.adapter.set_key.side_effect = [RuntimeError('W pipe failure'), None]
        driver._post = Mock()
        with patch('sprint_driver.AttachedWindowsDriver.release_all') as final:
            with self.assertRaises(RuntimeError):
                driver.release_all()
            final.assert_called_once()
        self.assertEqual([c.args for c in driver.adapter.set_key.call_args_list], [(0x57, False), (0xA0, False)])
        self.assertEqual(driver.virtual_held, [])


if __name__ == '__main__':
    unittest.main()
