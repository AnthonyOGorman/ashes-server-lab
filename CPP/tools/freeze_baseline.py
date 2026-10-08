"""One-time snapshot; Python is used for migration evidence, never the C++ runtime."""
import hashlib, json, pathlib, shutil, subprocess, sys, datetime, sqlite3
root=pathlib.Path(__file__).resolve().parents[2]
dest=root/'CPP'/'baseline'
if (dest/'manifest.json').exists():
    raise SystemExit('Baseline already frozen; refusing to replace it')
files=[]
for group in ('lab','tools','native','web','config','tests'):
    files.extend(p for p in (root/group).rglob('*') if p.is_file() and '__pycache__' not in p.parts and 'build' not in p.parts and p.suffix.lower() not in ('.obj','.exp','.lib','.dll','.exe'))
files.extend(root/p for p in ('README.md','RESUME.md','Start-Lab.ps1','requirements.txt'))
files.extend((root/'data').glob('*.json'))
files.extend(p for p in (root/'evidence').rglob('*') if p.is_file() and p.suffix.lower() in ('.json','.pb','.bin','.raw','.u16','.u8','.f32','.f64') and 'ghidra-project' not in p.parts and 'packaged_asset_inventory' not in p.parts)
manifest=[]
for p in sorted(set(files)):
    rel=p.relative_to(root); out=dest/rel;out.parent.mkdir(parents=True,exist_ok=True)
    contents=p.read_bytes();out.write_bytes(contents)
    manifest.append({'path':rel.as_posix(),'size':len(contents),'sha256':hashlib.sha256(contents).hexdigest()})
# Only immutable character rows are needed, not the live multi-GB packet database.
try:
    db=sqlite3.connect('file:'+str(root/'data/lab.sqlite')+'?mode=ro',uri=True)
    rows=[{'id':r[0],'name':r[1],'world':r[2],'proto_hex':bytes(r[3]).hex()} for r in db.execute('select id,name,world,proto from characters')]
    (dest/'characters.json').write_text(json.dumps(rows,indent=2));db.close()
except Exception as e:
    (dest/'characters-error.txt').write_text(str(e))
(dest/'manifest.json').write_text(json.dumps({'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_root':str(root),'files':manifest},indent=2))
(dest/'dependencies.txt').write_text(subprocess.run([sys.executable,'-m','pip','freeze'],capture_output=True,text=True).stdout)
with (dest/'python-tests.log').open('w') as log:
    result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=dest,stdout=log,stderr=subprocess.STDOUT)
(dest/'test-result.json').write_text(json.dumps({'command':[sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],'cwd':str(dest),'exit_code':result.returncode},indent=2))
print(json.dumps({'files':len(manifest),'bytes':sum(p['size'] for p in manifest),'test_exit_code':result.returncode}))
