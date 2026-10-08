import copy
import json
from pathlib import Path
import unittest
from lab.character_info_component import encode_character_info_export, encode_character_info_empty_content, validate_character_info_export,encode_character_info_name_content,validate_character_info_name
from lab.world_bootstrap import decode_exports, NetGUID
from lab.unreal import BitReader
from lab.character_info_component import encode_character_info_guid_content,validate_character_info_guid,character_guid_words

ROOT=Path(__file__).resolve().parents[1]
class CharacterInfoTests(unittest.TestCase):
    def setUp(self):
        fixture=json.loads((ROOT/'tests/fixtures/character_info_epoch4_20261006.json').read_text())
        self.actors=fixture['actors']
        self.appearance=fixture['appearance']
        self.receiver=fixture['receiver']
        self.mapping=fixture['mapping']
        self.layouts=fixture['layouts']
        self.pawn=next(m['guid'] for m in self.actors['network_guid_actor_matches'] if m['actor']['class']=='PlayerPawn_C')
        self.component={'object_id':'0x12345678','server_id':1,'randomizer':7}
    def validate(self):
        return validate_character_info_export(self.actors,self.appearance,self.receiver,self.pawn,self.component)
    def test_existing_component_wire_and_empty_content(self):
        self.assertTrue(self.validate()['dispatch_authorized'])
        data,bits=encode_character_info_export(self.pawn,self.component)
        decoded=decode_exports(data,bits)
        self.assertEqual(decoded['remaining_bits'],0)
        obj=decoded['objects'][0]
        self.assertEqual((obj['path'],obj['checksum'],obj['no_load']),('BaseCharacterInfo',2952361071,True))
        self.assertEqual(obj['outer']['guid'],self.pawn)
        data,bits=encode_character_info_empty_content(self.component)
        r=BitReader(data,bits)
        self.assertEqual((r.read(1),r.read(1)),(1,0))
        self.assertEqual(NetGUID.read(r).as_dict(),NetGUID(0x12345678,1,7).as_dict())
        self.assertEqual((r.read(1),r.packed(),r.read(1),r.packed(),r.remaining),(1,9,0,0,0))
        self.assertEqual(bits,148)
    def test_refuses_wrong_component_or_receiver(self):
        mutations=[lambda:self.appearance['character_information']['identity'].update(class_='wrong',name='other'),
            lambda:self.appearance['character_information']['identity'].update(outer_address='0x1'),
            lambda:self.appearance['character_information']['fields']['bReplicates'].update(value=False),
            lambda:self.receiver.update(functions_invoked=True),
            lambda:self.receiver['virtual_targets']['0x2b0'].update(jump_target_bytes='909090'),
            lambda:self.actors['network_guid_actor_matches'].append(copy.deepcopy(next(m for m in self.actors['network_guid_actor_matches'] if m['guid']==self.pawn)))]
        for mutation in mutations:
            self.setUp()
            mutation()
            with self.assertRaises(ValueError):self.validate()
    def test_refuses_alias_and_invalid_guid(self):
        with self.assertRaises(ValueError):encode_character_info_export(self.pawn,self.pawn)
        with self.assertRaises(ValueError):encode_character_info_empty_content({'object_id':3,'server_id':1,'randomizer':0})
    def test_name_block_consumes_exactly(self):
        data,bits=encode_character_info_name_content(self.component,'LabExplorer')
        r=BitReader(data,bits)
        self.assertEqual((r.read(1),r.read(1)),(1,0))
        NetGUID.read(r)
        self.assertEqual(r.read(1),1)
        content_bits=r.packed()
        self.assertEqual(content_bits,r.remaining)
        self.assertEqual((r.read(1),r.packed(),r.string(),r.packed(),r.remaining),(0,8,'LabExplorer',0,0))
        with self.assertRaises(ValueError):encode_character_info_name_content(self.component,'')
    def test_name_guard_rejects_unaccepted_mapping(self):
        with self.assertRaises(ValueError):validate_character_info_name(self.actors,self.appearance,{}, {},self.pawn,self.component)
    def test_name_guard_accepts_reviewed_mapping_and_refuses_changed_layout(self):
        component=self.mapping['network_guid_component_matches'][0]['guid']
        def validate():return validate_character_info_name(self.actors,self.appearance,self.mapping,self.layouts,self.pawn,component)
        self.assertTrue(validate()['dispatch_authorized'])
        self.layouts['layouts'][0]['commands'][7]['uninterpreted_word_14']=9
        with self.assertRaises(ValueError):validate()
    def test_guid_update_uses_four_child_handles(self):
        value='00112233445566778899aabbccddeeff'
        data,bits=encode_character_info_guid_content(self.component,value)
        r=BitReader(data,bits)
        self.assertEqual((r.read(1),r.read(1)),(1,0))
        NetGUID.read(r)
        self.assertEqual(r.read(1),1)
        self.assertEqual(r.packed(),169)
        self.assertEqual(r.read(1),0)
        expected=[0x00112233,0x44556677,0x8899aabb,0xccddeeff]
        for handle,word in zip(range(3,7),expected):
            self.assertEqual((r.packed(),r.read(32)),(handle,word))
        self.assertEqual((r.packed(),r.remaining),(0,0))
        for invalid in ('0'*32,'abc','not-an-id'):
            with self.assertRaises(ValueError):character_guid_words(invalid)
    def test_guid_guard_validates_children_and_registration(self):
        component=self.mapping['network_guid_component_matches'][0]['guid']
        def validate():return validate_character_info_guid(self.actors,self.appearance,self.mapping,self.layouts,self.pawn,component)
        self.assertEqual(validate()['wire_handles'],[3,4,5,6])
        self.mapping['guid_fields']['C']['serialize_item_rva']='0x1'
        with self.assertRaises(ValueError):validate()
