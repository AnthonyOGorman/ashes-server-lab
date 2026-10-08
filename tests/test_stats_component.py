import json
from pathlib import Path
import unittest
from lab.stats_component import encode_stat_array, validate_gravity_update


class StatsWireTests(unittest.TestCase):
    def test_native_codec_matches_independent_captured_array(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/captured_gravity_stats_array.json').read_text())
        items = []
        for row in fixture['items']:
            item = dict(replication_id=row['replication_id'], record=int(row['record'], 16),
                        value_bits=int(row['value_bits'], 16))
            if row['conditional_base_equipment']:
                item['extra'] = (int(row['base_bits'], 16), int(row['equipment_bits'], 16))
            items.append(item)
        raw, bits = encode_stat_array(fixture['array_key'], fixture['base_key'], items)
        self.assertEqual(bits, fixture['payload_bits'])
        self.assertEqual(raw.hex(), fixture['payload_hex'])

    def test_rejects_update_before_component_guid_acceptance(self):
        with self.assertRaisesRegex(ValueError, 'accepted'):
            validate_gravity_update({'functions_invoked': False, 'accepted_component_guids': []}, {}, {})


if __name__ == '__main__':
    unittest.main()
