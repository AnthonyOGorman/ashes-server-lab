import hashlib,json,secrets,sys
from pathlib import Path
root=Path(__file__).resolve().parent
if '--prepare' in sys.argv:
    (root/'build').mkdir(exist_ok=True)
    build_id=secrets.randbelow(0xFFFFFFFF)+1
    (root/'build'/'build_tag.h').write_text(f'constexpr uint32_t BUILD_ID=0x{build_id:08X};\n',encoding='ascii')
    (root/'build'/'build_id.json').write_text(json.dumps({'build_id':build_id}),encoding='ascii')
    raise SystemExit(0)
build_id=json.loads((root/'build'/'build_id.json').read_text(encoding='ascii'))['build_id']
artifacts={}
for name in ('ashes_input_adapter.dll','ashes_input_fixture.exe'):
    path=root/'build'/name
    artifacts[name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':path.stat().st_size}
(root/'build'/'manifest.json').write_text(json.dumps({'protocol_version':2,'build_id':build_id,'artifacts':artifacts},indent=2),encoding='utf-8')
