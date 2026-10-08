import tempfile
import unittest
from pathlib import Path
import grpc
from lab.contracts import Contracts
from lab.storage import Store
from lab.lobby import Lobby, WORLD
from lab.tether import Tether, HEADER, decode_tether

ROOT=Path(__file__).resolve().parent.parent


class LobbyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=Contracts(ROOT/'evidence/client_contracts.pb')
        self.store=Store(Path(self.temp.name)/'test.db')
        self.events=[]
        self.lobby=Lobby(self.c,self.store,lambda *a:None,lambda *a:self.events.append(a),port=0)

    def tearDown(self):
        self.lobby.stop()
        self.store.db.close()
        self.temp.cleanup()

    def request(self,name,**fields):
        full='ics_common.'+name if name in ('SessionRequest','KeepAliveMessage') else 'ics_xclient.'+name
        wrapper=self.c.new('ics_common.MessageWrapper',message_type_name=full,
                           message_data=self.c.new(full,**fields).SerializeToString())
        wrapper.system_data.tags['client_tracking_id']='test-17'
        return wrapper

    def test_real_grpc_stream_serialization_and_correlation(self):
        self.lobby.port=0
        # Run the genuine generic gRPC handler, including stream framing.
        from concurrent.futures import ThreadPoolExecutor
        server=grpc.server(ThreadPoolExecutor(max_workers=2))
        cls=self.c.cls('ics_common.MessageWrapper')
        handler=grpc.stream_stream_rpc_method_handler(self.lobby.stream,request_deserializer=cls.FromString,
                                                       response_serializer=lambda m:m.SerializeToString())
        server.add_generic_rpc_handlers([grpc.method_handlers_generic_handler('ics_xclient.XClientService',{'ProcessXClientMessage':handler})])
        port=server.add_insecure_port('127.0.0.1:0')
        server.start()
        try:
            with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
                call=channel.stream_stream('/ics_xclient.XClientService/ProcessXClientMessage',
                                           request_serializer=lambda m:m.SerializeToString(),response_deserializer=cls.FromString)
                responses=list(call(iter([self.request('SessionRequest',request_type=1),self.request('GetWorldsRequest'),self.request('GetCharactersRequest',world_id=WORLD)]),timeout=5))
            names=[x.message_type_name for x in responses]
            self.assertIn('ics_xclient.GetCharactersReply',names)
            worlds=self.c.parse('ics_xclient.GetWorldsReply',responses[-2].message_data)
            self.assertEqual(worlds.worlds[0].world_id,WORLD)
            self.assertEqual(responses[-1].system_data.tags['client_tracking_id'],'test-17')
            chars=self.c.parse('ics_xclient.GetCharactersReply',responses[-1].message_data)
            self.assertEqual(chars.characters[0].character_name,'LabExplorer')
        finally: server.stop(0).wait()

    def test_unknown_character_never_gets_world_token(self):
        session={'open':True}
        result=self.lobby.process(self.request('PlayRequest',character_id='missing',world_id=WORLD),session)
        self.assertEqual(result[0].status_code,59)
        self.assertFalse(self.lobby.tokens)

    def test_lobby_requires_session_and_persists_creation(self):
        result=self.lobby.process(self.request('GetCharactersRequest',world_id=WORLD),{'open':False})
        self.assertEqual(result[0].status_code,43)
        result=self.lobby.process(self.request('CreateCharacterRequest',character_name='Fresh',world_id=WORLD),{'open':True})
        self.assertEqual(result[0].status_code,0)
        self.assertEqual(len(self.lobby.characters()),2)
        other=Store(Path(self.temp.name)/'test.db')
        self.assertEqual(len(other.query('SELECT id FROM characters')),2)
        other.db.close()

    def test_tether_roundtrip_fragmented_and_duplicate(self):
        tether=Tether(self.c,15051,lambda *a:None)
        msg=self.c.new('ics_tether.TetherMessage')
        msg.tags['message_type_name']='request_open_session'
        msg.data_string='x'*2000
        payload=msg.SerializeToString()
        chunks=[payload[:1360],payload[1360:]]
        packets=[HEADER.pack(0xa55a0201,13,128,1-i,len(chunk),i,0,1710000000000)+chunk for i,chunk in enumerate(chunks)]
        first=tether.handle(packets[0],('127.0.0.1',30000))
        self.assertEqual(len(first),1)
        replies=tether.handle(packets[1],('127.0.0.1',30000))
        response=self.c.parse('ics_tether.TetherMessage',b''.join(x[40:] for x in replies if x[3]==1))
        self.assertEqual(response.tags['auth_endpoint'],'http://127.0.0.1:15051')
        self.assertEqual(response.data_string,'x'*2000)
        self.assertEqual(tether.handle(packets[1],('127.0.0.1',30000))[1:],replies[1:])
        with self.assertRaises(ValueError): decode_tether(packets[0][:-1])


if __name__=='__main__': unittest.main()
