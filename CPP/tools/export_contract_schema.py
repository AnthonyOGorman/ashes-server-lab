import sys,pathlib,json
cpp=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(cpp/'baseline'))
from lab.contracts import Contracts
c=Contracts(cpp/'baseline/evidence/client_contracts.pb');schema={}
def export(d):
    if d.full_name in schema:return
    schema[d.full_name]={'fields':{f.name:{'number':f.number,'type':f.type,'repeated':f.is_repeated,'message':f.message_type.full_name if f.message_type else None,'map':bool(f.message_type and f.message_type.GetOptions().map_entry)} for f in d.fields}}
    for f in d.fields:
        if f.message_type:export(f.message_type)
for file in c.files:
    pkg=file.package
    for d in file.message_type:export(c.pool.FindMessageTypeByName(pkg+'.'+d.name if pkg else d.name))
(cpp/'config/contracts.json').write_text(json.dumps(schema,separators=(',',':')))
print('Exported',len(schema),'installed-client message schemas')
