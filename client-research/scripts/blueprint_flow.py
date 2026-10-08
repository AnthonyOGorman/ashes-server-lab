"""Index function-local fields and partial Blueprint control-flow relationships.

Stack continuations and computed targets are explicit unresolved edges. This is
not a complete interprocedural CFG or an assertion of runtime reachability.
"""
import json,sqlite3
from collections import Counter
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite',timeout=60)
rows=db.execute('SELECT package,name,body FROM blueprint_scripts WHERE body IS NOT NULL').fetchall()
db.executescript('''
CREATE TABLE IF NOT EXISTS blueprint_fields(package TEXT,function TEXT,name TEXT,type TEXT,element_size INTEGER,flags TEXT,details TEXT);
CREATE TABLE IF NOT EXISTS blueprint_flow(package TEXT,function TEXT,source INTEGER,target INTEGER,kind TEXT,target_status TEXT);
CREATE INDEX IF NOT EXISTS blueprint_flow_function ON blueprint_flow(package,function);
DELETE FROM blueprint_fields; DELETE FROM blueprint_flow;
''')
status_counts=Counter();fields=0;edges=0
for package,name,body in rows:
    doc=json.loads(body);script=doc.get('ScriptBytecode',[])
    positions={item['StatementIndex'] for item in script}
    for prop in doc.get('ChildProperties',[]):
        db.execute('INSERT INTO blueprint_fields VALUES(?,?,?,?,?,?,?)',(package,name,prop['Name'],prop['Type'],prop.get('ElementSize'),prop.get('PropertyFlags'),json.dumps(prop)));fields+=1
    def edge(source,target,kind):
        global edges
        status='unresolved_runtime_target' if target is None else 'statement_boundary' if target in positions else 'target_requires_review'
        status_counts[status]+=1;edges+=1
        db.execute('INSERT INTO blueprint_flow VALUES(?,?,?,?,?,?)',(package,name,source,target,kind,status))
    for i,item in enumerate(script):
        token=item['Token'];at=item['StatementIndex']
        if token in ('EX_Jump','EX_JumpIfNot'):edge(at,item['CodeOffset'],'jump' if token=='EX_Jump' else 'jump_if_false')
        if token=='EX_PushExecutionFlow':edge(at,item['PushingAddress'],'push_stack_continuation')
        if token in ('EX_PopExecutionFlow','EX_PopExecutionFlowIfNot'):edge(at,None,'pop_stack_continuation' if token=='EX_PopExecutionFlow' else 'pop_stack_if_false')
        if token=='EX_ComputedJump':edge(at,None,'computed_jump')
        if token not in ('EX_Jump','EX_ComputedJump','EX_PopExecutionFlow','EX_Return','EX_EndOfScript') and i+1<len(script):edge(at,script[i+1]['StatementIndex'],'fallthrough')
db.commit()
summary={'functions':len(rows),'function_local_fields':fields,'partial_flow_edges':edges,'edge_target_status':dict(status_counts),'limitations':['Computed jumps and flow-stack returns require execution-state analysis.','Fallthrough edges are structural candidates; latent actions and exceptions are not modeled.','Switch expressions and nested expression control flow are not expanded.','ChildProperties describe function parameters/locals, not general asset defaults.']}
(RESEARCH/'index/blueprint-flow-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));db.close()
