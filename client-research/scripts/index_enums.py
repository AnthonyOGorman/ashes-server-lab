"""Index enum declarations from the saved generated SDK, retaining source provenance."""
import hashlib,json,re,sqlite3
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
SDK=Path(r'E:\Ashes Of Creation\AOC-SDK\SDK')
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite',timeout=60)
db.executescript('''
DROP TABLE IF EXISTS sdk_enum_values;
DROP TABLE IF EXISTS sdk_enums;
CREATE TABLE IF NOT EXISTS sdk_enums(full_name TEXT PRIMARY KEY,cpp_name TEXT,underlying_type TEXT,source TEXT,line INTEGER,source_sha256 TEXT);
CREATE TABLE IF NOT EXISTS sdk_enum_values(owner TEXT,name TEXT,value TEXT,value_expression TEXT,source TEXT,line INTEGER);
CREATE INDEX IF NOT EXISTS enum_value_owner ON sdk_enum_values(owner,value);
DELETE FROM sdk_enums; DELETE FROM sdk_enum_values;
''')
pattern=re.compile(r'// Enum ([\w.]+)[^\n]*\n(?:(?://[^\n]*\n)|\s)*enum class (\w+)\s*:\s*(\w+)\s*\{(.*?)\};',re.S)
entries=0;unknown=0
for path in sorted(SDK.glob('*.hpp')):
    raw=path.read_bytes();text=raw.decode('utf-8-sig',errors='replace');sha=hashlib.sha256(raw).hexdigest()
    for match in pattern.finditer(text):
        owner,name,underlying,body=match.groups();line=text.count('\n',0,match.start())+1
        db.execute('INSERT INTO sdk_enums VALUES(?,?,?,?,?,?)',(owner,name,underlying,str(path),line,sha))
        for member in re.finditer(r'^\s*(\w+)\s*=\s*([^,\n]+)',body,re.M):
            label,expression=member.groups();expression=expression.strip()
            try:value=str(int(expression,16 if expression.lower().startswith('0x') else 10))
            except ValueError:value=None;unknown+=1
            member_line=text.count('\n',0,match.start(4)+member.start())+1
            db.execute('INSERT INTO sdk_enum_values VALUES(?,?,?,?,?,?)',(owner,label,value,expression,str(path),member_line));entries+=1
db.commit()
summary={'enum_types':db.execute('SELECT count(*) FROM sdk_enums').fetchone()[0],'enum_values':entries,'unparsed_value_expressions':unknown,'limit':'Saved SDK declarations preserve reflected names and numeric values; their complete build provenance and runtime use remain unverified.'}
(RESEARCH/'index/enum-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));db.close()
