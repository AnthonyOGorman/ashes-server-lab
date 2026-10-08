"""Read-only client/SDK inventory. Rebuild only derived outputs in client-research/index.

Native ranges are PE exception-table records, not a claim of all logical functions.
SDK function bodies are generated ProcessEvent wrappers, not recovered implementations.
"""
import argparse
import hashlib
import json
import re
import sqlite3
import struct
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pefile
from google.protobuf import descriptor_pb2

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / 'client-research'
CLIENT = Path(r'E:\Games\Steam Library\steamapps\common\Ashes of Creation')
SDK = Path(r'E:\Ashes Of Creation\AOC-SDK\SDK')
EXE = CLIENT / 'Game/AOC/Binaries/Win64/AOCClient-Win64-Shipping.exe'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def schema(db):
    db.executescript('''
    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE files(path TEXT PRIMARY KEY,size INTEGER,mtime_ns INTEGER,sha256 TEXT);
    CREATE TABLE sections(name TEXT,rva INTEGER,virtual_size INTEGER,raw_offset INTEGER,raw_size INTEGER,flags INTEGER);
    CREATE TABLE native_ranges(begin INTEGER PRIMARY KEY,end INTEGER,unwind INTEGER,bytes INTEGER,sha256 TEXT);
    CREATE TABLE imports(dll TEXT,name TEXT,iat_rva INTEGER,kind TEXT);
    CREATE TABLE exports(name TEXT,rva INTEGER,ordinal INTEGER,forwarder TEXT);
    CREATE TABLE strings(id INTEGER PRIMARY KEY,rva INTEGER,file_offset INTEGER,encoding TEXT,section TEXT,value TEXT);
    CREATE INDEX strings_rva ON strings(rva);
    CREATE VIRTUAL TABLE string_search USING fts5(value,content=strings,content_rowid=id);
    CREATE TABLE sdk_sources(path TEXT PRIMARY KEY,sha256 TEXT,size INTEGER);
    CREATE TABLE sdk_types(full_name TEXT PRIMARY KEY,kind TEXT,package TEXT,cpp_name TEXT,parent TEXT,size INTEGER,source TEXT,line INTEGER);
    CREATE TABLE sdk_properties(owner TEXT,name TEXT,cpp_type TEXT,offset INTEGER,size INTEGER,flags TEXT,source TEXT,line INTEGER);
    CREATE INDEX properties_owner ON sdk_properties(owner);
    CREATE TABLE sdk_functions(full_name TEXT PRIMARY KEY,package TEXT,owner TEXT,name TEXT,flags TEXT,signature TEXT,source TEXT,line INTEGER);
    CREATE VIRTUAL TABLE sdk_search USING fts5(full_name,flags,signature);
    CREATE TABLE contracts(full_name TEXT,kind TEXT,definition TEXT,source TEXT);
    CREATE TABLE prior_decompiles(rva INTEGER,path TEXT,sha256 TEXT,status TEXT);
    CREATE TABLE historical_reflection(class_name TEXT,function_name TEXT,flags TEXT,definition TEXT,source TEXT,exe_sha256 TEXT,captured_at TEXT);
    ''')


