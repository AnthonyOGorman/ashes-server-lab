import json
from pathlib import Path
import unittest

from lab.unreal import BitReader, decode_packet, encode_packet
from lab.world_bootstrap import (decode_exports, decode_actor_prefix,
                                 decode_actor_location, experimental_scene_bunches,
                                 encode_actor_rpc_content, decode_actor_rpc_content,
                                 NetGUID, encode_rpc_object_argument, decode_rpc_object_argument,
                                 experimental_controller_bunches)
from lab.world_bootstrap import experimental_hud_bunches


class WorldBootstrapTests(unittest.TestCase):
    def test_authored_hud_export_and_rpc_match_independent_capture_grammar(self):
        root = Path(__file__).resolve().parents[1]
        fixture = json.loads((root/"evidence/world_bootstrap_capture.json").read_text())
        row = next(row for row in fixture["evidence"] if row["frame"] == 3710)
        original = decode_packet(bytes.fromhex(row["udp_hex"]), "server")["bunches"]
        authored = experimental_hud_bunches(534, 53, 1032)
        for fresh, captured in zip(authored, original[2:]):
            self.assertEqual(fresh["payload_bits"], captured["payload_bits"])
            self.assertEqual(fresh["payload"].hex(), captured["payload_hex"])
            self.assertEqual(fresh["partial_flags"], captured["partial_flags"])
            self.assertEqual(fresh["reliable_sequence"], captured["reliable_sequence"])
        packet = encode_packet(0, 1, 7700, 11595, [31], info=0, bunches=experimental_hud_bunches(1023, 53, 1032))
        decoded = decode_packet(packet, "server")
        self.assertNotIn("error", decoded)
        self.assertEqual([b["reliable_sequence"] for b in decoded["bunches"]], [0, 1])
        export = decode_exports(bytes.fromhex(decoded["bunches"][0]["payload_hex"]), decoded["bunches"][0]["payload_bits"])
        hud = export["objects"][0]
        self.assertEqual(hud["path"], "BP_AOCHUD_C")
        self.assertEqual(hud["checksum"], 0xac6f1251)
        rpc = decoded["bunches"][1]
        field = decode_actor_rpc_content(bytes.fromhex(rpc["payload_hex"]), rpc["payload_bits"], 1032)["fields"][0]
        self.assertEqual(field["field_index"], 53)
        argument = decode_rpc_object_argument(bytes.fromhex(field["argument_hex"]), field["argument_bits"])
        self.assertEqual(argument.as_dict(), hud["guid"])
    def test_object_rpc_argument_preserves_full_custom_guid_and_presence(self):
        guid = NetGUID(0x123456789ABCDEF0, 1, 0x89ABCDEF)
        payload, bits = encode_rpc_object_argument(guid)
        self.assertEqual(bits, 129)
        reader = BitReader(payload, bits)
        self.assertEqual(reader.read(1), 1)
        self.assertEqual(reader.read(64), guid.object_id)
        self.assertEqual(reader.read(32), guid.server_id)
        self.assertEqual(reader.read(32), guid.randomizer)
        self.assertEqual(decode_rpc_object_argument(payload, bits), guid)
        empty, empty_bits = encode_rpc_object_argument(None)
        self.assertEqual((empty, empty_bits), (b"\x00", 1))
        self.assertIsNone(decode_rpc_object_argument(empty, empty_bits))
        with self.assertRaises(ValueError):
            decode_rpc_object_argument(payload, bits-1)

    def test_actual_live_possession_request_and_acknowledgement_match_guid(self):
        path = Path(__file__).resolve().parents[1]/"evidence/live_possession_packets_29312.json"
        capture = json.loads(path.read_text(encoding="utf-8"))
        observed = []
        for packet, expected_index in zip(capture["packets"], (45, 73)):
            parsed = decode_packet(bytes.fromhex(packet["hex"]), "server" if packet["direction"] == "S2C" else "client")
            bunch = parsed["bunches"][0]
            self.assertEqual(bunch["channel"], 3)
            content = decode_actor_rpc_content(bytes.fromhex(bunch["payload_hex"]), bunch["payload_bits"], capture["class_field_max"])
            self.assertEqual(len(content["fields"]), 1)
            field = content["fields"][0]
            self.assertEqual(field["field_index"], expected_index)
            self.assertEqual(field["argument_bits"], 129)
            guid = decode_rpc_object_argument(bytes.fromhex(field["argument_hex"]), field["argument_bits"])
            self.assertEqual(guid.as_dict(), capture["pawn_guid"])
            observed.append(guid)
        self.assertEqual(observed[0], observed[1])

    @classmethod
    def setUpClass(cls):
        report = json.loads((Path(__file__).resolve().parents[1]/"evidence"/"world_bootstrap_capture.json").read_text(encoding="utf-8"))
        cls.capture = {r["frame"]: r for r in report["evidence"]}

    def test_real_first_controller_export_consumes_every_bit(self):
        decoded = decode_packet(bytes.fromhex(self.capture[3710]["udp_hex"]), "server")
        first = decoded["bunches"][0]
        self.assertEqual(first["channel_name"], 102)
        self.assertEqual(first["channel"], 3)
        exports = decode_exports(bytes.fromhex(first["payload_hex"]), first["payload_bits"])
        self.assertEqual(exports["remaining_bits"], 0)
        self.assertEqual(exports["consumed_bits"], 3545)
        self.assertEqual(len(exports["objects"]), 3)
        self.assertEqual(exports["objects"][0]["path"], "Default__AoCPlayerControllerBP_C")
        self.assertEqual(exports["objects"][0]["checksum"], 0x6b62891c)
        self.assertEqual(exports["objects"][1]["path"], "PersistentLevel")
        self.assertEqual(exports["objects"][2]["path"], "GlobalGMCommands")

    def test_capture_dynamic_guid_is_not_static_hash(self):
        decoded = decode_packet(bytes.fromhex(self.capture[3710]["udp_hex"]), "server")
        actor = decoded["bunches"][1]
        prefix = decode_actor_prefix(bytes.fromhex(actor["payload_hex"]), actor["payload_bits"])
        self.assertEqual(prefix["actor"]["server_id"], 33)
        self.assertEqual(prefix["archetype"]["server_id"], 0)
        self.assertEqual(prefix["actor"]["object_id"], "0x00000000000925a0")

    def test_authored_controller_bunches_form_valid_transport(self):
        bunches = experimental_controller_bunches(532)
        packet = encode_packet(0, 1, 7700, 11595, [31], info=238498260022029, bunches=bunches)
        decoded = decode_packet(packet, "server")
        self.assertNotIn("error", decoded)
        export_bunch, actor_bunch = decoded["bunches"]
        self.assertEqual(export_bunch["reliable_sequence"], 533)
        self.assertEqual(actor_bunch["reliable_sequence"], 534)
        exports = decode_exports(bytes.fromhex(export_bunch["payload_hex"]), export_bunch["payload_bits"])
        self.assertEqual(exports["remaining_bits"], 0)
        prefix = decode_actor_prefix(bytes.fromhex(actor_bunch["payload_hex"]), actor_bunch["payload_bits"])
        self.assertEqual(prefix["actor"]["server_id"], 1)
        self.assertEqual(int(prefix["actor"]["object_id"], 16) & 1, 0)
        self.assertEqual(prefix["remaining_bits"], 12)
        self.assertNotEqual(bunches[1]["payload"], experimental_controller_bunches(532)[1]["payload"])

    def test_capture_gamestate_has_zero_default_transform_flag_nibble(self):
        decoded = decode_packet(bytes.fromhex(self.capture[3717]["udp_hex"]), "server")
        bunch = decoded["bunches"][0]
        self.assertEqual(bunch["channel"], 5)
        reader = BitReader(bytes.fromhex(bunch["payload_hex"]), bunch["payload_bits"])
        reader.read(384)
        self.assertEqual(reader.read(4), 0)

    def test_real_controller_location_uses_seven_bit_scaled_header(self):
        decoded = decode_packet(bytes.fromhex(self.capture[3710]["udp_hex"]), "server")
        bunch = decoded["bunches"][1]
        actor = decode_actor_location(bytes.fromhex(bunch["payload_hex"]), bunch["payload_bits"])
        self.assertEqual(actor["location_component_bits"], 24)
        self.assertEqual(actor["location"], [-660391.3, 389341.8, 13622.9])
        self.assertEqual(actor["consumed_bits"], 465)

    def test_scene_spawn_asset_identity_and_requested_location(self):
        # Keep the capture-derived serializer fixture independent of the lab's
        # current experimental spawn candidate.
        scene = experimental_scene_bunches(1022, (-660384., 389360.28125, 13622.94))
        expected = {"game_state": (5, 0x01442053), "pawn": (9, 0x02cdc5b6), "player_state": (39, 0xf4f44182)}
        for kind, bunches, actor_guid in scene:
            packet = encode_packet(0, 1, 7700, 11595, [31], info=0, bunches=bunches)
            decoded = decode_packet(packet, "server")
            self.assertNotIn("error", decoded)
            export, body = decoded["bunches"]
            self.assertEqual((export["reliable_sequence"], body["reliable_sequence"]), (1023, 0))
            self.assertEqual(export["channel"], expected[kind][0])
            refs = decode_exports(bytes.fromhex(export["payload_hex"]), export["payload_bits"])
            self.assertEqual(refs["objects"][0]["checksum"], expected[kind][1])
            self.assertEqual(refs["remaining_bits"], 0)
            actor = decode_actor_location(bytes.fromhex(body["payload_hex"]), body["payload_bits"])
            self.assertEqual(actor["actor"], actor_guid)
            self.assertEqual(int(actor_guid["object_id"], 16) & 1, 0)
            self.assertEqual(actor["location"], [-660384., 389360.3, 13622.9] if kind == "pawn" else [0., 0., 0.])
            self.assertEqual(actor["remaining_bits"], 3)

    def test_live_rpc_wrapper_with_explicit_candidate_cache_max(self):
        # The real live packet proves the wrapper. Maximum 995 is independently
        # compatible with the 995 reflected controller RPCs, but its exact cache
        # mapping remains unknown, so this test assigns no function name.
        parsed = decode_actor_rpc_content(bytes.fromhex("925c0100"), 28, 995)
        self.assertEqual(parsed["fields"], [{"field_index": 87, "argument_bits": 0, "argument_hex": ""}])
        authored, count = encode_actor_rpc_content(87, 995)
        self.assertEqual((authored.hex(), count), ("925c0100", 28))


if __name__ == "__main__":
    unittest.main()
