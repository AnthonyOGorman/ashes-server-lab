"""Make cooked default input declarations reviewable; do not infer live user bindings."""
import csv,json,re,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[1]
db=sqlite3.connect(R/'index/client-index.sqlite',timeout=60)
def base(key):return re.sub(r'\[\d+\]$','',key)
def props(doc):return {base(k):v for k,v in doc.get('Properties',{}).items()}
rows=db.execute('SELECT package,name,cls,status,body FROM asset_value_candidates WHERE cls IN ("InputAction","AOCInputMappingContext","PlayerInputConfig")').fetchall()
actions={};bindings=[];config=[]
for package,name,cls,status,body in rows:
    values=props(json.loads(body))
    if cls=='InputAction':actions[name]={'package':package,'name':name,'status':status,**values}
    if cls=='PlayerInputConfig':
        for field,target in values.items():
            config.append(dict(package=package,field=field,target=json.dumps(target),status=status))
    if cls=='AOCInputMappingContext':
        for idx,item in enumerate(values.get('Mappings',[])):
            v={base(k):value for k,value in item.items()};action=v.get('Action') or {}
            action_name=action.get('ObjectName','').split("'")[-2] if "'" in action.get('ObjectName','') else action.get('ObjectName')
            bindings.append(dict(package=package,index=idx,action=action_name,action_path=action.get('ObjectPath'),key=(v.get('Key') or {}).get('KeyName'),triggers=json.dumps(v.get('Triggers')),modifiers=json.dumps(v.get('Modifiers')),status=status))
db.execute('CREATE TABLE IF NOT EXISTS input_bindings(package TEXT,binding_index INTEGER,action TEXT,action_path TEXT,key TEXT,triggers TEXT,modifiers TEXT,status TEXT)')
db.execute('DELETE FROM input_bindings')
db.executemany('INSERT INTO input_bindings VALUES(?,?,?,?,?,?,?,?)',[tuple(b.values()) for b in bindings]);db.commit();db.close()
for filename,items in [('input-bindings',bindings),('input-config-fields',config)]:
    with (R/'catalogs'/f'{filename}.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(items[0]) if items else []);w.writeheader();w.writerows(items)
report={'source':'asset-values-v2.jsonl','actions':actions,'bindings':bindings,'config_fields':config,'limits':['These are cooked default configuration declarations, not the current account/user settings.','Input trigger/modifier references are recorded; their nested export values and native implementations require review.','An action name or binding does not prove a gameplay effect.','Missing serialized properties must not be treated as explicit false/zero values without inherited/native-default resolution.']}
(R/'proofs/input-configuration.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
with sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True) as rd:
    tables=rd.execute('SELECT package,asset,count(*) FROM asset_table_rows GROUP BY package,asset ORDER BY count(*) DESC').fetchall()
lines=['# Cooked input and configuration assets','',f'The selected pass decoded 653 configuration exports with exact payload consumption and no recorded parser warnings. It includes {len(actions)} InputAction assets, one base-character input config, and one mapping context. Schemas remain inferred; live bindings, nested trigger/modifier behavior, and omitted defaults need separate validation.','',f'The mapping context contains {len(bindings)} declared bindings; the config has {len(config)} serialized field references. All bindings are saved in `catalogs/input-bindings.csv`; normalized action metadata and original references are in `proofs/input-configuration.json`.','', '## Selected default bindings','','| Action | Key | Trigger references |','| --- | --- | --- |']
selected={'IA_Sprint','IA_Jump','IA_Dodge','IA_CharacterMoveForward','IA_CharacterMoveBackward','IA_CharacterMoveLeft','IA_CharacterMoveRight','IA_Attack1','IA_Guard'}
for binding in bindings:
    if binding['action'] in selected:
        triggers=json.loads(binding['triggers']) or []
        lines.append(f"| {binding['action']} | {binding['key']} | {len(triggers)} |")
lines+=['','The base-character config maps ToggleSprint to IA_Sprint. This connects the declaration to an action name; the input handler and trigger execution are still needed to establish how it changes sprint requests.','', '## Data tables','','The pass recovered 526,357 rows across 30 tables. Two biome-selection grids contribute 262,144 rows each; those counts should not be presented as hundreds of thousands of gameplay rules. Other tables include vendors, dialogue audio, remappable key bindings, economic regions, and UI styles.','', '| Table | Rows |','| --- | --- |']
for package,asset,count in tables:lines.append(f'| {asset} | {count:,} |')
lines+=['','Raw candidates, properties, table rows, and references are in the `asset_value_*` and `asset_table_rows` SQLite tables and corresponding catalogs. The AI/configuration pass also includes 12 behavior trees, 111 blackboards, and 331 state trees. Root references and serialized state metadata are decoded; a referenced object is not automatically a decoded object.','', '33,275 object references matched separately indexed package headers; 41,541 lie outside that header subset and remain explicitly unresolved. These relationships guide expansion of the header/export map.']
(R/'INPUT_CONFIGURATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'actions':len(actions),'bindings':len(bindings),'config_fields':len(config),'selected_bindings':[b for b in bindings if b['action'] in selected]},indent=2))
