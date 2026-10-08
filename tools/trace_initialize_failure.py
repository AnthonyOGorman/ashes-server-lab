"""Offline targeted exact-PE log string xrefs; no execution or modification."""
import json
import mmap
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
terms = ['IntrepidInitialize', 'Calling RequestInitializeCharacter', 'RequestInitializeCharacter',
         'IsEasyOnlineServicesEnabled', 'EACExitGame', 'Custom Failure', 'KICK_ERROR',
         'Both SandboxId and DeploymentId', 'SandboxId', 'DeploymentId', 'System Enabled']
inventory = json.loads((ROOT/'evidence/client_inventory.json').read_text())
with Path(inventory['exe']).open('rb') as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    count, optsize = struct.unpack_from('<H12xH', data, pe+6)
    sections = []
    for i in range(count):
        at = pe+24+optsize+i*40
        virtual_size, virtual, raw_size, raw = struct.unpack_from('<IIII', data, at+8)
        sections.append((data[at:at+8].rstrip(b'\0').decode(), virtual, raw, raw_size))
    def rva(offset):
        return next(v+offset-r for n,v,r,s in sections if r<=offset<r+s)
    strings = {}
    for term in terms:
        found = []
        for encoding in ('utf-16le','utf-8'):
            pattern = term.encode(encoding)
            start = 0
            while True:
                start = data.find(pattern, start)
                if start < 0:
                    break
                beginning = start
                step = 2 if encoding == 'utf-16le' else 1
                while beginning > max(0,start-512) and data[beginning-step:beginning] != b'\0'*step:
                    beginning -= step
                end = start+len(pattern)
                while end < min(len(data)-step,start+1024) and data[end:end+step] != b'\0'*step:
                    end += step
                found.append({'rva': hex(rva(start)), 'encoding': encoding,
                    'enclosing_rva':hex(rva(beginning)),
                    'text': data[beginning:end].decode(encoding,errors='replace')})
                start += len(pattern)
        strings[term] = {'strings': found, 'xrefs': []}
    addresses = {int(entry[key],16): term for term,group in strings.items()
                 for entry in group['strings'] for key in ('rva','enclosing_rva')}
    for target,term in list(addresses.items()):
        pattern = struct.pack('<Q', 0x140000000+target)
        start = 0
        while True:
            start = data.find(pattern,start)
            if start < 0:
                break
            table = rva(start)
            addresses[table] = term
            strings[term].setdefault('pointer_refs', []).append({'rva':hex(table),'target_rva':hex(target)})
            start += 8
    for name,virtual,raw,size in sections:
        if not name.startswith('.text'):
            continue
        code = data[raw:raw+size]
        for match in re.finditer(rb'[\x48\x4c][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', code):
            at = match.start()
            dest = virtual+at+7+struct.unpack_from('<i', code, at+3)[0]
            if dest in addresses:
                strings[addresses[dest]]['xrefs'].append({'instruction_rva':hex(virtual+at), 'target_rva':hex(dest)})
    (ROOT/'evidence/initialize_failure_string_xrefs.json').write_text(json.dumps(strings,indent=2))
    print(json.dumps(strings,indent=2))
