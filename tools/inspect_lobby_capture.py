"""Inspect exported decoded gRPC wrappers without printing account credentials."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from lab.contracts import Contracts


def fields(obj,key):
    if isinstance(obj,dict):
        for name,value in obj.items():
            if name==key: yield value
            yield from fields(value,key)
    elif isinstance(obj,list):
        for item in obj: yield from fields(item,key)


if __name__=='__main__':
    c=Contracts(Path(__file__).resolve().parent.parent/'evidence/client_contracts.pb')
    packets=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    for packet in packets:
        for value in fields(packet,'grpc.message_data'):
            try:
                wrapper=c.parse('ics_common.MessageWrapper',bytes.fromhex(value.replace(':','')))
                result={'type':wrapper.message_type_name,'system_keys':list(wrapper.system_data.tags)}
                if wrapper.message_type_name=='ics_common.SessionReply':
                    reply=c.parse(wrapper.message_type_name,wrapper.message_data)
                    result['tag_keys']=list(reply.tags)
                    result['data_keys']=list(reply.data_map)
                    result['config']={k:v for k,v in wrapper.system_data.tags.items() if 'config' in k.lower()}
                    result['config'].update({k:v for k,v in reply.data_map.items() if 'config' in k.lower()})
                print(json.dumps(result))
            except Exception: pass
