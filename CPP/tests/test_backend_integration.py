"""Python only drives independent wire tests; the service under test is C++."""
import json,pathlib,sys,urllib.request,socket,struct,time,grpc
CPP=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(CPP/'baseline'))
from lab.contracts import Contracts
from lab.unreal import decode_packet,encode_handshake,encode_packet,encode_control
c=Contracts(CPP/'baseline/evidence/client_contracts.pb');base='http://127.0.0.1:8865';checks=[]
def get(path):return json.load(urllib.request.urlopen(base+path,timeout=8))
def control(action,service=None):
    body={'action':action}
    if service:body['service']=service
    return json.load(urllib.request.urlopen(urllib.request.Request(base+'/api/control',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=12))
def check(value,name):
    assert value,name
    checks.append(name)
deadline=time.monotonic()+30
while True:
    try:
        get('/api/state')
        break
    except (OSError,ValueError):
        if time.monotonic()>=deadline:raise
        time.sleep(.25)
control('start_services')
channel=grpc.insecure_channel('127.0.0.1:16051');grpc.channel_ready_future(channel).result(timeout=5)
call=channel.stream_stream('/ics_xclient.XClientService/ProcessXClientMessage',request_serializer=lambda m:m.SerializeToString(),response_deserializer=c.cls('ics_common.MessageWrapper').FromString)
def request(name,**fields):return c.new('ics_common.MessageWrapper',message_type_name=name,message_data=c.new(name,**fields).SerializeToString())
requests=[request('ics_common.SessionRequest',request_type=1),request('ics_xclient.GetWorldsRequest'),request('ics_xclient.GetCharactersRequest',world_id='aoc-dev-minikube-minikube')]
responses=call(iter(requests),timeout=8)
for i,response in enumerate(responses):
    check(response.status_code==0,'gRPC status '+str(i))
    data=c.parse(response.message_type_name,response.message_data)
    if i==0:check('player_session_state' in data.data_map,'Exact SessionReply state sink');check(c.parse('ics_xclient.PlayerSessionState',data.data_map['player_session_state'].encode()).character_mini_records,'Own character state')
    elif i==1:check(data.worlds[0].world_id=='aoc-dev-minikube-minikube','World list')
    elif i==2:check(data.characters[0].character_name=='LabExplorer','Character list');break
channel.close()
selected=json.loads((CPP/'data/characters.json').read_text())[0]
channel=grpc.insecure_channel('127.0.0.1:16051')
play_call=channel.stream_stream('/ics_xclient.XClientService/ProcessXClientMessage',request_serializer=lambda m:m.SerializeToString(),response_deserializer=c.cls('ics_common.MessageWrapper').FromString)
play_responses=iter(play_call(iter([request('ics_common.SessionRequest',request_type=1),request('ics_xclient.PlayRequest',character_id=selected['character_id'],world_id='aoc-dev-minikube-minikube')]),timeout=8))
check(next(play_responses).status_code==0,'Play stream session opened')
play_reply=next(play_responses)
check(play_reply.status_code==0,'Lobby Play token issued')
play=c.parse(play_reply.message_type_name,play_reply.message_data)
token=play.game_connection_token
channel.close()
sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.settimeout(4)
initial={'session_id':1,'client_id':2,'min_version':3,'version':4,'sent_count':0,'network_version':12345,'network_features':0,'extension_hex':'1122334455'}
sock.sendto(encode_handshake(initial,0,0.,bytes(20)),('127.0.0.1',18089));challenge=decode_packet(sock.recv(65535));check(challenge['packet_type']==1,'Stateless challenge')
response=encode_handshake(challenge,2,challenge['timestamp'],bytes.fromhex(challenge['cookie']));sock.sendto(response,('127.0.0.1',18089));ack=decode_packet(sock.recv(65535));check(ack['packet_type']==3,'Cookie validated acknowledgement')
first=get('/api/connections')[0]['id'];sock.sendto(response,('127.0.0.1',18089));sock.recv(65535);check(get('/api/connections')[0]['id']==first,'Duplicate handshake preserves connection identity')
server,client=struct.unpack('<HH',bytes.fromhex(challenge['cookie'])[:4]);seq=client&16383;reliable=client&1023
for ident in (0,5,9):
    reliable=(reliable+1)&1023
    fields={'network_version':12345} if ident==0 else {'url':'?EncryptionToken='+token+'?Name=WrongLobbyName'} if ident==5 else {}
    packet=encode_packet(1,2,seq,server&16383,[0],encode_control(ident,**fields),reliable)
    sock.sendto(packet,('127.0.0.1',18089));reply=decode_packet(sock.recv(65535),direction='server');check('error' not in reply,'Control decode '+str(ident));seq=(seq+1)&16383
check(get('/api/connections')[0]['phase']=='joined','Hello Login Join lifecycle')
bound=get('/api/connections')[0]
check(bound['selected_character_id']==selected['character_id'] and bound['selected_character_name']==selected['character_name'],'World login binds the lobby-selected identity, independently of URL Name')
control('stop_service','lobby');state=get('/api/state');check(not next(s for s in state['services'] if s['name']=='tether')['running'],'Lobby stop cascades tether');check(next(s for s in state['services'] if s['name']=='world')['running'],'World retained independently');check(get('/api/connections')[0]['id']==first,'Lobby control preserves world state')
control('start_service','tether');check(next(s for s in get('/api/state')['services'] if s['name']=='lobby')['running'],'Tether start restores dependency')
control('stop_service','world');check(get('/api/connections')==[],'World stop withdraws sessions');control('start_service','world')
geometry=get('/api/world-geometry?radius=5000&stride=4&detail=bounds');check(geometry['segments']['terrain']>0 and geometry['segments']['collision']==0,'Terrain geometry and bounds mode')
for detail in ('lightweight','full'):
    geometry=get('/api/world-geometry?radius=5000&stride=8&detail='+detail);check(geometry['collision_detail']==detail,'Geometry mode '+detail)
sock.close();result={'passed':len(checks),'checks':checks,'backend':'native C++','real_client_verified':False};(CPP/'logs/integration-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
