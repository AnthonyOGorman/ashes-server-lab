"""Fresh lobby service using descriptors extracted from this installed client."""
import json
import secrets
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import grpc

WORLD = 'aoc-dev-minikube-minikube'
MAP = '/Game/Levels/Verra_World_Master/Verra_World_Master'
ACCOUNT = '00000037000000370000003700000000'


class Lobby:
    def __init__(self, contracts, store, record, event, port=15051, world_port=17089):
        self.c, self.store, self.record, self.event = contracts, store, record, event
        self.port, self.world_port = port, world_port
        self.server = None
        self.tokens = {}
        self.seed()

    def seed(self):
        if self.store.query('SELECT id FROM characters'):
            return
        # A valid customization object; no old character credentials or inventories.
        char = self.c.new('aoc_character.Character', character_id=uuid.uuid4().hex,
                          character_name='LabExplorer', character_name_lcase='labexplorer',
                          account_id=ACCOUNT, auth0_id='local-lab', world_id=WORLD,
                          version=1, revision=1, record_status='active',
                          created_msec=int(time.time()*1000), updated_msec=int(time.time()*1000))
        char.character_info.level = 1
        char.character_info.primary_class = 1
        char.character_info.gender = 1
        char.character_info.race = 1
        char.character_info.json_blob_map.map['CustomizationDataKey'] = json.dumps({
            'presetGuid':'0', 'randomSeed':1454, 'gender':'Male', 'race':'Kaelar', 'class':'Fighter',
            'skinSet':2, 'faceMorphWeightMaps':{}, 'sectionsValues':{}, 'decalData':[],
            'decalBlendGroups':[], 'bIsHelmetVisible':True, 'bIsCapeVisible':True})
        char.character_location.map = MAP
        char.character_location.version = 1
        char.character_location.location.x = -660384.0
        char.character_location.location.y = 389360.28125
        char.character_location.location.z = 13622.9404296875
        char.experience_data.experience_data_version = 1
        self.save_character(char)

    def save_character(self, char):
        self.store.execute('INSERT OR REPLACE INTO characters VALUES(?,?,?,?)',
                           (char.character_id, char.character_name, char.world_id, char.SerializeToString()))

    def characters(self, world=WORLD):
        return [self.c.parse('aoc_character.Character', row['proto']) for row in
                self.store.query('SELECT proto FROM characters WHERE world=? ORDER BY name', (world,))]

    def config(self):
        ping = {'ping_period_msec':1000, 'ping_hosts':['127.0.0.1']}
        # Verified SessionReply sink lookup in this installed executable.
        return {'ics_ping_client_config.json':json.dumps(ping)}

    def world(self, reply):
        world = reply.worlds.add()
        world.world_id, world.world_display_name = WORLD, 'Ashes Lab'
        world.available = True
        world.character_count = len(self.characters())
        return reply

    def wrap(self, name, payload, request=None, status=0):
        reply = self.c.new('ics_common.MessageWrapper', message_type_name=name,
                           message_data=payload.SerializeToString(), status_code=status)
        if request is not None:
            reply.system_data.CopyFrom(request.system_data)
        reply.system_data.tags['server_tracking_id'] = str(time.time_ns())
        return reply

    def process(self, request, session):
        name = request.message_type_name
        try:
            payload = self.c.parse(name, request.message_data)
        except (KeyError, ValueError):
            return [self.c.new('ics_common.MessageWrapper', message_type_name=name, status_code=30)]
        short = name.rsplit('.',1)[-1]
        replyname = name.replace('Request','Reply')
        if short == 'SessionRequest':
            session['open'] = payload.request_type == 1
            reply = self.c.new('ics_common.SessionReply', request_type=payload.request_type, result_code=0)
            reply.tags.update(payload.tags)
            reply.tags.update({'account_id':ACCOUNT, 'session_token':secrets.token_hex(16)})
            reply.data_map.update(self.config())
            reply.data_map['server_time'] = str(int(time.time()*1000))
            reply.data_string = 'session_opened' if session['open'] else 'session_closed'
            if session['open']:
                self.event('session_request', 'Client requested a local XClient session')
            if session['open']:
                state = self.c.new('ics_xclient.PlayerSessionState')
                for char in self.characters():
                    mini = state.character_mini_records.add()
                    mini.character_id, mini.character_name, mini.world_id = char.character_id, char.character_name, WORLD
                # Client ParseFromString reads this map value directly. This
                # initial ASCII-only state is valid UTF-8 without transformation.
                reply.data_map['player_session_state'] = state.SerializeToString().decode('utf-8')
            return [self.wrap(replyname, reply, request)]
        if short == 'KeepAliveMessage':
            return [self.wrap(name, payload, request)]
        if not session.get('open'):
            return [self.wrap(name, payload, request, status=43)]
        if short == 'CheckGameVersionRequest':
            session['version'] = payload.game_version
            reply = self.c.new(replyname, supported=True, message='Local lab client')
        elif short == 'GetWorldsRequest':
            reply = self.world(self.c.new(replyname))
        elif short == 'GameClientInterestEvent':
            return [self.wrap('ics_xclient.WorldStatusEvent', self.world(self.c.new('ics_xclient.WorldStatusEvent')))]
        elif short == 'GetCharactersRequest':
            reply = self.c.new(replyname)
            for char in self.characters(payload.world_id or WORLD):
                reply.characters.add().CopyFrom(char)
            self.event('character_list_request', 'Client requested the local character list')
        elif short == 'CheckCharacterNameRequest':
            available = bool(payload.character_name.strip()) and not self.store.query('SELECT id FROM characters WHERE name=? COLLATE NOCASE',(payload.character_name,))
            reply = self.c.new(replyname, character_name=payload.character_name, available=available)
        elif short == 'CreateCharacterRequest':
            if payload.world_id != WORLD or not payload.character_name.strip() or self.store.query('SELECT id FROM characters WHERE name=? COLLATE NOCASE',(payload.character_name,)):
                return [self.wrap(name, payload, request, status=24)]
            char = self.c.new('aoc_character.Character', version=1,revision=1,character_id=uuid.uuid4().hex,
                              character_name=payload.character_name,character_name_lcase=payload.character_name.lower(),
                              world_id=WORLD,account_id=ACCOUNT,record_status='active',created_msec=int(time.time()*1000))
            info = payload.create_character_info
            char.character_info.json_blob_map.CopyFrom(info.json_blob_map)
            char.character_info.gender, char.character_info.race, char.character_info.primary_class = info.gender,info.race,info.primary_class
            char.character_info.level = 1
            self.save_character(char)
            reply = self.c.new(replyname, character_id=char.character_id, character_name=char.character_name,world_id=WORLD)
            reply.character_info.CopyFrom(char.character_info)
        elif short in ('SelectCharacterRequest','PlayRequest','CanDeleteCharacterRequest','DeleteCharacterRequest'):
            rows = self.store.query('SELECT proto FROM characters WHERE id=?', (payload.character_id,))
            if not rows:
                return [self.wrap(name,payload,request,status=59)]
            if short == 'PlayRequest':
                if payload.world_id != WORLD:
                    return [self.wrap(name,payload,request,status=24)]
                token = secrets.token_hex(16)
                self.tokens[token] = (payload.character_id,time.monotonic()+120)
                url = f'127.0.0.1:{self.world_port}?map={MAP}&driver=/Script/IntrepidNet.IntrepidNetDriver&world_id={WORLD}&EncryptionToken={token}'
                reply = self.c.new(replyname,game_connection_token=token,game_connection_string=url)
                self.event('play_requested','Client requested a world connection')
            else:
                reply = self.c.new(replyname,character_id=payload.character_id)
                if short == 'CanDeleteCharacterRequest': reply.can_delete = True
                elif short == 'DeleteCharacterRequest':
                    self.store.execute('DELETE FROM characters WHERE id=?',(payload.character_id,))
                else: session['character_id'] = payload.character_id
        elif short == 'AuthRefreshRequest':
            reply = self.c.new(replyname, auth_token=secrets.token_hex(16), refresh_token=secrets.token_hex(16))
        elif short == 'PlayEndRequest':
            reply = self.c.new(replyname)
        else:
            return [self.wrap(name,payload,request,status=23)]
        return [self.wrap(replyname,reply,request)]

    def stream(self, requests, context):
        session = {'open':False}
        for request in requests:
            self.record('lobby','C2S',request.SerializeToString(), request.message_type_name, self.c.describe(request))
            try:
                responses = self.process(request,session)
            except Exception as exc:
                self.event('service_error', f'Lobby {request.message_type_name}: {type(exc).__name__}: {exc}')
                responses = [self.c.new('ics_common.MessageWrapper',message_type_name=request.message_type_name,status_code=22)]
            for response in responses:
                self.record('lobby','S2C',response.SerializeToString(),response.message_type_name,self.c.describe(response))
                yield response

    def start(self):
        self.server = grpc.server(ThreadPoolExecutor(max_workers=8))
        handler = grpc.stream_stream_rpc_method_handler(self.stream,
                    request_deserializer=self.c.cls('ics_common.MessageWrapper').FromString,
                    response_serializer=lambda m:m.SerializeToString())
        self.server.add_generic_rpc_handlers([grpc.method_handlers_generic_handler('ics_xclient.XClientService',{'ProcessXClientMessage':handler})])
        if not self.server.add_insecure_port(f'127.0.0.1:{self.port}'):
            raise OSError('Cannot bind local lobby port')
        self.server.start()

    def stop(self):
        if self.server: self.server.stop(0).wait(3)
