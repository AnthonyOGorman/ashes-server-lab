import copy
import json
from pathlib import Path
import unittest
from lab.pawn_player_state import validate_pawn_player_state, encode_pawn_player_state_content
from lab.unreal import BitReader
from lab.world_bootstrap import NetGUID

ROOT = Path(__file__).resolve().parents[1]

class PawnPlayerStateTests(unittest.TestCase):
    def setUp(self):
        load = lambda name: json.loads((ROOT/'evidence'/name).read_text())
        self.layouts = load('rep_layout_world_60304.json')
        self.actors = load('player_state_possession_60304.json')
        layout = next(x for x in self.layouts['layouts'] if x['class'] == 'PlayerPawn_C')
        self.cache = {k:layout[k] for k in ('class','class_index','class_serial')}
        self.pawn = next(x for x in self.actors['network_guid_actor_matches'] if x['actor']['class'] == 'PlayerPawn_C')
        self.ps = next(x for x in self.actors['network_guid_actor_matches'] if x['actor']['class'] == 'AoCPlayerStateBP_C')
        self.receiver = {'functions_invoked':False,'actor_address':self.pawn['actor']['address'],
            'player_state_address':self.ps['actor']['address'],'pawn_guid':self.pawn['guid'],
            'player_state_guid':self.ps['guid'],'property':layout['parents'][15]['property'],
            'notify_rva':'0x433c720','changed_callback_rva':'0x131c2f0',
            'notify_bytes':'488b9188030000e924890000','changed_callback_bytes':'c20000',
            'net_serialize_rva':'0x170af50'}
    def validate(self):
        return validate_pawn_player_state(self.layouts,self.receiver,self.actors,self.cache,self.pawn['guid'],self.ps['guid'])
    def test_reviewed_scalar_and_receiver(self):
        self.assertTrue(self.validate()['dispatch_authorized'])
        data,bits = encode_pawn_player_state_content(self.ps['guid'])
        r=BitReader(data,bits)
        self.assertEqual((r.read(1),r.read(1),r.packed(),r.read(1),r.packed()),(1,1,145,0,21))
        self.assertEqual(NetGUID.read(r).as_dict(),self.ps['guid'])
        self.assertEqual((r.packed(),r.remaining),(0,0))
    def test_refuses_unbound_or_changed_proofs(self):
        mutations = [lambda:self.receiver.update(notify_rva='0x1'),
            lambda:self.receiver.update(changed_callback_bytes='90'),
            lambda:self.receiver.update(functions_invoked=True),
            lambda:self.receiver.update(actor_address=self.ps['actor']['address']),
            lambda:self.receiver.update(net_serialize_rva='0x1'),
            lambda:self.cache.update(class_serial=-1),
            lambda:self.ps.update(guid_cache='other'),
            lambda:self.ps.update(weak_object_serial=0),
            lambda:self.pawn['actor'].update(player_state=self.ps['actor']),
            lambda:self.pawn['actor'].pop('player_state'),
            lambda:self.actors['network_guid_actor_matches'].append(copy.deepcopy(self.ps)),
            lambda:next(x for x in self.layouts['layouts'] if x['class']=='PlayerPawn_C')['commands'][0].update(command_type_byte=0)]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.setUp()
                mutation()
                with self.assertRaises(ValueError):self.validate()

if __name__ == '__main__':unittest.main()
