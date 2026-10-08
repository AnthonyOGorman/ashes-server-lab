"""Independently traverse the CPP-authored offline first-floor fixture against native/capture bindings."""
import hashlib,json,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent))
from lab.unreal import BitReader
source=R.parent/'CPP/runs/settlement-probe-20261008/floor-wire.json';s=json.loads(source.read_bytes())
r=BitReader(bytes.fromhex(s['payload_hex']),s['payload_bits']);assert r.limit==1081
assert [r.read(1),r.read(1)]==[1,1];content=r.packed();content_start=r.pos
assert content==1063 and content_start==18 and r.remaining==content
assert r.read(1)==0 and r.packed()==25 and r.read(64)==0x62d024b45678 and r.packed()==0 and r.pos==99
assert r.uint(16)==13;length=r.packed();start=r.pos;assert length==962 and start==119
assert r.read(1)==1 and [r.read(8) for _ in range(3)]==[1,0,1] and r.read(1)==1 and r.read(8)==1
assert [r.read(32) for _ in range(4)]==[1,0,0,1]
assert r.read(32)==1 and r.read(64)==0x62d024b45678 and r.read(32)==0 and r.read(32)==14 and r.read(64)==0x5429e761b0070000
assert struct.unpack('<9d',r.raw(576))==(0.,0.,0.,0.,0.,0.,1.,1.,1.)
assert r.remaining==0 and r.pos==start+length==content_start+content
out={'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'capture_binding':'proofs/settlement-winstead-capture-decoded.json','native_binding':'proofs/settlement-native-verification.json',
 'passed':True,'payload_bits':r.limit,'content_bits':content,'custom_delta_bits':length,'remaining_bits':r.remaining,
 'limits':['Offline authored-fixture review only; no packet sent by research.',
 'Dynamic actor/channel envelopes, lifetime/reliable sequence, native receipt and collision require implementation/testing acceptance.']}
(R/'proofs/settlement-floor-wire-review.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
