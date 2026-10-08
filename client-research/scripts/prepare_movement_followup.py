"""Prepare bounded, hash-checked movement collaboration targets without changing the index."""
import argparse,hashlib,json,sqlite3,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import capstone,pefile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('rvas',nargs='+',type=lambda x:int(x,0))
p.add_argument('--batch-name',default='movement-followup',help='Keep independent research manifests and snapshots separate')
args=p.parse_args()
assert args.batch_name and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.batch_name)
assert len(args.rvas)<=128
d=sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
meta=json.loads(d.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])
raw=Path(meta['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==meta['sha256']
pe=pefile.PE(data=raw,fast_load=True);cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
manifest=[];targets=[];missing=[]
for rv in sorted(set(args.rvas)):
    bounds=d.execute('SELECT end FROM native_ranges WHERE begin=?',(rv,)).fetchone()
    if not bounds or not 0<bounds[0]-rv<=65536:
        missing.append(hex(rv));continue
    manifest.append(f'{hex(rv)}\t{hex(bounds[0])}\tmovement collaboration; PE_exception_range')
    frags=d.execute('SELECT u.begin,r.end FROM native_unwind u JOIN native_ranges r ON u.begin=r.begin WHERE u.root_begin=? ORDER BY u.begin',(rv,)).fetchall() or [(rv,bounds[0])]
    records=[]
    for begin,end in frags:
        assert 0<end-begin<=65536
        dat=pe.get_data(begin,end-begin);name=f'{args.batch_name}-{rv:x}-{begin:x}'
        lines=[f'{i.address:08x} {i.bytes.hex():24} {i.mnemonic} {i.op_str}' for i in cs.disasm(dat,begin)]
        proof=dict(exe_sha256=meta['sha256'],root_rva=hex(rv),rva=hex(begin),end=hex(end),bytes=len(dat),fragment_sha256=hashlib.sha256(dat).hexdigest(),boundary='native exception fragment; not complete logical function',instructions=lines)
        (R/'proofs'/f'{name}.json').write_text(json.dumps(proof,indent=2))
        (R/'proofs'/f'{name}.bin').write_bytes(dat)
        (R/'proofs'/f'{name}.asm').write_text('\n'.join(lines)+'\n')
        records.append('proofs/'+name+'.json')
    targets.append(dict(rva=hex(rv),end=hex(bounds[0]),snapshots=records))
(R/'batches'/f'{args.batch_name}.tsv').write_text('\n'.join(manifest)+'\n')
(R/'proofs'/f'{args.batch_name}-targets.json').write_text(json.dumps(dict(exe_sha256=meta['sha256'],targets=targets,missing=missing,limits=['Targets are explicit reviewed research leads.','Snapshots retain chained fragments; inferred types and names require review.']),indent=2))
print(json.dumps(dict(ranges=len(manifest),missing=missing),indent=2));d.close();pe.close()
