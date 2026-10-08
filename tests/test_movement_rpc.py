import json
from pathlib import Path
import unittest

from lab.movement_rpc import decode_pawn_movement_rpc
from lab.unreal import DecodeError, Connection, WorldProtocol


class MovementRPCEnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = json.loads((Path(__file__).resolve().parents[1] / "evidence" /
                                  "captured_movement_rpc_envelopes.json").read_text())

    def test_real_client_move_preserves_every_opaque_argument_bit(self):
        samples = [x for x in self.capture["samples"] if x["field_index"] == 44]
        self.assertTrue(samples)
        for sample in samples:
            parsed = decode_pawn_movement_rpc(bytes.fromhex(sample["payload_hex"]),
                                             sample["payload_bits"], "client")
            field = parsed["fields"][0]
            self.assertEqual(field["rpc"], "ServerMovePacked")
            self.assertEqual(field["argument_bits"], sample["argument_bits"])
            self.assertEqual(field["argument_hex"], sample["argument_hex"])
            self.assertFalse(field["packed_data_decoded"])
            self.assertFalse(parsed["movement_proved"])

    def test_real_server_response_and_wrong_direction(self):
        for sample in self.capture["response_samples"]:
            data = bytes.fromhex(sample["payload_hex"])
            parsed = decode_pawn_movement_rpc(data, sample["payload_bits"], "server")
            self.assertEqual(parsed["fields"][0]["rpc"], "ClientMoveResponsePacked")
            self.assertEqual(parsed["fields"][0]["argument_bits"], 42)
            with self.assertRaises(DecodeError):
                decode_pawn_movement_rpc(data, sample["payload_bits"], "client")

    def test_truncated_and_appended_real_wire_payloads_rejected(self):
        sample = self.capture["response_samples"][0]
        data, bits = bytes.fromhex(sample["payload_hex"]), sample["payload_bits"]
        for altered_bits in (bits - 1, bits + 1):
            with self.assertRaises(DecodeError):
                decode_pawn_movement_rpc(data, altered_bits, "server")
        with self.assertRaises(DecodeError):
            decode_pawn_movement_rpc(data[:-1], bits, "server")

    def test_real_unrelated_pawn_rpc_does_not_become_movement(self):
        sample = self.capture["samples"][0]
        self.assertNotIn(sample["field_index"], (35, 44, 76))
        with self.assertRaises(DecodeError):
            decode_pawn_movement_rpc(bytes.fromhex(sample["payload_hex"]),
                                     sample["payload_bits"], sample["direction"])

    def test_live_observer_requires_connection_contract_and_never_claims_walking(self):
        sample = next(x for x in self.capture['samples'] if x['field_index'] == 44)
        bunch = {'channel': 9, 'payload_hex': sample['payload_hex'], 'payload_bits': sample['payload_bits'], 'reliable': False}
        recorded = []
        protocol = WorldProtocol(event=lambda kind, detail: recorded.append((kind, detail)))
        connection = Connection(b'\x00'*20, 0, 0, 0, 0, 0, 0)
        connection.phase = 'joined'
        connection.possession_acknowledged = True
        connection.actor_guids = {'pawn': {'object_id':'0x1234', 'server_id':1, 'randomizer':2}}
        self.assertFalse(protocol._observe_pawn_movement_rpc(connection, bunch, ('127.0.0.1', 1)))
        connection.pawn_movement_contract = {'pawn_guid': dict(connection.actor_guids['pawn']), 'field_max':198, 'server_move_field':44, 'cache_snapshot':'current'}
        for flag in ('partial','exports','must_map','open','close'):
            self.assertFalse(protocol._observe_pawn_movement_rpc(connection, {**bunch, flag:True}, ('127.0.0.1', 1)))
        self.assertTrue(protocol._observe_pawn_movement_rpc(connection, bunch, ('127.0.0.1', 1)))
        self.assertEqual(recorded[0][0], 'pawn_movement_rpc_observed')
        self.assertFalse(recorded[0][1]['movement_proved'])
        field = recorded[0][1]['fields'][0]
        self.assertTrue(field['packed_data_decoded'])
        self.assertEqual(field['movement']['moves'][0]['client_location'],
                         [-660391.25, 389341.78, 13622.93])
        self.assertFalse(field['movement']['movement_proved'])
        connection.phase = 'closed'
        self.assertFalse(protocol._observe_pawn_movement_rpc(connection, bunch, ('127.0.0.1', 1)))


if __name__ == "__main__":
    unittest.main()
