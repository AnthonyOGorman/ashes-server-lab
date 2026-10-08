"""Local launcher tether with its observed 40-byte ARQ header and fragmentation."""
import struct
import time
import uuid

HEADER = struct.Struct('>IIIHHqqq')


def decode_tether(data):
    if len(data) < 40 or data[:2] != b'\xa5\x5a':
        raise ValueError('Invalid tether header')
    magic, sid, window, fragment, size, seq, expected, timestamp = HEADER.unpack_from(data)
    if magic >> 8 & 255 != 2 or not 1 <= magic & 255 <= 5:
        raise ValueError('Unsupported tether version or message')
    if len(data) != 40+size and magic & 255 not in (2,5):
        raise ValueError('Tether length mismatch')
    return {'kind':f'tether_{magic & 255}', 'session_id':sid, 'window':window,
            'fragment':fragment,'size':size,'seq':seq,'expected':expected,'timestamp':timestamp}


class Tether:
    def __init__(self, contracts, lobby_port, event):
        self.c, self.port, self.event = contracts,lobby_port,event
        self.clients = {}

    def header(self, kind, sid, fragment=0,size=0,seq=0,expected=0,timestamp=0):
        return HEADER.pack(0xa55a0200|kind,sid,128,fragment,size,seq,expected,timestamp)

    def handle(self,data,addr):
        parsed = decode_tether(data)
        sid = parsed['session_id']
        client = self.clients.setdefault((addr,sid), {'seq':0,'expected':0,'fragments':{},'replies':{}})
        kind = data[3]
        if kind == 5:
            processor = uuid.uuid4().hex.encode()
            return [self.header(5,sid)+struct.pack('>I',len(processor))+processor]
        if kind == 3:
            return [self.header(4,sid,expected=client['expected'])]
        if kind in (2,4): return []
        seq,fragment = parsed['seq'],parsed['fragment']
        ack = self.header(2,sid,seq=seq,expected=max(client['expected'],seq+1),timestamp=parsed['timestamp'])
        if seq in client['replies']:
            return [ack]+client['replies'][seq]
        if seq < client['expected']: return [ack]
        client['fragments'][seq] = (fragment,data[40:])
        start = client['expected']
        if start not in client['fragments']: return [ack]
        count = client['fragments'][start][0]+1
        if count > 128: raise ValueError('Tether fragment limit exceeded')
        if any(start+i not in client['fragments'] for i in range(count)): return [ack]
        pieces = [client['fragments'][start+i] for i in range(count)]
        if [p[0] for p in pieces] != list(range(count-1,-1,-1)):
            raise ValueError('Noncontiguous tether fragments')
        message = self.c.parse('ics_tether.TetherMessage',b''.join(p[1] for p in pieces))
        for i in range(count): client['fragments'].pop(start+i)
        client['expected'] = start+count
        name = message.tags.get('message_type_name','')
        if name not in ('request_open_session','request_echo'): return [ack]
        if name == 'request_open_session':
            message.tags.update({'auth_endpoint':f'http://127.0.0.1:{self.port}',
                  'auth_token':'lab-local-auth','refresh_token':'lab-local-refresh',
                  'auth0_accesstoken':'lab-local-account','account_id':'00000037000000370000003700000000',
                  'eac_deployment_id':'','eac_sandbox_id':'',
                  'grpc_metadata_magic_key':'content-md5',
                  'grpc_metadata_magic_val':'7b7b59b4dc518f6db31c3f928ac86a00',
                  'user_agent_prefix':'ashes-lab'})
            from .eos_local import local_tether_tags
            message.tags.update(local_tether_tags())
            self.event('tether_session','Local launcher session returned to client')
        payload = message.SerializeToString()
        chunks = [payload[i:i+1360] for i in range(0,len(payload),1360)]
        responses = []
        now = int(time.time()*1000)
        for i,chunk in enumerate(chunks):
            responses.append(self.header(1,sid,len(chunks)-1-i,len(chunk),client['seq'],client['expected'],now)+chunk)
            client['seq'] += 1
        client['replies'][seq] = responses
        return [ack]+responses
