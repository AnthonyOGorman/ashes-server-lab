import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from lab.unreal import BitReader, BitWriter, Connection, WorldProtocol, decode_packet
from lab.world_bootstrap import NetGUID
from lab.game_state_begin_play import encode_game_state_begin_play_content, validate_game_state_begin_play
ROOT = Path(__file__).resolve().parents[1]

def fixture(name):
    return json.loads((ROOT/'evidence'/name).read_text())

def proofs():
    layouts = fixture('begin_play_layout_fixture_56352.json')
    lifecycle = fixture('begin_play_lifecycle_fixture_56352.json')
    serializer = fixture('begin_play_serializer_native_fixture_56352.json')
    # Synthetic guard inputs: actual live BP target must be reprobed before dispatch.
    serializer.update(native_only=False, observed_bool_value=False, game_state_class_index=88270,
        actor_address=lifecycle['game_state']['identity']['address'], actor_roles={'Role':1,'RemoteRole':4})
    serializer['notify']['target_evidence'] = 'actual_accepted_BP_actor_virtual_target'
    serializer['notify']['receiver_address'] = lifecycle['game_state']['identity']['address']
    return layouts,serializer,lifecycle,lifecycle['game_state']['identity']

class GameStateBeginPlayTests(unittest.TestCase):
    def test_independent_full_partial_capture_bool_prefix(self):
        source = fixture('gamestate_property_capture.json')
        writer = BitWriter()
        sequences = []
        for row in source['evidence']:
            for bunch in decode_packet(bytes.fromhex(row['udp_hex']), 'server').get('bunches',[]):
                if bunch['channel'] == 5 and 534 <= bunch['reliable_sequence'] <= 549:
                    sequences.append(bunch['reliable_sequence'])
                    writer.raw(bytes.fromhex(bunch['payload_hex']),bunch['payload_bits'])
        self.assertEqual(sequences,list(range(534,550)))
        self.assertEqual(writer.bits,119929)
        reader=BitReader(bytes(writer.data),writer.bits)
        reader.read(388)
        self.assertEqual([reader.read(1),reader.read(1)],[1,1])
        length=reader.packed()
        self.assertEqual((length,reader.pos+length),(119515,writer.bits))
        self.assertEqual(reader.read(1),0)
        self.assertEqual(reader.packed(),1);self.assertEqual(reader.read(32),0)
        self.assertEqual(reader.packed(),8);self.assertEqual(reader.read(3),1)
        self.assertEqual(reader.packed(),16);self.assertEqual(reader.read(3),4)
        self.assertEqual(reader.packed(),19);NetGUID.read(reader)
        self.assertEqual(reader.packed(),21)
        self.assertEqual(reader.pos,621)
        self.assertEqual(reader.read(1),1)
        self.assertEqual(reader.packed(),23)  # Next proven field aligns after precisely one bit.

    def test_fixed_single_property_complete_exhaustion(self):
        data,bits=encode_game_state_begin_play_content()
        reader=BitReader(data,bits)
        self.assertEqual([reader.read(1),reader.read(1)],[1,1])
        count=reader.packed();self.assertEqual(count,reader.remaining)
        self.assertEqual(reader.read(1),0);self.assertEqual(reader.packed(),21)
        self.assertEqual(reader.read(1),1);self.assertEqual(reader.packed(),0)
        self.assertEqual(reader.remaining,0)
        self.assertEqual(bits,28)

    def test_missing_or_stale_world_and_native_only_target_refused(self):
        l,s,w,a=proofs()
        self.assertEqual(validate_game_state_begin_play(l,s,w,a)['wire_handle'],21)
        for mutate in ('missing_parent','missing_command','wrong_world','already_true','native_only','wrong_bool_bits','array_span','authority'):
            ll,ss,ww,aa=map(copy.deepcopy,(l,s,w,a))
            layout=next(x for x in ll['layouts'] if x['class']=='AoCGameStateBP_C')
            if mutate=='missing_parent':layout['parents']=[x for x in layout['parents'] if x['parent_index']!=15]
            elif mutate=='missing_command':layout['commands']=[x for x in layout['commands'] if x['command_index']!=20]
            elif mutate=='wrong_world':ww['world']['fields']['GameState']['value']['address']='0x1234'
            elif mutate=='already_true':ww['game_state']['fields']['bReplicatedHasBegunPlay']['value']=True
            elif mutate=='native_only':ss['native_only']=True
            elif mutate=='wrong_bool_bits':ss['net_serialize_rva']='0x170ad20'
            elif mutate=='array_span':layout['commands'][0]['command_type_byte']=0
            elif mutate=='authority':ss['actor_roles']['Role']=4
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                validate_game_state_begin_play(ll,ss,ww,aa)

    def test_emission_requires_possession_retained_channel_once_no_movement(self):
        events=[]
        server=WorldProtocol(lambda kind,detail:events.append((kind,detail)))
        c=Connection(b'\0'*20,0,1,0,0,0,0,phase='joined')
        c.actor_guids={'game_state':{'object_id':'0x0000000000000002','server_id':1,'randomizer':3}}
        c.channel_reliable={5:1023}
        with self.assertRaises(ValueError):server._game_state_begin_play(c,proof_verified=True)
        c.possession_acknowledged=True
        packets=server._game_state_begin_play(c,proof_verified=True)
        bunch=decode_packet(packets[0],'server')['bunches'][0]
        self.assertEqual((bunch['channel'],bunch['reliable_sequence'],bunch['payload_bits']),(5,0,28))
        with self.assertRaises(ValueError):server._game_state_begin_play(c,proof_verified=True)
        self.assertEqual(events[0][0],'game_state_begin_play_experiment')
        self.assertFalse(events[0][1]['movement_proved'])

    def test_command_current_guid_binding_freshness_once_and_nonce_rejection(self):
        actors=fixture('player_state_possession_56352.json')
        refs={kind:next(m['guid'] for m in actors['network_guid_actor_matches'] if m['actor']['class']==cls)
            for kind,cls in (('controller','AoCPlayerControllerBP_C'),('pawn','PlayerPawn_C'),('game_state','AoCGameStateBP_C'))}
        layouts,serializer,lifecycle,_=proofs()
        events=[];server=WorldProtocol(lambda kind,detail:events.append((kind,detail)))
        c=Connection(b'\0'*20,0,1,0,0,0,0,phase='joined')
        c.actor_guids=refs;c.channel_reliable={3:10,5:1023,9:10};c.possession_acknowledged=True
        peer=('127.0.0.1',9999)
        command={'command':'GameStateBeginPlay','peer':list(peer),'controller_guid':refs['controller'],
            'pawn_guid':refs['pawn'],'game_state_guid':refs['game_state'],
            'cache_snapshot':'evidence/driver_net_cache_world_56352.json',
            'actor_snapshot':'evidence/player_state_world_56352.json',
            'layout_snapshot':'evidence/rep_layout_world_56352.json',
            'begin_play_snapshot':'evidence/begin_play_serialization_56352.json',
            'lifecycle_snapshot':'evidence/world_lifecycle_prerequisites_56352.json',
            'id':'wrong-gs','expires_at':time.time()+25}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'data').mkdir();(root/'evidence').mkdir()
            for key,value in (('actor_snapshot',actors),('layout_snapshot',layouts),('begin_play_snapshot',serializer),('lifecycle_snapshot',lifecycle)):
                (root/command[key]).write_text(json.dumps(value))
            (root/command['cache_snapshot']).write_bytes((ROOT/command['cache_snapshot']).read_bytes())
            path=root/'data/client-restart-experiment.json'
            with patch('lab.unreal.__file__',str(root/'lab/unreal.py')),patch('tools.protocol_proof.validate_current_client_proofs') as fresh:
                invalid=copy.deepcopy(command);invalid['game_state_guid']['randomizer']+=1
                path.write_text(json.dumps(invalid));self.assertEqual(server._poll_client_restart_experiment(c,peer),[])
                command['id']='valid-gs';path.write_text(json.dumps(command))
                packets=server._poll_client_restart_experiment(c,peer)
                self.assertEqual(len(packets),1)
                self.assertEqual(fresh.call_count,4) # base actor/cache pair on reject, then all three accepted proof pairs validated.
                self.assertEqual(server._poll_client_restart_experiment(c,peer),[])
                command['id']='repeat-gs';path.write_text(json.dumps(command))
                self.assertEqual(server._poll_client_restart_experiment(c,peer),[])
        self.assertEqual(sum(kind=='game_state_begin_play_experiment' for kind,_ in events),1)
