"""Bounded offline PE xrefs for movement serializer research (never executes client)."""
import argparse
import json
import mmap
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]

class PE:
    def __init__(self, data):
        self.data = data
        pe = struct.unpack_from('<I', data, 0x3c)[0]
        count, optsize = struct.unpack_from('<H12xH', data, pe+6)
        opt = pe+24
        self.base = struct.unpack_from('<Q', data, opt+24)[0]
        self.sections = []
        for i in range(count):
            at = opt+optsize+i*40
            size, virtual, rawsize, raw = struct.unpack_from('<IIII', data, at+8)
            self.sections.append((data[at:at+8].rstrip(b'\0').decode(), virtual, raw, rawsize))
        ex, size = struct.unpack_from('<II', data, opt+112+3*8)
        at = self.offset(ex)
        self.functions = list(struct.iter_unpack('<III', data[at:at+size]))

    def offset(self, rva):
        return next(raw+rva-v for _,v,raw,size in self.sections if v <= rva < v+size)

    def rva(self, offset):
        return next(v+offset-raw for _,v,raw,size in self.sections if raw <= offset < raw+size)

    def boundary(self, rva):
        return next(([hex(a),hex(b)] for a,b,_ in self.functions if a <= rva < b), None)

    def references(self, targets):
        result = []
        for name,v,raw,size in self.sections:
            if not name.startswith('.text'):
                continue
            code = self.data[raw:raw+size]
            for match in re.finditer(rb'[\x48\x4c][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', code):
                at = match.start()
                target = v+at+7+struct.unpack_from('<i',code,at+3)[0]
                if target in targets:
                    result.append({'instruction':hex(v+at),'target':hex(target), 'boundary':self.boundary(v+at)})
        return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--term', default='AoCCharacterMovement')
    parser.add_argument('--rva', type=lambda x:int(x,0))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads((ROOT/'evidence/client_inventory.json').read_text())
    with Path(inventory['exe']).open('rb') as file, mmap.mmap(file.fileno(),0,access=mmap.ACCESS_READ) as data:
        pe = PE(data)
        targets = set()
        if args.rva is not None:
            targets.add(args.rva)
        else:
            for encoding in ['utf-16le','utf-8']:
                pattern = args.term.encode(encoding)
                start = 0
                while (start := data.find(pattern,start)) >= 0:
                    targets.add(pe.rva(start))
                    start += len(pattern)
        pointer_refs = []
        for target in list(targets):
            start = 0
            pattern = struct.pack('<Q',pe.base+target)
            while (start := data.find(pattern,start)) >= 0:
                pointer = pe.rva(start)
                pointer_refs.append({'rva':hex(pointer),'target':hex(target)})
                targets.add(pointer)
                start += 8
        result = {'term':args.term,'targets':[hex(x) for x in sorted(targets)], 'pointer_refs':pointer_refs,
                  'code_refs':pe.references(targets),'caution':'Pattern xrefs are candidates; validate disassembly.'}
        args.output.write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
