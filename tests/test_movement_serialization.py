import json
from pathlib import Path
import unittest

from lab.movement_serialization import decode_move_response_argument, decode_server_move_argument
from lab.unreal import DecodeError

ROOT = Path(__file__).resolve().parents[1]


class ExactMovementSerializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = json.loads((ROOT/'evidence/captured_movement_rpc_envelopes.json').read_text())
        cls.live = json.loads((ROOT/'evidence/begin_play_packet_window_28500.json').read_text())['recognized'][0]['fields'][0]

    def test_captured_idle_move_fixtures_have_stable_world_position(self):
        timestamps = []
        for sample in self.capture['samples']:
            if sample['field_index'] != 44:
                continue
            decoded = decode_server_move_argument(bytes.fromhex(sample['argument_hex']),sample['argument_bits'])
            self.assertEqual(decoded['inner_bits'],168)
            self.assertEqual(len(decoded['moves']),1)
            move = decoded['moves'][0]
            self.assertEqual(move['client_location'],[-660391.25,389341.78,13622.93])
            self.assertEqual(move['acceleration'],[0,0,0])
            self.assertEqual(move['custom_axes'],[0,0])
            self.assertFalse(decoded['movement_proved'])
            timestamps.append(move['timestamp'])
        self.assertEqual(timestamps,sorted(timestamps))
        self.assertGreater(len(timestamps),1)

    def test_real_local_move_matches_independently_read_pawn_position(self):
        sample = self.live
        decoded = decode_server_move_argument(bytes.fromhex(sample['argument_hex']),sample['argument_bits'])
        move = decoded['moves'][0]
        self.assertEqual(move['client_location'],[-660384.0,389360.3,13622.9])
        self.assertEqual(move['acceleration'],[6741.4,-4654.3,0.0])
        self.assertEqual(move['movement_mode'],3)
        self.assertEqual(decoded['inner_bits'],235)
        self.assertFalse(decoded['movement_proved'])

    def test_real_acknowledgements_decode_monotonic_timestamps(self):
        timestamps = []
        for sample in self.capture['response_samples']:
            decoded = decode_move_response_argument(bytes.fromhex(sample['argument_hex']),sample['argument_bits'])
            self.assertTrue(decoded['acknowledgement'])
            timestamps.append(decoded['timestamp'])
            self.assertFalse(decoded['movement_proved'])
        self.assertEqual(timestamps,sorted(timestamps))
        self.assertAlmostEqual(timestamps[0],1.6231026649475098)

    def test_changed_length_and_truncated_arguments_are_refused(self):
        sample = self.live
        data = bytes.fromhex(sample['argument_hex'])
        for bits in [sample['argument_bits']-1,sample['argument_bits']+1]:
            with self.assertRaises(DecodeError):
                decode_server_move_argument(data,bits)
        with self.assertRaises(DecodeError):
            decode_server_move_argument(data[:-1],sample['argument_bits'])

    def test_correction_branch_is_never_mistaken_for_ack(self):
        sample = self.capture['response_samples'][0]
        data = bytearray.fromhex(sample['argument_hex'])
        # one presence bit + eight packed-count bits => ack is bit9
        data[1] &= ~2
        with self.assertRaises(DecodeError):
            decode_move_response_argument(bytes(data),sample['argument_bits'])

    def test_real_server_correction_retains_server_position_and_velocity(self):
        sample = json.loads((ROOT/'evidence/movement_correction_fixture_7820.json').read_text())
        decoded = decode_move_response_argument(bytes.fromhex(sample['argument_hex']),sample['argument_bits'])
        self.assertFalse(decoded['acknowledgement'])
        self.assertEqual(decoded['inner_bits'],435)
        self.assertEqual(decoded['timestamp'],41.632442474365234)
        correction = decoded['correction']
        self.assertEqual(correction['server_location'],[-660318.8867460706,390236.69319750246,13749.404648050135])
        self.assertEqual(correction['server_velocity'],[-204.59848856273317,564.0346301070583,436.20433807373047])
        self.assertEqual(correction['movement_mode'],3)
        self.assertFalse(decoded['movement_proved'])


if __name__ == '__main__':
    unittest.main()
