import json
from pathlib import Path
import unittest

from lab.movement_response import encode_move_ack_argument, encode_move_ack_content
from lab.movement_serialization import decode_move_response_argument


class MovementAcknowledgementTests(unittest.TestCase):
    def test_freshly_encoded_ack_matches_real_server_wire_fixtures(self):
        fixture = json.loads((Path(__file__).resolve().parents[1] /
            'evidence/captured_movement_rpc_envelopes.json').read_text())
        for sample in fixture['response_samples']:
            decoded = decode_move_response_argument(bytes.fromhex(sample['argument_hex']), sample['argument_bits'])
            argument, bits = encode_move_ack_argument(decoded['timestamp'])
            self.assertEqual((argument.hex(), bits), (sample['argument_hex'], sample['argument_bits']))
            payload, payload_bits = encode_move_ack_content(decoded['timestamp'])
            self.assertEqual((payload.hex(), payload_bits), (sample['payload_hex'], sample['payload_bits']))

    def test_invalid_timestamp_cannot_be_encoded(self):
        for timestamp in (True, None, '1', float('inf'), float('nan'), 1e100):
            with self.assertRaises(ValueError):
                encode_move_ack_argument(timestamp)


if __name__ == '__main__':
    unittest.main()
