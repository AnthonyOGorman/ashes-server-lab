import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ashes_testing.floor import outer_identity, weak_component
from ashes_testing.telemetry import Unavailable


def fixture(index=5, serial=7, current_serial=7, flags=0, pointer=0x3000, kind='Package'):
    item = bytearray(24)
    struct.pack_into('<QI', item, 0, pointer, flags)
    struct.pack_into('<i', item, 16, current_serial)

    class Reader:
        def unpack(self, address, fmt):
            if fmt == '<ii':
                return index, serial
            return (0x2000,)
        def read(self, address, size):
            return bytes(item)

    identity = {'address': hex(pointer), 'object_index': index, 'class': kind, 'name': 'fixture'}
    probe = SimpleNamespace(reader=Reader(), reflection=SimpleNamespace(count=100, chunks=0x1000, cache={}),
                            identity=lambda address: identity)
    return probe, {**identity, 'serial': current_serial}


class FloorIdentityTests(unittest.TestCase):
    def test_weak_reuse_refused_before_resolving(self):
        probe, _ = fixture(current_serial=8)
        with patch('ashes_testing.floor.NativeTelemetry.identity') as identity:
            with self.assertRaises(Unavailable):
                weak_component(probe, 0x4000)
            identity.assert_not_called()

    def test_invalid_index_or_serial_refused(self):
        for kwargs in ({'index': -2}, {'index': 100}, {'serial': -1}):
            probe, _ = fixture(**kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(Unavailable):
                weak_component(probe, 0x4000)

    def test_destroyed_or_missing_component_refused(self):
        for kwargs in ({'flags': 0x10000000}, {'flags': 0x200000}, {'pointer': 0}):
            probe, _ = fixture(**kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(Unavailable):
                weak_component(probe, 0x4000)

    def test_valid_component_preserves_weak_serial(self):
        probe, live = fixture(kind='PrimitiveComponent')
        with patch('ashes_testing.floor.NativeTelemetry.identity', return_value=live) as identity:
            self.assertEqual(weak_component(probe, 0x4000), live)
            identity.assert_called_once_with(probe, 0x3000, 'PrimitiveComponent')

    def test_package_without_allocated_serial_is_explicitly_labeled(self):
        probe, _ = fixture(current_serial=0)
        result = outer_identity(probe, 0x3000)
        self.assertIsNone(result['serial'])
        self.assertIn('package weak serial', result['identity_check'])

    def test_package_pointer_mismatch_or_destroyed_refused(self):
        for kwargs in ({'pointer': 0x5000}, {'flags': 0x10000000}):
            probe, _ = fixture(**kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(Unavailable):
                outer_identity(probe, 0x3000)

    def test_actor_never_uses_package_serial_exception(self):
        probe, _ = fixture(kind='Actor', current_serial=0)
        with patch('ashes_testing.floor.NativeTelemetry.identity', side_effect=Unavailable('serial absent')):
            with self.assertRaises(Unavailable):
                outer_identity(probe, 0x3000)


if __name__ == '__main__':
    unittest.main()