def index_pe(db):
    data = EXE.read_bytes()
    exe_hash = hashlib.sha256(data).hexdigest()
    pe = pefile.PE(data=data, fast_load=True)
    pe.parse_data_directories(directories=[1, 0, 3, 6, 13])
    info = {'path': str(EXE), 'sha256': exe_hash, 'bytes': len(data),
            'machine': hex(pe.FILE_HEADER.Machine), 'image_base': hex(pe.OPTIONAL_HEADER.ImageBase),
            'entry_rva': hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint),
            'linker_timestamp_raw': pe.FILE_HEADER.TimeDateStamp,
            'image_size': pe.OPTIONAL_HEADER.SizeOfImage,
            'prior_hash_matches': exe_hash == json.loads((ROOT/'evidence/client_inventory.json').read_text())['sha256']}
    for section in pe.sections:
        name = section.Name.rstrip(b'\0').decode(errors='replace')
        db.execute('INSERT INTO sections VALUES(?,?,?,?,?,?)', (name, section.VirtualAddress, section.Misc_VirtualSize, section.PointerToRawData, section.SizeOfRawData, section.Characteristics))
        # Restrict strings to nonexecutable, initialized readable sections.
        if section.Characteristics & 0x20000000 or not section.Characteristics & 0x40000000:
            continue
        raw = section.get_data()
        for encoding, pattern in [('ascii', rb'[\x20-\x7e]{6,}'), ('utf16le', rb'(?:[\x20-\x7e]\x00){6,}')]:
            rows = []
            for m in re.finditer(pattern, raw):
                value = m.group().decode('ascii' if encoding == 'ascii' else 'utf-16le')
                if not re.search('[A-Za-z]', value):
                    continue
                rows.append((section.VirtualAddress+m.start(), section.PointerToRawData+m.start(), encoding, name, value))
                if len(rows) == 10000:
                    db.executemany('INSERT INTO strings(rva,file_offset,encoding,section,value) VALUES(?,?,?,?,?)', rows)
                    rows.clear()
            db.executemany('INSERT INTO strings(rva,file_offset,encoding,section,value) VALUES(?,?,?,?,?)', rows)
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    table = pe.get_data(directory.VirtualAddress, directory.Size)
    if len(table) % 12:
        raise ValueError('Exception directory size not divisible by RUNTIME_FUNCTION size')
    ranges = []
    invalid = 0
    for begin, end, unwind in struct.iter_unpack('<III', table):
        if not begin and not end:
            continue
        section = pe.get_section_by_rva(begin)
        if not section or not section.Characteristics & 0x20000000 or not begin < end <= section.VirtualAddress + section.SizeOfRawData:
            invalid += 1
            continue
        raw = pe.get_data(begin, end-begin)
        ranges.append((begin, end, unwind, end-begin, hashlib.sha256(raw).hexdigest()))
    db.executemany('INSERT INTO native_ranges VALUES(?,?,?,?,?)', ranges)
    for kind, attr in [('regular', 'DIRECTORY_ENTRY_IMPORT'), ('delayed', 'DIRECTORY_ENTRY_DELAY_IMPORT')]:
        for entry in getattr(pe, attr, []):
            for imp in entry.imports:
                db.execute('INSERT INTO imports VALUES(?,?,?,?)', (entry.dll.decode(errors='replace'), imp.name.decode(errors='replace') if imp.name else f'ordinal:{imp.ordinal}', imp.address-pe.OPTIONAL_HEADER.ImageBase, kind))
    for exp in getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', []):
        db.execute('INSERT INTO exports VALUES(?,?,?,?)', (exp.name.decode(errors='replace') if exp.name else None, exp.address, exp.ordinal, exp.forwarder.decode(errors='replace') if exp.forwarder else None))
    debug_paths = []
    for entry in getattr(pe, 'DIRECTORY_ENTRY_DEBUG', []):
        raw = data[entry.struct.PointerToRawData:entry.struct.PointerToRawData+entry.struct.SizeOfData]
        if raw.startswith(b'RSDS'):
            debug_paths.append({'pdb_path': raw[24:].rstrip(b'\0').decode(errors='replace'), 'guid_bytes': raw[4:20].hex(), 'age': struct.unpack_from('<I', raw, 20)[0]})
    info.update(exception_records=len(ranges), invalid_exception_records=invalid, debug_records=debug_paths)
    db.execute("INSERT INTO string_search(string_search) VALUES('rebuild')")
    pe.close()
    return info


def index_files(db):
    totals = Counter()
    for path in sorted(CLIENT.rglob('*')):
        if not path.is_file():
            continue
        stat = path.stat()
        extension = path.suffix.lower() or '<none>'
        totals[extension] += 1
        # Hash executable code, TOCs, and manifests; do not re-read hundreds of GB of content.
        hash_file = path.suffix.lower() in ('.exe', '.dll', '.utoc') or path.name.startswith('Manifest_')
        db.execute('INSERT INTO files VALUES(?,?,?,?)', (str(path.relative_to(CLIENT)), stat.st_size, stat.st_mtime_ns, digest(path) if hash_file else None))
    return dict(totals)


def index_sdk(db):
    for path in sorted(SDK.iterdir()):
        if not path.is_file() or path.suffix not in ('.hpp', '.cpp'):
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        db.execute('INSERT INTO sdk_sources VALUES(?,?,?)', (str(path), digest(path), path.stat().st_size))
        package_match = re.search(r'^// Package: (.+)$', text, re.M)
        package = package_match.group(1).strip() if package_match else path.stem
        lines = text.splitlines()
        if path.name.endswith(('_classes.hpp', '_structs.hpp')):
            owner = None
            for n, line in enumerate(lines, 1):
                match = re.match(r'// (Class|ScriptStruct) (\S+)', line)
                if match:
                    owner = match.group(2)
                    declaration = '\n'.join(lines[n:n+6])
                    cpp = re.search(r'^(?:class|struct)\s+(?:alignas\([^)]*\)\s+)?(\w+)(?: final)?(?:\s*:\s*public (\w+))?', declaration,re.M)
                    size = re.search(r'\(0x([0-9A-Fa-f]+) - 0x[0-9A-Fa-f]+\)', declaration)
                    db.execute('INSERT OR IGNORE INTO sdk_types VALUES(?,?,?,?,?,?,?,?)', (owner, match.group(1), package, cpp.group(1) if cpp else None, cpp.group(2) if cpp else None, int(size.group(1), 16) if size else None, str(path), n))
                if owner:
                    prop = re.match(r'^\s*(.*?)\s+(\w+)(?:\[[^]]+\])?(?:\s*:\s*\d+)?;\s*//\s*0x([0-9A-Fa-f]+)\(0x([0-9A-Fa-f]+)\)(.*)', line)
                    if prop and not prop.group(2).startswith('Pad_'):
                        db.execute('INSERT INTO sdk_properties VALUES(?,?,?,?,?,?,?,?)', (owner, prop.group(2), prop.group(1).strip(), int(prop.group(3), 16), int(prop.group(4), 16), prop.group(5).strip(), str(path), n))
        if path.name.endswith('_functions.cpp'):
            for n, line in enumerate(lines, 1):
                match = re.match(r'// Function (\S+)', line)
                if not match:
                    continue
                full = match.group(1)
                parts = full.split('.')
                flags = lines[n].removeprefix('// ').strip() if n < len(lines) else ''
                signature = ''
                for following in lines[n:n+100]:
                    if '::' in following and not following.lstrip().startswith('//'):
                        signature = following.strip()
                        break
                db.execute('INSERT OR IGNORE INTO sdk_functions VALUES(?,?,?,?,?,?,?,?)', (full, package, '.'.join(parts[:-1]), parts[-1], flags, signature, str(path), n))
                db.execute('INSERT INTO sdk_search VALUES(?,?,?)', (full, flags, signature))


