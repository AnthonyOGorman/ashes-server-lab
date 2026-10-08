"""Summarize recoverable SDK inheritance, package coverage and diagnostic source areas."""
import csv,json,re,sqlite3
from collections import Counter,defaultdict
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect((RESEARCH/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True,timeout=60)
out=RESEARCH/'catalogs';out.mkdir(exist_ok=True)
types=db.execute('SELECT full_name,package,cpp_name,parent FROM sdk_types').fetchall()
cpp_names=defaultdict(list)
for name,package,cpp,parent in types:cpp_names[cpp].append(name)
edges=[]
for name,package,cpp,parent in types:
    if not parent:continue
    candidates=cpp_names.get(parent,[]);same=[n for n in candidates if n.startswith(package+'.')]
    resolved=same[0] if len(same)==1 else candidates[0] if len(candidates)==1 else None
    edges.append((name,parent,resolved,'declaration_unique_candidate' if resolved else 'unresolved_or_ambiguous',json.dumps(candidates)))
with (out/'type-hierarchy.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['type','parent_cpp_name','parent_candidate','status','all_candidates']);w.writerows(edges)
package_types=Counter(package for _,package,_,_ in types)
package_functions=dict(db.execute('SELECT package,count(*) FROM sdk_functions GROUP BY package'))
package_properties=dict(db.execute('SELECT t.package,count(*) FROM sdk_properties p JOIN sdk_types t ON t.full_name=p.owner GROUP BY t.package'))
package_enums=Counter(r[0].split('.',1)[0] for r in db.execute('SELECT full_name FROM sdk_enums'))
package_mapped=dict(db.execute('SELECT f.package,count(DISTINCT f.full_name) FROM sdk_functions f JOIN native_labels n ON n.name=f.full_name AND n.kind="native_registration_candidate" GROUP BY f.package'))
packages=sorted(set(package_types)|set(package_functions)|set(package_enums),key=lambda p:(-package_types.get(p,0),p))
with (out/'sdk-packages.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['package','types','functions','properties','enums','methods_with_native_candidates'])
    for p in packages:w.writerow([p,package_types.get(p,0),package_functions.get(p,0),package_properties.get(p,0),package_enums.get(p,0),package_mapped.get(p,0)])
areas=defaultdict(lambda:{'paths':set(),'ranges':set(),'references':0})
for begin,path in db.execute('SELECT source_begin,path FROM source_path_refs'):
    path=path.replace('\\','/')
    match=re.search(r'/Source/([^/]+)/(?:Public|Private)/(.+)',path)
    if not match:continue
    module,tail=match.groups();parts=tail.split('/')
    area=parts[0] if len(parts)>1 else '(module root)'
    if area in ('GameService','Narrative','Interactables') and len(parts)>2:area+='/'+parts[1]
    value=areas[(module,area)];value['paths'].add(path);value['ranges'].add(begin);value['references']+=1
with (out/'source-areas.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['module','area','diagnostic_paths','source_attributed_ranges','references'])
    for (module,area),v in sorted(areas.items()):w.writerow([module,area,len(v['paths']),len(v['ranges']),v['references']])
game_types=[t for t in types if t[1]=='GameSystemsPlugin' and t[2].startswith(('U','A'))]
methods_by_owner=Counter(r[0] for r in db.execute('SELECT owner FROM sdk_functions'))
native_names={r[0] for r in db.execute('SELECT name FROM native_labels WHERE kind="native_registration_candidate"')}
labels_by_owner=Counter(owner for name,owner in db.execute('SELECT full_name,owner FROM sdk_functions') if name in native_names)
with (out/'game-classes.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['class','cpp_name','parent_cpp_name','reflected_methods','methods_with_native_candidates'])
    for name,_,cpp,parent in sorted(game_types):w.writerow([name,cpp,parent,methods_by_owner[name],labels_by_owner[name]])
lines=['# Recovered client structure atlas','','This atlas groups declarations and diagnostic paths. It describes recoverable structure and provenance, not verified behavior or exhaustive subsystem ownership.','','## Largest reflected packages','','| Package | Types | Methods | Native candidate links | Enums |','| --- | ---: | ---: | ---: | ---: |']
for p in packages[:30]:lines.append(f'| {p} | {package_types.get(p,0):,} | {package_functions.get(p,0):,} | {package_mapped.get(p,0):,} | {package_enums.get(p,0):,} |')
lines+=['','The complete package table is `catalogs/sdk-packages.csv`. `catalogs/type-hierarchy.csv` retains unique candidate parent resolutions and ambiguous/unresolved declarations. `catalogs/game-classes.csv` lists every indexed GameSystemsPlugin class whose C++ name has an Unreal class prefix.','','## Game diagnostic source areas','','These groups come from embedded Public/Private source paths referenced by machine instructions. Counts reflect diagnostic provenance; an inline helper can contribute a path inside a differently owned function.','','| Area | Distinct paths | Attributed ranges | References |','| --- | ---: | ---: | ---: |']
for (module,area),v in sorted(areas.items()):
    if module=='GameSystemsPlugin':lines.append(f'| {area} | {len(v["paths"])} | {len(v["ranges"])} | {v["references"]} |')
lines+=['','`catalogs/source-areas.csv` contains every matched source module. Full original path strings and instruction RVAs are in `catalogs/source-references.csv`.','','## Coverage boundaries','','Generated SDK parents and member layouts are declarations from a saved dump. The main executable and archives have separate fingerprints. Matching native registration candidates do not prove all layout assumptions for every type. General asset default objects still require correct serialized property schemas. Indirect dispatch, object lifetime, state transitions, expression evaluation, and complete exception flow require semantic review.']
(RESEARCH/'STRUCTURE_ATLAS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
summary={'sdk_packages':len(packages),'parent_relationships':len(edges),'uniquely_resolved_parent_candidates':sum(row[2] is not None for row in edges),'game_classes':len(game_types),'diagnostic_source_areas':len(areas),'game_diagnostic_areas':sum(module=='GameSystemsPlugin' for module,_ in areas)}
(RESEARCH/'index/atlas-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));db.close()
