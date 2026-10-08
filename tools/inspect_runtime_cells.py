"""Bounded read-only reflected runtime-cell inventory for one live world partition."""
import argparse
import json
import re
from pathlib import Path
from inspect_character_appearance import AppearanceProbe
from dump_runtime_reflection import Reader, ReadError
from protocol_proof import EXPECTED_EXE, client_proof, validate_current_client_proofs

def inspect(pid, source):
    saved=json.loads(Path(source).read_text())
    validate_current_client_proofs(pid,saved,saved)
    partition=saved['world_partition']['identity']
    reader=Reader(pid,EXPECTED_EXE,budget=128*1024*1024)
    try:
        probe=AppearanceProbe(reader)
        if probe.identity(int(partition['address'],16)) != partition:
            raise ReadError('Partition identity changed')
        loaded_names={entry['identity']['name'].removeprefix('WorldPartitionLevelStreaming_')
            for entry in saved['streaming_levels']}
        result={'pid':pid,'client_proof':client_proof(pid),'functions_invoked':False,'partition':partition,
            'cells':[],'same_partition_count':0,'selection':'current streaming-cell names plus first eight samples'}
        for address,obj in probe.reflection.objects():
            if obj['name'].startswith('Default__'):
                continue
            cls=probe.reflection.class_name(obj['class_address'])
            if not cls.startswith('WorldPartitionRuntime') or 'Cell' not in cls or 'CellData' in cls:
                continue
            identity=probe.identity(address)
            # Exact ownership binds the inventory to this live partition.
            outer=identity['outer_address']
            owners=[]
            for _ in range(4):
                if not outer:break
                owner=probe.identity(int(outer,16))
                owners.append(owner['address'])
                outer=owner['outer_address']
            if partition['address'] not in owners:
                continue
            result['same_partition_count']+=1
            if result['same_partition_count']>65536:
                raise ReadError('Partition cell inventory exceeds bound')
            if identity['name'] not in loaded_names and len(result['cells'])>=8:
                continue
            names=[n for n in probe.properties_for(address) if re.search(r'hlod|load|always|stream|level|cell|data|grid|visible|state',n,re.I)][:64]
            entry={'identity':identity,'fields':probe.fields(address,names)}
            data=entry['fields'].get('RuntimeCellData',{}).get('value')
            if isinstance(data,dict) and data.get('address'):
                at=int(data['address'],16)
                names=[n for n in probe.properties_for(at) if re.search(r'grid|bound|position|extent|hlod|load|stream|spatial|level|cell|layer',n,re.I)][:64]
                entry['cell_data']={'identity':data,'fields':probe.fields(at,names)}
            result['cells'].append(entry)
        result['completed_client_proof']=client_proof(pid)
        result['bytes_read']=reader.bytes_read
        return result
    finally:reader.close()

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',required=True,type=int)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    d=inspect(a.pid,a.source)
    a.output.write_text(json.dumps(d,indent=2),encoding='utf-8')
    print(json.dumps({'cells':len(d['cells']),'bytes_read':d['bytes_read']}))
