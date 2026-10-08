"""Offline, build-bound pawn gate targets, tier projection and prerequisite receipts."""
import hashlib,json,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import pefile,capstone
m=json.loads((R/'index/summary.json').read_bytes())['native']
raw=Path(m['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==m['sha256']
pe=pefile.PE(data=raw,fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
targets=[]
for owner,table in [('BaseCharacter',0xb741268),('PlayerCharacter',0xb7bf4e8)]:
    for label,slot in [('Jump',0x9c8),('IsLocallyControlled',0x8d8),('IsMoveInputIgnored',0x970),('AddMovementInput',0x948)]:
        target=struct.unpack('<Q',pe.get_data(table+slot,8))[0]-base
        assert 0<target<pe.OPTIONAL_HEADER.SizeOfImage
        fragment=pe.get_data(target,256)
        lines=[f'{i.address:08x} {i.bytes.hex():24} {i.mnemonic} {i.op_str}' for i in cs.disasm(fragment,target)]
        name=f'loading-pawn-target-{target:x}'
        (R/f'proofs/{name}.asm').write_text('\n'.join(lines)+'\n')
        targets.append(dict(owner=owner,table_rva=hex(table),slot=hex(slot),label=label,
                            target_rva=hex(target),fragment_sha256=hashlib.sha256(fragment).hexdigest(),
                            boundary='256-byte discovery prefix; not a complete function claim',instructions=lines))
(R/'proofs/loading-pawn-targets.json').write_text(json.dumps(dict(exe_sha256=m['sha256'],targets=targets),indent=2)+'\n')
sources=[]
for rel in ['decompiled/settlement-streaming/function_65a8f40.c',
            'decompiled/settlement-assets/function_65ac950.c',
            'decompiled/settlement-level-creation-retry/function_65a25a0.c',
            'decompiled/settlement-streaming/function_65a1430.c']:
    p=R/rel;text=p.read_text();assert m['sha256'] in text and 'Decompilation failed:' not in text
    sources.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
receipt=dict(exe_sha256=m['sha256'],sources=sources,
    established_entry_conditions=['OnRep65A8F40 requires initialized byte+508 and nonzero NodeGuid+500.',
      'Resolver consumes item compound+10/transform+30 and replicator level/culture/season/tags.',
      'Async refresh occurs on changed cached metadata/tags or version; unchanged version and metadata returns.'],
    conclusion='Reviewed settlement entry/load dispatch does not gate on pawn autonomy or character Stats; early dispatch is supported as a static inference.',
    limits=['Dependent design-data/world/async availability remains required.',
      'Absence of a direct pawn check does not prove all transitive dependencies absent.',
      'Fresh Role1 loaded-level visibility/transform and native floor test required before release.',
      'No client calls, process access, inputs, packets or CPP changes.'])
(R/'proofs/settlement-loading-prerequisites.json').write_text(json.dumps(receipt,indent=2)+'\n')
catalog_path=R/'proofs/settlement-tier-profiles.json';catalog=json.loads(catalog_path.read_bytes())
assert catalog['build_sha256']==m['sha256']
win=next(n for n in catalog['nodes'] if n['name']=='Verra_RVR_Winstead')
thin={k:v for k,v in win.items() if k!='tiers'};thin['tiers']=[]
for tier in win['tiers']:
    row={k:v for k,v in tier.items() if k not in ('props','service_plots')}
    row['props']=[]
    for prop in tier['props']:
        p={k:v for k,v in prop.items() if k!='selection_key'};p['selected_definitions']=[]
        for selection in catalog['selection_pool'][prop['selection_key']]:
            definition=catalog['definition_pool'][selection['definition_id']]
            p['selected_definitions'].append(dict(selection,assets=[dict(path=a['path'],inventory_classes=a['inventory_classes'],instance_count=len(a['instances'])) for a in definition['assets']]))
        row['props'].append(p)
    row['service_plots']=tier['service_plots']
    thin['tiers'].append(row)
keys={k for tier in win['tiers'] for plot in tier['service_plots'] for k in plot['building_candidate_keys']+[plot['empty_building_key']] if k}
out=dict(build_sha256=m['sha256'],source=dict(path=str(catalog_path),sha256=hashlib.sha256(catalog_path.read_bytes()).hexdigest()),
         profile=catalog['profile'],node=thin,building_pool={k:catalog['building_pool'][k] for k in sorted(keys)},limits=catalog['limits']+[
             'Thin projection excludes asset instance buffers; client-local definitions retain them.',
             'Candidate building state/selection is not a packet-authoring mandate.'])
dest=R/'proofs/winstead-tier-recipes.json';dest.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(targets=[{k:v for k,v in t.items() if k!='instructions'} for t in targets],thin_bytes=dest.stat().st_size),indent=2));pe.close()