def index_prior(db, exe_hash):
    for path in sorted((ROOT/'evidence').glob('**/function_*.c')):
        match = re.fullmatch(r'function_([0-9a-fA-F]+)', path.stem)
        if match:
            text = path.read_text(encoding='utf-8', errors='replace')
            status = 'failed' if 'Decompilation failed:' in text else 'historical_requires_provenance_review'
            db.execute('INSERT INTO prior_decompiles VALUES(?,?,?,?)', (int(match.group(1), 16), str(path), digest(path), status))
    for path in sorted((ROOT/'evidence').glob('runtime_reflection_*.json')):
        document = json.loads(path.read_text(encoding='utf-8'))
        for cls in document.get('classes', []):
            for fun in cls.get('net_functions', []):
                db.execute('INSERT INTO historical_reflection VALUES(?,?,?,?,?,?,?)', (cls.get('name'), fun.get('name'), str(fun.get('flags')), json.dumps(fun), str(path), document.get('sha256'), document.get('time')))
    descriptor_path = ROOT/'evidence/client_contracts.pb'
    descriptors = descriptor_pb2.FileDescriptorSet.FromString(descriptor_path.read_bytes())
    def messages(package, entries, prefix=''):
        for item in entries:
            name = '.'.join(x for x in (package, prefix, item.name) if x)
            db.execute('INSERT INTO contracts VALUES(?,?,?,?)', (name, 'message', str(item), str(descriptor_path)))
            messages(package, item.nested_type, '.'.join(x for x in (prefix, item.name) if x))
    for file in descriptors.file:
        messages(file.package, file.message_type)
        for service in file.service:
            db.execute('INSERT INTO contracts VALUES(?,?,?,?)', (file.package+'.'+service.name, 'service', str(service), str(descriptor_path)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=RESEARCH/'index')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    staging = args.output/'client-index.building.sqlite'
    if staging.exists():
        raise RuntimeError(f'Unfinished build exists: {staging}; preserve/review it before rebuilding')
    db = sqlite3.connect(staging)
    schema(db)
    stages = [('native', lambda: index_pe(db)), ('files', lambda: index_files(db)), ('sdk', lambda: index_sdk(db))]
    results = {}
    for name, run in stages:
        print(f'INDEX {name} started', flush=True)
        results[name] = run()
        db.commit()
        print(f'INDEX {name} complete', flush=True)
    index_prior(db, results['native']['sha256'])
    results['created_at'] = datetime.now(timezone.utc).isoformat()
    results['tables'] = {name: db.execute(f'SELECT count(*) FROM {name}').fetchone()[0] for name in ['files','native_ranges','strings','imports','exports','sdk_sources','sdk_types','sdk_properties','sdk_functions','contracts','prior_decompiles','historical_reflection']}
    results['limitations'] = ['Exception records can include split/chained ranges and omit leaf/inlined functions.', 'SDK methods are reflection wrappers; SDK build identity is unproven until individually validated.', 'String candidates may include coincidental printable data; extraction covers printable ASCII and ASCII-subset UTF-16LE in readable non-code sections.', 'Most content archive payloads have metadata only, not full-file hashes.', 'Historical reflection is saved evidence, not a current process inspection.', 'Installed EOS DLL is a local replacement; do not attribute it to the vendor client.']
    for key, value in results.items():
        db.execute('INSERT INTO metadata VALUES(?,?)', (key, json.dumps(value)))
    db.commit()
    check = db.execute('PRAGMA integrity_check').fetchone()[0]
    if check != 'ok':
        raise RuntimeError(check)
    db.close()
    staging.replace(args.output/'client-index.sqlite')
    (args.output/'summary.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
