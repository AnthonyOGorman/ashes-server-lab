import struct
import json
from pathlib import Path
import unittest
import tempfile
import time
from unittest.mock import patch

from lab.unreal import (BitReader, BitWriter, DecodeError, WorldProtocol,
                        decode_packet, encode_control, encode_handshake,
                        encode_packet, DEFAULT_MAP)

# Independent real packet fixtures from the user's gameplay capture. Frame IDs
# make the transport/control claims reproducible with tshark.
CAPTURE = {
    3634: "96760c50a40102800027b117520000000000000000000000000000000000000000000000000000000000007f7f7f7fff7f00000000000000000000000000000000fdaae419644ecf2f6bf96cae56d2f7d3000000000000000000000000000000001fd9fd1b8f416cf11ef525b26a70c0550000000000000000000000000000000000000000000000006b9051a0bb47efb001",
    3646: "96760c50044c78472d00000040c35c046d3af6ff4d0020f55f000c00043889bd900200000000000c",
    3650: "96760c500418b5141e00000040c35c046d3af6ff110015fe178003030900000046393436313433340003",
    3651: "96760c50041cb5155e00000040c35c046d3ab601",
    3652: "96760c50044c78482d00000040c35c046d3af698110049fd17c01d05020000003000320000003f4e616d653d414e54484f4e592d50432d453343433041413734313832414539464331353636344141364535313430343700082c000000414e54484f4e592d50432d453343433041413734313832414539464331353636344141364535313430343700050000004e554c4c0003",
    3657: "96760c50041cb5165e00000040c35c046d3af6c4110016fe17c01e01330000002f47616d652f4c6576656c732f56657272615f576f726c645f4d61737465722f56657272615f576f726c645f4d6173746572003b0000002f47616d652f47616d65426c75657072696e74732f416f4347616d654d6f64654261736542502e416f4347616d654d6f64654261736542505f43000000000003",
    3660: "96760c50045c784aed03000040c35c046d3a760810004afd17400104400d030003",
}


