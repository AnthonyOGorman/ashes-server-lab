"""Resumable bounded-range static references with Capstone; never launch the game.

Sequential decoding uses PE exception ranges. Direct calls/jumps are evidence;
indirect calls, virtual dispatch, dynamically loaded code and inlining remain unresolved.
"""
import argparse
import bisect
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH/'vendor'))
import capstone
import pefile


def analyze(db, limit):
    metadata = json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])
    exe = Path(metadata['path'])
    import hashlib
    if hashlib.sha256(exe.read_bytes()).hexdigest() != metadata['sha256']:
        raise RuntimeError('Installed executable changed; rebuild index before analysis')
    pe = pefile.PE(str(exe), fast_load=True)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS code_scan(begin INTEGER PRIMARY KEY,decoded_bytes INTEGER,total_bytes INTEGER,instructions INTEGER,status TEXT);
    CREATE TABLE IF NOT EXISTS code_refs(source_begin INTEGER,instruction_rva INTEGER,target_rva INTEGER,kind TEXT,detail TEXT);
    CREATE INDEX IF NOT EXISTS refs_target ON code_refs(target_rva);
    CREATE INDEX IF NOT EXISTS refs_source ON code_refs(source_begin);
    ''')
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.skipdata = False
    image_base = pe.OPTIONAL_HEADER.ImageBase
    ranges = db.execute('SELECT begin,end FROM native_ranges WHERE begin NOT IN (SELECT begin FROM code_scan) ORDER BY begin LIMIT ?', (limit,)).fetchall()
    began = time.monotonic()
    for i, (start, end) in enumerate(ranges, 1):
        decoded_bytes = 0
        count = 0
        refs = []
        for address, size, mnemonic, operands in decoder.disasm_lite(pe.get_data(start, end-start), image_base+start):
            rva = address-image_base
            count += 1
            decoded_bytes += size
            if mnemonic == 'call' or mnemonic == 'jmp':
                if re.fullmatch('0x[0-9a-f]+', operands):
                    refs.append((start, rva, int(operands, 16)-image_base, 'direct_'+mnemonic, mnemonic+' '+operands))
                else:
                    refs.append((start, rva, None, 'indirect_'+mnemonic, mnemonic+' '+operands))
            for rip in re.finditer(r'\[rip(?:\s*([+-])\s*(0x[0-9a-f]+|\d+))?\]', operands):
                displacement = int(rip.group(2), 0) if rip.group(2) else 0
                if rip.group(1) == '-':
                    displacement = -displacement
                refs.append((start, rva, rva+size+displacement, 'rip_relative', mnemonic+' '+operands))
        db.executemany('INSERT INTO code_refs VALUES(?,?,?,?,?)', refs)
        status = 'complete_range_decode' if decoded_bytes == end-start else 'partial_range_decode'
        db.execute('INSERT INTO code_scan VALUES(?,?,?,?,?)', (start, decoded_bytes, end-start, count, status))
        if i % 5000 == 0:
            db.commit()
            print(json.dumps({'scanned_this_run': i, 'selected': len(ranges), 'seconds': round(time.monotonic()-began, 1)}), flush=True)
    db.commit()
    pe.close()
    summary = {'capstone': capstone.__version__, 'ranges_total': db.execute('SELECT count(*) FROM native_ranges').fetchone()[0],
               'ranges_scanned': db.execute('SELECT count(*) FROM code_scan').fetchone()[0],
               'decode_status': dict(db.execute('SELECT status,count(*) FROM code_scan GROUP BY status')),
               'references': dict(db.execute('SELECT kind,count(*) FROM code_refs GROUP BY kind')),
               'decoded_bytes': db.execute('SELECT sum(decoded_bytes) FROM code_scan').fetchone()[0],
               'instructions': db.execute('SELECT sum(instructions) FROM code_scan').fetchone()[0]}
    (RESEARCH/'index/code-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=50000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000000:
        parser.error('limit must be 1..1000000')
    with sqlite3.connect(RESEARCH/'index/client-index.sqlite') as db:
        analyze(db, args.limit)
