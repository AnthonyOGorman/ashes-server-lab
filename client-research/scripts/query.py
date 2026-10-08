"""Search the local client evidence index without modifying it."""
import argparse
import json
import sqlite3
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('kind', choices=['sdk','types','properties','enums','strings','assets','blueprints','scripts','managed','managed-all','fields','flow','unwind','labels','rva','callers','callees','contracts','sql'])
parser.add_argument('query')
parser.add_argument('--limit', type=int, default=30)
args = parser.parse_args()
db = sqlite3.connect((RESEARCH/'index/client-index.sqlite').as_uri()+'?mode=ro', uri=True,timeout=60)
db.row_factory = sqlite3.Row
limit = max(1, min(args.limit, 1000))
like = '%'+args.query+'%'
queries = {
    'sdk': ('SELECT * FROM sdk_functions WHERE full_name LIKE ? ORDER BY full_name LIMIT ?', (like,limit)),
    'types': ('SELECT * FROM sdk_types WHERE full_name LIKE ? OR cpp_name LIKE ? ORDER BY full_name LIMIT ?', (like,like,limit)),
    'properties': ('SELECT * FROM sdk_properties WHERE owner LIKE ? OR name LIKE ? LIMIT ?', (like,like,limit)),
    'enums': ('SELECT * FROM sdk_enum_values WHERE owner LIKE ? OR name LIKE ? LIMIT ?', (like,like,limit)),
    'strings': ('SELECT id,printf("0x%x",rva) AS rva,encoding,section,value FROM strings WHERE value LIKE ? LIMIT ?', (like,limit)),
    'contracts': ('SELECT * FROM contracts WHERE full_name LIKE ? LIMIT ?', (like,limit)),
    'assets': ('SELECT package,name,cls FROM assets WHERE package LIKE ? OR name LIKE ? LIMIT ?', (like,like,limit)),
    'blueprints': ('SELECT package,name,cls,size,serial_offset FROM package_exports WHERE cls="Function" AND (package LIKE ? OR name LIKE ?) LIMIT ?', (like,like,limit)),
    'scripts': ('SELECT package,name,status,flags,expression_count FROM blueprint_scripts WHERE package LIKE ? OR name LIKE ? LIMIT ?', (like,like,limit)),
    'managed': ('SELECT assembly,token,rva,name,attributes FROM managed_methods WHERE name LIKE ? OR assembly LIKE ? LIMIT ?', (like,like,limit)),
    'managed-all': ('SELECT path,owner,name,printf("0x%x",token) AS token,printf("0x%x",rva) AS rva,il_bytes,body_error FROM all_managed_methods WHERE name LIKE ? OR owner LIKE ? LIMIT ?', (like,like,limit)),
    'fields': ('SELECT package,function,name,type,element_size,flags FROM blueprint_fields WHERE package LIKE ? OR function LIKE ? OR name LIKE ? LIMIT ?', (like,like,like,limit)),
    'flow': ('SELECT * FROM blueprint_flow WHERE package LIKE ? OR function LIKE ? LIMIT ?', (like,like,limit)),
    'labels': ('SELECT printf("0x%x",n.rva) AS rva,n.name,n.kind,q.status,q.output FROM native_labels n LEFT JOIN decompile_queue q ON q.begin=n.rva WHERE n.name LIKE ? LIMIT ?', (like,limit)),
}
if args.kind in queries:
    sql, params = queries[args.kind]
elif args.kind == 'unwind':
    sql, params = 'SELECT * FROM native_unwind WHERE begin=? OR root_begin=? LIMIT ?', (int(args.query,0),int(args.query,0),limit)
elif args.kind == 'rva':
    rva = int(args.query, 0)
    sql, params = 'SELECT printf("0x%x",begin) AS begin,printf("0x%x",end) AS end,bytes,sha256 FROM native_ranges WHERE begin<=? AND end>?', (rva,rva)
elif args.kind == 'callers':
    sql, params = 'SELECT printf("0x%x",source_begin) AS source,printf("0x%x",instruction_rva) AS instruction,kind,detail FROM code_refs WHERE target_rva=? LIMIT ?', (int(args.query,0),limit)
elif args.kind == 'callees':
    sql, params = 'SELECT printf("0x%x",instruction_rva) AS instruction,CASE WHEN target_rva IS NOT NULL THEN printf("0x%x",target_rva) END AS target,kind,detail FROM code_refs WHERE source_begin=? LIMIT ?', (int(args.query,0),limit)
else:
    sql, params = args.query, ()
for row in db.execute(sql, params):
    print(json.dumps(dict(row), ensure_ascii=True))
db.close()