class UnrealTests(unittest.TestCase):
    def test_live_mixed_bunch_lengths_use_value_dependent_bounded_integer(self):
        fixture = json.loads((Path(__file__).resolve().parents[1]/"evidence"/"live_bounded_bunch_fixtures.json").read_text(encoding="utf-8"))
        for row in fixture["evidence"]:
            with self.subTest(packet_id=row["packet_id"]):
                parsed = decode_packet(bytes.fromhex(row["udp_hex"]), "client")
                self.assertNotIn("error", parsed)
                self.assertEqual(parsed["payload_length_max"], 8224)
                self.assertEqual([(b["payload_bits"], b["payload_length_field_bits"]) for b in parsed["bunches"][:2]], [(7436, 13), (28, 14)])
                if row["packet_id"] != 23939:
                    self.assertEqual(parsed["bunches"][2]["payload_length_field_bits"], 13)
                    self.assertEqual(parsed["bunches"][2]["payload_bits"], 241)

    def test_bounded_length_boundary_is_not_fixed_width(self):
        for value in (0, 8, 28, 31, 32, 241, 7436, 8223):
            writer = BitWriter().uint(value, 8224)
            self.assertEqual(writer.bits, 14 if value % 8192 < 32 else 13)
            reader = BitReader(bytes(writer.data), writer.bits)
            self.assertEqual(reader.uint(8224), value)
            self.assertEqual(reader.remaining, 0)
        with self.assertRaises(DecodeError):
            BitReader(b"").uint(0)

    def test_real_capture_control_messages(self):
        expected = {3646: ("Hello", 11591, 328), 3650: ("Challenge", 7700, 533), 3652: ("Login", 11592, 329), 3657: ("Welcome", 7702, 534), 3660: ("NetSpeed", 11594, 330)}
        for frame, (name, seq, reliable) in expected.items():
            with self.subTest(frame=frame):
                parsed = decode_packet(bytes.fromhex(CAPTURE[frame]), "server" if frame in (3650, 3657) else "client")
                self.assertNotIn("error", parsed)
                self.assertEqual(parsed["sequence"], seq)
                bunch = parsed["bunches"][0]
                self.assertEqual(bunch["start_bit"], 162)
                self.assertEqual(bunch["reliable_sequence"], reliable)
                self.assertEqual(bunch["messages"][0]["name"], name)
        self.assertEqual(decode_packet(bytes.fromhex(CAPTURE[3657]))["bunches"][0]["messages"][0]["map"], DEFAULT_MAP)
        self.assertEqual(decode_packet(bytes.fromhex(CAPTURE[3660]))["bunches"][0]["messages"][0]["rate"], 200000)

    def test_capture_pure_ack_is_not_a_bunch(self):
        parsed = decode_packet(bytes.fromhex(CAPTURE[3651]), "server")
        self.assertNotIn("error", parsed)
        self.assertFalse(parsed["has_packet_info"])
        self.assertEqual(parsed["bunches"], [])
        self.assertEqual(parsed["ack_history"], [1])

    def test_real_handshake_format(self):
        parsed = decode_packet(bytes.fromhex(CAPTURE[3634]))
        self.assertEqual(parsed["network_version"], 0xa42f624e)
        self.assertEqual(parsed["version"], 4)
        self.assertEqual(parsed["client_id"], 1)
        self.assertEqual(parsed["extension_bits"], 816)

    def test_bitreader_rejects_truncation_and_overflows(self):
        with self.assertRaises(DecodeError):
            BitReader(b"\0").read(9)
        with self.assertRaises(DecodeError):
            BitReader(b"\xff"*6).packed()
        for data in (b"", b"test", bytes.fromhex(CAPTURE[3646])[:-8], bytes.fromhex(CAPTURE[3646])+b"\0"):
            self.assertIn("error", decode_packet(data))

    def test_fstring_negative_utf16_count(self):
        data = BitWriter().string("Verra 日本").finish()
        self.assertLess(struct.unpack("<i", data[:4])[0], 0)
        self.assertEqual(BitReader(data).string(), "Verra 日本")

    def test_unknown_actor_payload_stays_opaque(self):
        # Move a captured control channel to another channel at its packed index
        # bit position. Transport remains valid but cannot imply movement.
        data = bytearray.fromhex(CAPTURE[3646])
        bit = 162+5+1
        data[bit//8] |= 1 << (bit%8)
        parsed = decode_packet(bytes(data))
        self.assertNotIn("error", parsed)
        self.assertEqual(parsed["bunches"][0]["channel"], 1)
        self.assertEqual(parsed["bunches"][0]["evidence"], "opaque_replication_payload")
        self.assertNotIn("messages", parsed["bunches"][0])

    def _connect(self):
        events = []
        server = WorldProtocol(lambda k, v: events.append(k))
        peer = ("127.0.0.1", 4242)
        challenge = server.handle(bytes.fromhex(CAPTURE[3634]), peer)[0]
        p = decode_packet(challenge)
        response = encode_handshake(p, 2, p["timestamp"], bytes.fromhex(p["cookie"]))
        ack = decode_packet(server.handle(response, peer)[0])
        self.assertEqual(ack["packet_type"], 3)
        return server, peer, events, server.connections[peer]

    def test_state_machine_proves_join_not_walking(self):
        server, peer, events, c = self._connect()
        seq = (c.in_seq+1) & 16383
        rel = (c.in_reliable+1) & 1023
        def send(payload):
            nonlocal seq, rel
            packet = encode_packet(c.session, c.client, seq, (c.out_seq-1)&16383, [0xff], payload, rel, opened=(rel == ((c.in_reliable+1)&1023)), info=238498260022029)
            seq = (seq+1)&16383
            rel = (rel+1)&1023
            return server.handle(packet, peer)
        hello = send(encode_control(0, network_version=0xa42f624e))
        self.assertEqual(decode_packet(hello[0])["bunches"][0]["messages"][0]["name"], "Challenge")
        welcome = send(encode_control(5))
        self.assertEqual(decode_packet(welcome[0])["bunches"][0]["messages"][0]["name"], "Welcome")
        send(encode_control(4))
        send(encode_control(9))
        self.assertEqual(events, ["udp_challenge", "udp_handshake", "hello", "login", "welcome", "netspeed", "join"])
        self.assertEqual(c.phase, "joined")
        self.assertNotIn("walking", events)

    def test_unreliable_move_responses_are_not_retried_after_lost_packet_ack(self):
        from lab.movement_response import encode_move_ack_content
        server,peer,events,c=self._connect()
        payload,bits=encode_move_ack_content(42.)
        bunch={'channel':9,'channel_name':102,'reliable':False,
               'payload':payload,'payload_bits':bits}
        for _ in range(100):server._send_bunches(c,[bunch])
        self.assertEqual(c.pending_bunches,{})
        # Simulate a stale entry retained across a hot reload. A new incoming
        # packet must discard it rather than resend obsolete movement data.
        c.pending_bunches[7]=([bunch],0.,0)
        incoming=encode_packet(c.session,c.client,(c.in_seq+1)&16383,
                               (c.out_seq-1)&16383,[0])
        replies=server.handle(incoming,peer)
        self.assertEqual(c.pending_bunches,{})
        self.assertEqual(len(replies),1)
        self.assertEqual(decode_packet(replies[0],'server')['bunches'],[])

    def test_mixed_packet_retries_only_its_reliable_bunches(self):
        server,peer,events,c=self._connect()
        reliable={'channel':0,'channel_name':255,'reliable':True,
                  'reliable_sequence':c.out_reliable,'payload':encode_control(4)}
        unreliable={'channel':9,'channel_name':102,'reliable':False,
                    'payload':b'\0','payload_bits':1}
        seq=c.out_seq
        server._send_bunches(c,[reliable,unreliable])
        self.assertEqual(c.pending_bunches[seq][0],[reliable])
        c.pending_bunches[seq]=([reliable,unreliable],0.,0)
        incoming=encode_packet(c.session,c.client,(c.in_seq+1)&16383,
                               (c.out_seq-1)&16383,[0])
        replies=server.handle(incoming,peer)
        self.assertEqual(len(replies),1)
        self.assertEqual([b['channel'] for b in decode_packet(replies[0],'server')['bunches']],[0])

    def test_live_close_fixture_exhaustion_and_closed_epoch_no_retransmits(self):
        from lab.unreal import Connection
        fixture = json.loads((Path(__file__).resolve().parents[1]/"evidence/live_world_close_56352.json").read_text())
        packet = bytes.fromhex(fixture["udp_hex"])
        parsed = decode_packet(packet)
        self.assertNotIn("error", parsed)
        self.assertEqual(len(parsed["bunches"]), 1)
        bunch = parsed["bunches"][0]
        self.assertEqual((bunch["channel"],bunch["close"],bunch["close_reason"],bunch["reliable_sequence"],bunch["channel_name"],bunch["payload_bits"]), (0,True,0,189,255,0))
        events=[];server=WorldProtocol(lambda k,v:events.append(k));peer=tuple(fixture["peer"])
        c=Connection(b"\0"*20,parsed["session_id"],parsed["client_id"],0,(parsed["sequence"]-1)&16383,0,188,phase="joined")
        c.pending={1:(b"test",1,0.,0)};c.pending_bunches={2:([],0.,0)};c.possession_acknowledged=True
        server.connections[peer]=c
        replies=server.handle(packet,peer)
        self.assertEqual(c.phase,"closed");self.assertEqual(c.pending,{})
        self.assertEqual(c.pending_bunches,{});self.assertFalse(c.possession_acknowledged)
        self.assertEqual(decode_packet(replies[0],"server")["bunches"],[])
        server.handle(packet,peer)
        self.assertEqual(events,["udp_connection_closed"])
        # One changed close-reason bit is explicitly unsupported.
        corrupt=bytearray(packet);reason_bit=bunch["start_bit"]+3
        corrupt[reason_bit//8] ^= 1<<(reason_bit%8)
        self.assertIn("nonzero channel-close",decode_packet(bytes(corrupt))["error"])
        # Complete known grammar, but opaque payload is never a validated close.
        opaque=encode_packet(c.session,c.client,1,0,[1],bunches=[{"channel":0,"channel_name":255,"close":True,
            "reliable_sequence":1,"payload":b"\x09"}])
        self.assertIn("error",decode_packet(opaque))

    def test_same_peer_new_cookie_replaces_epoch_duplicate_and_old_cookie_do_not(self):
        server,peer,events,old=self._connect()
        old.phase="joined";old.actor_guids={"pawn":{"object_id":"old"}}
        old.channel_reliable={9:333};old.possession_acknowledged=True
        old.pending={1:(b"old",333,0.,0)};old.consumed_experiment_ids={"old-command"}
        original_timestamp=old.handshake_timestamp
        old_response=encode_handshake(decode_packet(bytes.fromhex(CAPTURE[3634])),2,original_timestamp,old.cookie)
        with patch("lab.unreal.time.time",return_value=original_timestamp+1):
            challenge=decode_packet(server.handle(bytes.fromhex(CAPTURE[3634]),peer)[0])
            response=encode_handshake(challenge,2,challenge["timestamp"],bytes.fromhex(challenge["cookie"]))
            server.handle(response,peer)
            fresh=server.connections[peer]
            self.assertIsNot(fresh,old);self.assertNotEqual(fresh.connection_id,old.connection_id)
            self.assertEqual((fresh.phase,fresh.actor_guids,fresh.channel_reliable,fresh.pending,fresh.consumed_experiment_ids),("connected",{},{},{},set()))
            self.assertFalse(fresh.possession_acknowledged)
            server.handle(response,peer)
            self.assertIs(server.connections[peer],fresh)
            self.assertEqual(events.count("udp_handshake"),2)
            server.handle(old_response,peer)
            self.assertIs(server.connections[peer],fresh)
            self.assertIn("udp_rejected_old_handshake",events)
        # The new epoch negotiates control from new cookie seeds through Join.
        for payload in (encode_control(0,network_version=0xa42f624e),encode_control(5),encode_control(9)):
            packet=encode_packet(fresh.session,fresh.client,(fresh.in_seq+1)&16383,(fresh.out_seq-1)&16383,[0xff],
                payload,(fresh.in_reliable+1)&1023,opened=fresh.phase=="connected")
            server.handle(packet,peer)
        self.assertEqual(fresh.phase,"joined")
        self.assertEqual(events.count("join"),1)
        self.assertEqual(fresh.actor_guids,{})

    def test_guarded_possession_preserves_authored_guid_and_actor_sequence(self):
        from lab.world_bootstrap import decode_actor_rpc_content, decode_rpc_object_argument
        server, peer, events, c = self._connect()
        with self.assertRaises(ValueError):
            server._client_restart(c, 87, 1000)
        c.phase = "joined"
        # Simulate connection objects created before new dataclass fields were
        # installed by a module reload. Both stores must initialize safely.
        del c.actor_guids
        del c.channel_reliable
        controller = decode_packet(server._bootstrap(c)[0], "server")
        controller_final = controller["bunches"][-1]["reliable_sequence"]
        server._bootstrap_scene(c)
        pawn_guid = dict(c.actor_guids["pawn"])
        with self.assertRaises(ValueError):
            server._client_restart(c, 87, 1000, cache_verified=True)
        before = c.out_seq
        # Fixture index/max are explicitly supplied; no live function mapping
        # is asserted by this unit test.
        rpc = decode_packet(server._client_restart(c, 87, 1000, cache_verified=True, actors_verified=True)[0], "server")
        self.assertEqual(c.out_seq, (before+1)&16383)
        bunch = rpc["bunches"][0]
        self.assertEqual(bunch["channel"], 3)
        self.assertEqual(bunch["reliable_sequence"], (controller_final+1)&1023)
        fields = decode_actor_rpc_content(bytes.fromhex(bunch["payload_hex"]), bunch["payload_bits"], 1000)["fields"]
        self.assertEqual(len(fields), 1)
        argument = fields[0]
        self.assertEqual(argument["field_index"], 87)
        decoded_guid = decode_rpc_object_argument(bytes.fromhex(argument["argument_hex"]), argument["argument_bits"])
        self.assertEqual(decoded_guid.as_dict(), pawn_guid)
        self.assertEqual(c.actor_guids["pawn"], pawn_guid)
        self.assertIn("client_restart_experiment", events)
        self.assertNotIn("walking", events)
        with self.assertRaises(ValueError):
            server._bootstrap_scene(c)

    def test_fixed_client_restart_command_is_consumed_once_and_expiry_rejects(self):
        from pathlib import Path
        source = Path(__file__).resolve().parents[1]
        actors = json.loads((source/"evidence/player_state_world_29312.json").read_text())
        cache = json.loads((source/"evidence/driver_net_cache_world_29312.json").read_text())
        controller = next(m["guid"] for m in actors["network_guid_actor_matches"] if m["actor"]["class"] == "AoCPlayerControllerBP_C")
        pawn = next(m["guid"] for m in actors["network_guid_actor_matches"] if m["actor"]["class"] == "PlayerPawn_C")
        # This synthetic HUD state exercises the gate, not a live HUD claim.
        local_address = next(m["actor"]["address"] for m in actors["network_guid_actor_matches"] if m["guid"] == controller)
        next(item for item in actors["controllers"] if item["address"] == local_address)["hud"] = {
            "class": "BP_AOCHUD_C", "ancestors": ["BP_AOCHUD_C", "AoCHUDBase", "HUD", "Actor"]}
        server, peer, events, c = self._connect()
        c.phase = "joined"
        c.actor_guids = {"controller": controller, "pawn": pawn}
        c.channel_reliable = {3: 1023}
        command = {"command": "ClientRestart", "peer": list(peer), "controller_guid": controller,
                   "pawn_guid": pawn, "cache_snapshot": "evidence/driver_net_cache_world_29312.json",
                   "actor_snapshot": "evidence/player_state_world_29312.json", "id": "verified-one-shot", "expires_at": time.time()+25}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/"data").mkdir()
            (root/"evidence").mkdir()
            (root/"evidence/player_state_world_29312.json").write_text(json.dumps(actors))
            (root/"evidence/driver_net_cache_world_29312.json").write_text(json.dumps(cache))
            path = root/"data/client-restart-experiment.json"
            path.write_text(json.dumps(command))
            with patch("lab.unreal.__file__", str(root/"lab/unreal.py")), patch("tools.protocol_proof.validate_current_client_proofs"):
                packets = server._poll_client_restart_experiment(c, peer)
                self.assertEqual(len(packets), 1)
                bunch = decode_packet(packets[0], "server")["bunches"][0]
                self.assertEqual(bunch["reliable_sequence"], 0)
                self.assertEqual(server._poll_client_restart_experiment(c, peer), [])
                path.write_text(json.dumps(command)+"\n")
                self.assertEqual(server._poll_client_restart_experiment(c, peer), [])
                command.update(id="expired-one-shot", expires_at=time.time()-1)
                path.write_text(json.dumps(command))
                self.assertEqual(server._poll_client_restart_experiment(c, peer), [])
                self.assertIn("expired-one-shot", c.consumed_experiment_ids)
                self.assertIn("client_restart_experiment_rejected", events)
        self.assertEqual(events.count("client_restart_experiment"), 1)

    def test_staged_hud_allows_export_but_missing_or_wrong_hud_refuses_possession(self):
        source = Path(__file__).resolve().parents[1]
        actors = json.loads((source/"evidence/player_state_world_29312.json").read_text())
        cache = json.loads((source/"evidence/driver_net_cache_world_29312.json").read_text())
        controller = next(m for m in actors["network_guid_actor_matches"] if m["actor"]["class"] == "AoCPlayerControllerBP_C")
        pawn = next(m["guid"] for m in actors["network_guid_actor_matches"] if m["actor"]["class"] == "PlayerPawn_C")
        server, peer, events, c = self._connect()
        c.phase, c.actor_guids, c.channel_reliable = "joined", {"controller": controller["guid"], "pawn": pawn}, {3: 1023}
        command = {"command": "ClientRestart", "peer": list(peer), "controller_guid": controller["guid"],
                   "pawn_guid": pawn, "cache_snapshot": "evidence/driver_net_cache_world_29312.json",
                   "actor_snapshot": "evidence/player_state_world_29312.json", "id": "missing-hud", "expires_at": time.time()+25}
        state = next(item for item in actors["controllers"] if item["address"] == controller["actor"]["address"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/"data").mkdir()
            (root/"evidence").mkdir()
            (root/command["cache_snapshot"]).write_text(json.dumps(cache))
            path = root/"data/client-restart-experiment.json"
            with patch("lab.unreal.__file__", str(root/"lab/unreal.py")), patch("tools.protocol_proof.validate_current_client_proofs"):
                for hud in (None, {"class": "HUD", "ancestors": ["HUD"]}, {"class": "BP_AOCHUD_C", "ancestors": ["HUD"]}):
                    state["hud"] = hud
                    (root/command["actor_snapshot"]).write_text(json.dumps(actors))
                    command["id"] += "x"
                    path.write_text(json.dumps(command))
                    self.assertEqual(server._poll_client_restart_experiment(c, peer), [])
                command.update(command="ClientSetHUD", id="hud-stage")
                path.write_text(json.dumps(command))
                packets = server._poll_client_restart_experiment(c, peer)
                self.assertEqual(len(packets), 1)
                bunches = decode_packet(packets[0], "server")["bunches"]
                self.assertEqual([b["reliable_sequence"] for b in bunches], [0, 1])
                self.assertEqual(c.channel_reliable[3], 1)
                self.assertNotIn("player_spawned", events)
                command["id"] = "another-hud-stage"
                path.write_text(json.dumps(command))
                self.assertEqual(server._poll_client_restart_experiment(c, peer), [])
        self.assertNotIn("client_restart_experiment", events)
        self.assertEqual(events.count("client_set_hud_experiment"), 1)

    def test_actual_possession_ack_requires_cache_contract_and_exact_sent_guid(self):
        from lab.world_bootstrap import NetGUID, encode_rpc_object_argument, encode_actor_rpc_content
        source = Path(__file__).resolve().parents[1]
        fixture = json.loads((source/"evidence/live_possession_packets_29312.json").read_text())
        actual = next(p for p in fixture["packets"] if p["direction"] == "C2S")
        bunch = decode_packet(bytes.fromhex(actual["hex"]), "client")["bunches"][0]
        server, peer, events, c = self._connect()
        c.phase = "joined"
        c.actor_guids = {"controller": {"object_id": "0x0000000000000002", "server_id": 1, "randomizer": 7}, "pawn": fixture["pawn_guid"]}
        self.assertFalse(server._observe_possession_ack(c, bunch, peer))
        c.possession_ack_contract = {"field_index": 73, "field_max": 1032,
            "controller_guid": dict(c.actor_guids["controller"]), "pawn_guid": dict(c.actor_guids["pawn"]),
            "cache_snapshot": "evidence/driver_net_cache_world_29312.json"}
        for flag in ("partial", "exports", "must_map", "open", "close"):
            self.assertFalse(server._observe_possession_ack(c, {**bunch, flag: True}, peer))
        self.assertFalse(server._observe_possession_ack(c, {**bunch, "reliable": False}, peer))
        self.assertFalse(server._observe_possession_ack(c, {**bunch, "channel": 9}, peer))
        for guid, index in ((None, 73), (NetGUID(2, 1, 7), 73), (NetGUID(int(fixture["pawn_guid"]["object_id"], 16), 1, fixture["pawn_guid"]["randomizer"]), 72)):
            argument, bits = encode_rpc_object_argument(guid)
            payload, count = encode_actor_rpc_content(index, 1032, argument, bits)
            self.assertFalse(server._observe_possession_ack(c, {**bunch, "payload_hex": payload.hex(), "payload_bits": count}, peer))
        # Feed the exact observed RPC through live transport dispatch, preserving
        # its channel payload but constructing fresh fixture transport numbers.
        outgoing = {**bunch, "payload": bytes.fromhex(bunch["payload_hex"])}
        for _ in range(2):
            packet = encode_packet(c.session, c.client, (c.in_seq+1)&16383, (c.out_seq-1)&16383, [1], bunches=[outgoing])
            server.handle(packet, peer)
        self.assertTrue(c.possession_acknowledged)
        self.assertEqual(events.count("player_spawned"), 1)
        self.assertNotIn("walking", events)

    def test_cookie_is_bound_to_peer(self):
        server = WorldProtocol()
        original = ("127.0.0.1", 4242)
        challenge = decode_packet(server.handle(bytes.fromhex(CAPTURE[3634]), original)[0])
        response = encode_handshake(challenge, 2, challenge["timestamp"], bytes.fromhex(challenge["cookie"]))
        self.assertEqual(server.handle(response, ("127.0.0.1", 4243)), [])
        self.assertEqual(server.connections, {})

    def test_invalid_reliable_gap_is_not_acknowledged(self):
        server, peer, events, c = self._connect()
        packet = encode_packet(c.session, c.client, (c.in_seq+1)&16383, (c.out_seq-1)&16383, [0], encode_control(0, network_version=0xa42f624e), (c.in_reliable+2)&1023)
        answer = decode_packet(server.handle(packet, peer)[0])
        self.assertEqual(answer["ack_history"][0]&1, 0)
        self.assertIn("udp_reliable_gap", events)

    def test_reliable_retransmission_is_acknowledged_without_second_hello(self):
        server, peer, events, c = self._connect()
        payload = encode_control(0, network_version=0xa42f624e)
        rel = (c.in_reliable+1)&1023
        first = encode_packet(c.session, c.client, (c.in_seq+1)&16383, (c.out_seq-1)&16383, [0], payload, rel, opened=True)
        server.handle(first, peer)
        again = encode_packet(c.session, c.client, (c.in_seq+1)&16383, (c.out_seq-1)&16383, [0], payload, rel)
        reply = decode_packet(server.handle(again, peer)[0])
        self.assertEqual(events.count("hello"), 1)
        self.assertEqual(reply["ack_history"][0]&1, 1)


if __name__ == "__main__":
    unittest.main()
