"""Prioritize a bounded direct-call neighborhood for semantic review.

Exception fragments normalize to their recorded unwind roots. An incomplete
static graph is saved with provenance; indirect dispatch remains unresolved.
"""
import argparse,collections,json,sqlite3
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('seed');parser.add_argument('--depth',type=int,default=2)
parser.add_argument('--max',type=int,default=128);parser.add_argument('--reason',required=True)
args=parser.parse_args()
if not 0<=args.depth<=4 or not 1<=args.max<=256:parser.error('depth must be 0..4 and max 1..256')
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite',timeout=60)
db.execute('CREATE TABLE IF NOT EXISTS review_seeds(begin INTEGER PRIMARY KEY,reason TEXT,seed TEXT,depth INTEGER)')
if args.seed.startswith('0x'):seed=int(args.seed,16)
else:
    matches=db.execute('SELECT DISTINCT rva FROM native_labels WHERE name=? AND kind="native_registration_candidate"',(args.seed,)).fetchall()
    if len(matches)!=1:raise SystemExit(f'Seed needs one candidate target; found {len(matches)}')
    seed=matches[0][0]
def normalize(rva):
    row=db.execute('SELECT root_begin FROM native_unwind WHERE begin=? AND status="header_parsed"',(rva,)).fetchone()
    return row[0] if row else rva
queue=collections.deque([(normalize(seed),0)]);seen=set();nodes=[];edges=[];unresolved=0
while queue and len(nodes)<args.max:
    begin,depth=queue.popleft()
    if begin in seen:continue
    seen.add(begin)
    bounds=db.execute('SELECT end,boundary FROM decompile_queue WHERE begin=?',(begin,)).fetchone()
    if not bounds:
        nodes.append({'rva':hex(begin),'depth':depth,'status':'no_indexed_entry_bounds'});continue
    names=[r[0] for r in db.execute('SELECT name FROM native_labels WHERE rva=? AND kind!="function_metadata_accessor"',(begin,))]
    nodes.append({'rva':hex(begin),'depth':depth,'names':names,'boundary':bounds[1]})
    db.execute('INSERT OR REPLACE INTO review_seeds VALUES(?,?,?,?)',(begin,args.reason,args.seed,depth))
    sources=[r[0] for r in db.execute('SELECT begin FROM native_unwind WHERE root_begin=?',(begin,))] or [begin]
    placeholders=','.join('?' for _ in sources)
    for source,at,target,kind in db.execute('SELECT source_begin,instruction_rva,target_rva,kind FROM code_refs WHERE source_begin IN ('+placeholders+') AND kind IN ("direct_call","direct_jmp","indirect_call","indirect_jmp")',sources):
        if target is None:unresolved+=1;continue
        owner=normalize(target)
        if owner==begin:continue
        edges.append({'source':hex(source),'instruction':hex(at),'target':hex(target),'unwind_root':hex(owner),'kind':kind})
        if depth<args.depth and owner not in seen:queue.append((owner,depth+1))
db.commit()
result={'seed':args.seed,'reason':args.reason,'nodes':nodes,'direct_edges':edges,'indirect_sites_in_selected_nodes':unresolved,'node_limit':args.max,'truncated_frontier':len(queue),'limitations':['Unwind roots group compiler fragments, not every logical function.','Only direct calls/jumps with known target entries are followed.','Queued/decompiled code still requires semantic review.']}
output=RESEARCH/'proofs'/('trace_'+hex(seed)[2:]+'.json');output.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'seed':args.seed,'nodes':len(nodes),'edges':len(edges),'unresolved_indirect_sites':unresolved,'truncated_frontier':len(queue),'output':str(output)},indent=2));db.close()
