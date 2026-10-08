import copy
import json
from pathlib import Path
import unittest

from lab.controller_player_state import (encode_controller_player_state_content,
    validate_controller_player_state, validate_controller_player_state_wire)
from lab.unreal import BitReader
from lab.world_bootstrap import NetGUID
from tools.decode_captured_property_prefix import decode

ROOT = Path(__file__).resolve().parents[1]


class ControllerPlayerStateTests(unittest.TestCase):
    def setUp(self):
        load = lambda name: json.loads((ROOT/'evidence'/name).read_text())
        self.layouts = load('rep_layout_world_60304.json')
        self.actors = load('player_state_possession_60304.json')
        layout = self.layouts['layouts'][0]
        self.cache = {k: layout[k] for k in ('class', 'class_index', 'class_serial')}
        self.pc = next(m for m in self.actors['network_guid_actor_matches']
                       if m['actor']['class'] == 'AoCPlayerControllerBP_C')
        self.ps = next(m for m in self.actors['network_guid_actor_matches']
                       if m['actor']['class'] == 'AoCPlayerStateBP_C')
        self.serializer = {'property': layout['parents'][13]['property'],
            'actor_address': self.pc['actor']['address'], 'net_serialize_virtual_offset': '0xc8',
            'net_serialize_rva': '0x170af50', 'serialize_object_virtual_offset': '0x340',
            'serialize_object_rva': '0x42875a0', 'internal_load_object_rva': '0x42740f0',
            'guid_reader_rva': '0x141e960'}

    def check_wire(self):
        return validate_controller_player_state_wire(self.layouts, self.serializer, self.actors,
            self.cache, self.pc['guid'], self.ps['guid'])

    def test_complete_capture_boundary_proves_raw_guid_without_presence_bit(self):
        proof = decode(ROOT/'evidence/world_bootstrap_capture.json')
        field = next(f for f in proof['fields'] if f['property'] == 'PlayerState')
        self.assertEqual((field['handle'], field['value_start_bit'], field['value_bits']), (19, 597, 128))
        self.assertTrue(proof['property_content_exhausted'])
        self.assertEqual(proof['following_header_start_bit'], 1045)
        payload, bits = encode_controller_player_state_content(field['value'])
        self.assertEqual(bits, 163)
        reader = BitReader(payload, bits)
        self.assertEqual([reader.read(1), reader.read(1)], [1, 1])
        self.assertEqual(reader.packed(), 145)
        self.assertEqual(reader.read(1), 0)
        self.assertEqual(reader.packed(), 19)
        self.assertEqual(NetGUID.read(reader).as_dict(), field['value'])
        self.assertEqual(reader.packed(), 0)
        self.assertEqual(reader.remaining, 0)

    def test_wire_pass_is_explicitly_not_dispatch_authorization(self):
        self.assertFalse(self.check_wire()['dispatch_authorized'])
        with self.assertRaisesRegex(ValueError, 'OnRep_PlayerState target is unreviewed'):
            validate_controller_player_state(self.layouts, self.serializer, self.actors,
                self.cache, self.pc['guid'], self.ps['guid'])

    def test_refuses_changed_layout_serializer_and_unknown_actor(self):
        mutations = [
            lambda: self.layouts['layouts'][0]['commands'][0].update(command_type_byte=0),
            lambda: self.cache.update(class_serial=1),
            lambda: self.serializer.update(net_serialize_rva='0x170acb0'),
            lambda: self.ps.update(guid_cache='0xother'),
            lambda: self.ps.update(weak_object_serial=0),
            lambda: self.pc['actor'].update(player_state=self.ps['actor']),
            lambda: self.pc['actor'].pop('player_state'),
            lambda: self.serializer.update(actor_address=self.ps['actor']['address']),
            lambda: self.actors['network_guid_actor_matches'].append(copy.deepcopy(self.ps)),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.setUp()
                mutation()
                with self.assertRaises(ValueError):
                    self.check_wire()

    def test_reviewed_receiver_must_bind_both_current_actors_and_exact_code(self):
        receiver = json.loads((ROOT/'evidence/controller_player_state_receiver_56180.json').read_text())
        receiver.update(actor_address=self.pc['actor']['address'], player_state_address=self.ps['actor']['address'],
                        controller_guid=self.pc['guid'], player_state_guid=self.ps['guid'])
        args = (self.layouts, self.serializer, self.actors, self.cache, self.pc['guid'], self.ps['guid'])
        self.assertTrue(validate_controller_player_state(*args, receiver=receiver)['dispatch_authorized'])
        for key, value in (('actor_address', self.ps['actor']['address']), ('controller_notify_rva', '0x3eebc81'),
                           ('player_state_set_owner_rva', '0x1'), ('controller_notify_bytes', ''),
                           ('player_state_guid', self.pc['guid']), ('functions_invoked', True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_controller_player_state(*args, receiver={**receiver, key: value})

    def test_refuses_null_static_overflow_and_boolean_guids(self):
        for key, value in [('object_id', '0x0'), ('object_id', '0x1'),
                           ('object_id', hex(2**64)), ('server_id', 0),
                           ('server_id', True), ('randomizer', -1), ('randomizer', 2**32)]:
            with self.subTest(key=key, value=value):
                guid = {**self.ps['guid'], key: value}
                with self.assertRaises(ValueError):
                    encode_controller_player_state_content(guid)


if __name__ == '__main__':
    unittest.main()
