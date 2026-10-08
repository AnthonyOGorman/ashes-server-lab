"""Index decoded Blueprint expressions and call references; preserve parser confidence."""
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite')
db.executescript('''
CREATE TABLE IF NOT EXISTS blueprint_scripts(package TEXT,name TEXT,status TEXT,flags TEXT,expression_count INTEGER,body TEXT,PRIMARY KEY(package,name));
CREATE TABLE IF NOT EXISTS blueprint_calls(package TEXT,function TEXT,token TEXT,target_name TEXT,target_path TEXT,native_candidate_rva INTEGER);
CREATE INDEX IF NOT EXISTS blueprint_calls_target ON blueprint_calls(target_name);
CREATE TABLE IF NOT EXISTS blueprint_tokens(token TEXT PRIMARY KEY,count INTEGER);
DELETE FROM blueprint_scripts; DELETE FROM blueprint_calls; DELETE FROM blueprint_tokens;
''')
labels={name:rva for rva,name in db.execute('SELECT rva,name FROM native_labels WHERE kind="native_registration_candidate"')}
tokens=Counter();statuses=Counter();top_level=0;duplicates=0
def visit(node,package,function):
    if isinstance(node,dict):
        token=node.get('Token')
        if token:
            tokens[token]+=1
            if token in ['EX_CallMath','EX_FinalFunction','EX_LocalFinalFunction','EX_VirtualFunction','EX_LocalVirtualFunction','EX_CallMulticastDelegate']:
                target=node.get('Function',node.get('FunctionName'))
                name=target.get('ObjectName') if isinstance(target,dict) else str(target)
                path=target.get('ObjectPath') if isinstance(target,dict) else None
                label=None
                if path and path.startswith('/Script/') and name and ':' in name:
                    match=re.search(r"'([^']+)'",name)
                    if match:
                        owner,method=match.group(1).split(':',1)
                        label=path[len('/Script/'):] + '.' + owner + '.' + method
                db.execute('INSERT INTO blueprint_calls VALUES(?,?,?,?,?,?)',(package,function,token,name,path,labels.get(label)))
        for value in node.values():visit(value,package,function)
    elif isinstance(node,list):
        for value in node:visit(value,package,function)
for line in (RESEARCH/'index/blueprint-bytecode.jsonl').open(encoding='utf-8-sig'):
    row=json.loads(line);package=row['package'];name=row.get('name','<package>');status=row['status'];body=row.get('script_json')
    if body:
        document=json.loads(body);script=document.get('ScriptBytecode',[])
        if document.get('Name')!=name:
            status='name_mismatch_requires_review'
        if not script or script[-1].get('Token')!='EX_EndOfScript':
            status='script_termination_requires_review'
        indexes=[x['StatementIndex'] for x in script if 'StatementIndex' in x]
        if indexes!=sorted(set(indexes)):
            status='statement_order_requires_review'
        top_level+=len(script);visit(script,package,name)
    db.execute('INSERT INTO blueprint_scripts VALUES(?,?,?,?,?,?)',(package,name,status,row.get('flags'),row.get('expressions',0),body));statuses[status]+=1
db.executemany('INSERT INTO blueprint_tokens VALUES(?,?)',tokens.items());db.commit()
summary={'functions':sum(statuses.values()),'status':dict(statuses),'top_level_expressions':top_level,'nested_expressions':sum(tokens.values()),'call_references':db.execute('SELECT count(*) FROM blueprint_calls').fetchone()[0],'calls_with_native_candidate':db.execute('SELECT count(*) FROM blueprint_calls WHERE native_candidate_rva IS NOT NULL').fetchone()[0],'most_common_tokens':dict(tokens.most_common(20)),'limits':['Game-specific parser and zero reflected Object/Field/Struct/Function property schemas were used only for UFunction exports.','EndOfScript and ascending statement offsets validate structural decoding, not runtime behavior or correctness of every operand/type.','Virtual calls and delegate dispatch require runtime/context resolution.','Native targets inherit static registration candidate confidence.']}
(RESEARCH/'index/bytecode-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));db.close()
