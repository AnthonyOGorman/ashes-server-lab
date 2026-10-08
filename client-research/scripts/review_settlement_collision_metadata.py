"""Export/review all selected platform collision metadata; outputs stay in research.

Uses the existing implementation-owned archive reader without rebuilding it.
No client access, packets, inputs, CPP writes or collision admission.
Run only while the input owner is idle so archive work cannot skew a pulse.
"""
import argparse, collections, hashlib, json, shutil, subprocess
from pathlib import Path

R = Path(__file__).resolve().parents[1]
CPP = R.parent / 'CPP'
OUT = R / 'proofs/settlement-platform-metadata'
PROFILE = R / 'proofs/settlement-landscape-instances.json'
MANIFEST = CPP / 'data/terrain-offline/decoded-other-worlds/manifest.json'
DEFAULTS = CPP / 'data/terrain-offline/collision-defaults.json'
READER = CPP / 'tools/terrain-collision/bin/Release/net10.0/TerrainCollision.dll'
PAKS = Path(r'E:\Games\Steam Library\steamapps\common\Ashes of Creation\Game\AOC\Content\Paks')

def read(path):
    return json.loads(path.read_bytes())

def evidence(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--export', action='store_true', help='Read installed archives first')
    args = parser.parse_args()
    catalog, manifest, defaults = map(read, (PROFILE, MANIFEST, DEFAULTS))
    packages = sorted({x['path']['package'] for x in catalog['instances']})
    assert len(packages) == 12
    classes = {x['class']: x for x in defaults['records']}
    if args.export:
        OUT.mkdir(parents=True, exist_ok=True)
        shutil.copytree(CPP / 'data/terrain-offline/mappings', OUT / 'mappings', dirs_exist_ok=True)
        write(OUT / 'cooked/manifest.json', {'tiles': [{'package': p} for p in packages]})
        write(OUT / 'cooked-mesh/manifest.json', {'tiles': []})
        command = ['dotnet', str(READER), str(PAKS), str(OUT / 'archive'), '--collision-metadata']
        write(OUT / 'export-invocation.json', {'command': command, 'reader': evidence(READER),
            'reader_source': evidence(CPP / 'tools/terrain-collision/Program.cs'),
            'mapping_sources': [evidence(p) for p in sorted((OUT / 'mappings').glob('*.json'))],
            'scope': 'archive read; research outputs only; no live process access'})
        with (OUT / 'export.log').open('w', encoding='utf-8') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    metadata = read(OUT / 'collision-metadata.json')
    assert metadata['scanned'] == len(packages) and not metadata['failures']
    assert defaults['proof']['sha256'] == read(CPP / 'config/backend.json')['client_sha256']
    records = collections.defaultdict(list)
    for rec in metadata['records']:
        assert rec['package'] in packages
        records[(rec['package'], rec['cls'], rec['name'])].append(rec)
    reports = []
    for package in packages:
        tiles = [t for t in manifest['tiles'] if t['package'] == package]
        assert len(tiles) == 256
        overrides, disabled = [], []
        for tile in tiles:
            key = (package, tile['cls'], tile['name'])
            matching = records[key]
            assert len(matching) == 1, key
            rec = matching.pop()
            default = classes[rec['owner_cls']]
            assert default['collision_profile'] == 'BlockAll'
            assert default['collision_enabled_value'] == 3 and default['actor_enabled']
            if rec['body_json'] is not None or rec['template'] is not None:
                overrides.append(rec)
            if not rec['actor_enabled']:
                disabled.append(rec['name'])
        reports.append({'package': package, 'tiles': len(tiles),
            'archive_actor_disabled_components': disabled, 'overrides_requiring_review': overrides,
            'metadata_ready': not overrides and not disabled,
            'node_ids': [x['node_id'] for x in catalog['instances'] if x['path']['package'] == package]})
    assert not any(records.values()), 'Unused component metadata'
    write(R / 'proofs/settlement-platform-metadata-review.json', {
        'sources': [evidence(p) for p in (PROFILE, MANIFEST, DEFAULTS, OUT / 'collision-metadata.json')],
        'build_sha256': defaults['proof']['sha256'], 'packages': reports,
        'limits': ['Metadata readiness is not live client loading, pawn contact or server admission.',
            'Actor overrides/templates require review before using native defaults.',
            'Preserve material255 holes and exact per-node world transforms.',
            'Geometry buffer hashes are independently checked in settlement-platform-collision-inventory.json.']})
    print(json.dumps({'packages': len(reports), 'tiles': sum(x['tiles'] for x in reports),
        'metadata_ready': sum(x['metadata_ready'] for x in reports)}))

if __name__ == '__main__':
    main()
