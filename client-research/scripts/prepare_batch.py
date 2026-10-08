"""Prepare representative client code ranges plus directly referenced implementations."""
import json
import sqlite3
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite')
seeds=[
 ('GameSystemsPlugin.InventorySlotBase','GetItemInfo'),
 ('GameSystemsPlugin.InventorySlotBase','HandleCooldown'),
 ('GameSystemsPlugin.QuestConsumerComponent','OnRep_ReplicatedQuestCache'),
 ('GameSystemsPlugin.QuestConsumerComponent','HandleAbilityUsed'),
 ('GameSystemsPlugin.AoCCharacterCreationController','IsValidCharacterName'),
 ('GameSystemsPlugin.AoCCharacterCreationController','RequestPlayCharacter'),
 ('GameSystemsPlugin.AoCCharacterMovement','SetSprintRequest'),
 ('GameSystemsPlugin.FastCraftingMenu',None),
 ('GameSystemsPlugin.CraftingStationBase',None),
 ('GameSystemsPlugin.AoCAbilityComponent',None),
 ('GameSystemsPlugin.AoCLayoutBase','AcceptTradeRequest'),
 ('GameSystemsPlugin.AoCPlayerController','ClientSendNodeInventoryData')
]
selected={}
seed_info=[]
for owner,name in seeds:
    query='SELECT name,target_rva FROM native_registration_pairs WHERE inferred_owner=? AND orientation="native_registration_candidate"'
    params=[owner]
    if name:
        query+=' AND name=?';params.append(name)
    query+=' ORDER BY name LIMIT 1'
    rows=db.execute(query,params).fetchall()
    for method,target in rows:
        label=owner+'.'+method
        native=db.execute('SELECT begin,end FROM native_ranges WHERE begin<=? AND end>?',(target,target)).fetchone()
        boundary='PE_exception_range'
        if not native:
            native=db.execute('SELECT begin,end FROM entry_blocks WHERE begin=?',(target,)).fetchone()
            boundary='bounded_entry_block_only'
        seed_info.append({'candidate':label,'target':hex(target),'range':list(map(hex,native)) if native else None,'boundary_evidence':boundary})
        if not native or native[1]-native[0]>65536:continue
        selected[native[0]]=(native[1],label+'; '+boundary)
        # One level of direct calls/tail-jumps, excluding broad fan-out.
        refs=db.execute('SELECT DISTINCT target_rva FROM code_refs WHERE source_begin=? AND kind IN ("direct_call","direct_jmp")',(native[0],)).fetchall()
        for (callee,) in refs[:12]:
            r=db.execute('SELECT begin,end FROM native_ranges WHERE begin=?',(callee,)).fetchone()
            if r and r[1]-r[0]<=65536:
                selected.setdefault(r[0],(r[1],'direct reference from '+label))
out=RESEARCH/'batches';out.mkdir(exist_ok=True)
items=list(selected.items())[:128]
(out/'initial.tsv').write_text('\n'.join(f'{hex(start)}\t{hex(end)}\t{label}' for start,(end,label) in items)+'\n',encoding='utf-8')
(out/'initial-seeds.json').write_text(json.dumps(seed_info,indent=2),encoding='utf-8')
print(json.dumps({'ranges':len(items),'seeds':seed_info},indent=2))
