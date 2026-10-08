from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import initialize_joined_character as initializer


class StatsInitializationWaitTests(unittest.TestCase):
    def test_null_delegate_is_rechecked_until_native_initialization_finishes(self):
        ready={'delegate_wrapper':'0x1234'}
        with patch.object(initializer,'inspect_mapping',side_effect=[{'delegate_wrapper':'0x0'},ready]) as inspect:
            with patch.object(initializer.time,'sleep') as sleep:
                self.assertIs(initializer.wait_stats_delegate(1,'actors','receiver'),ready)
        self.assertEqual(inspect.call_count,2);sleep.assert_called_once_with(.1)

    def test_timeout_cannot_authorize_uninitialized_stat_update(self):
        clock=[0.]
        def sleep(seconds):clock[0]+=seconds
        with patch.object(initializer,'inspect_mapping',return_value={'delegate_wrapper':'0x0'}):
            with patch.object(initializer.time,'monotonic',side_effect=lambda:clock[0]):
                with patch.object(initializer.time,'sleep',side_effect=sleep):
                    with self.assertRaisesRegex(ValueError,'did not initialize'):
                        initializer.wait_stats_delegate(1,'actors','receiver',timeout=.2)
