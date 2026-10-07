"""Prepare a user's own, exactly matching client. No game binaries are distributed."""
import argparse, hashlib, json, pathlib, shutil, struct

ROOT = pathlib.Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def prepare(client_root, install=False, restore=False):
    supported = json.loads((ROOT/'config/supported-client.json').read_text())
    exe = client_root/'Game/AOC/Binaries/Win64/AOCClient-Win64-Shipping.exe'
    if not exe.is_file() or digest(exe) != supported['exe_sha256']:
        raise ValueError('Unsupported client: executable must match config/supported-client.json')
    sdk = exe.with_name('EOSSDK-Win64-Shipping.dll')
    backup = ROOT/'data/client-backup'/supported['original_eos_sha256']
    shim = ROOT/'build/msvc/Release/LocalEOSConnect.dll'
    if restore:
        if not backup.is_file() or digest(backup) != supported['original_eos_sha256']:
            raise ValueError('Verified original EOS backup not found')
        current = digest(sdk)
        config_file = ROOT/'config/backend.json'
        config = json.loads(config_file.read_text()) if config_file.exists() else {}
        if current != config.get('sdk_sha256') and current != supported['original_eos_sha256']:
            raise ValueError('EOS slot changed unexpectedly; refusing to replace it')
        shutil.copy2(backup, sdk)
        print('Restored original EOS library. Configure/install again before using the lab.')
        return
    # Derive reviewed machine-code ranges from the caller's own PE, never ship them.
    proof_dir = ROOT/'data/client-proofs'
    proof_dir.mkdir(parents=True, exist_ok=True)
    with exe.open('rb') as stream:
        stream.seek(0x3c); pe = struct.unpack('<I', stream.read(4))[0]
        stream.seek(pe)
        if stream.read(4) != b'PE\0\0': raise ValueError('Invalid PE header')
        header = stream.read(20)
        count = struct.unpack_from('<H', header, 2)[0]
        optional_size = struct.unpack_from('<H', header, 16)[0]
        stream.seek(pe + 24 + optional_size)
        sections = [stream.read(40) for _ in range(count)]
        ranges = json.loads((ROOT/'config/client-proof-ranges.json').read_text())
        for entry in ranges:
            rva, size = entry['rva'], entry['size']
            for section in sections:
                virtual_size, address, raw_size, raw_offset = struct.unpack_from('<IIII', section, 8)
                if address <= rva and rva + size <= address + raw_size:
                    stream.seek(raw_offset + rva - address); data = stream.read(size)
                    break
            else: raise ValueError('Reviewed range outside PE sections')
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('Reviewed range hash differs: ' + entry['file'])
            (proof_dir/entry['file']).write_bytes(data)
    if install:
        if not shim.is_file(): raise ValueError('Build Release first to create LocalEOSConnect.dll')
        current = digest(sdk)
        replacement = digest(shim)
        if current != supported['original_eos_sha256'] and current != replacement:
            raise ValueError('EOS slot differs from the supported original or this build. Restore your original library first.')
        if current == supported['original_eos_sha256']:
            backup.parent.mkdir(parents=True, exist_ok=True)
            if backup.exists() and digest(backup) != current:
                raise ValueError('Existing backup hash differs')
            if not backup.exists(): shutil.copy2(sdk, backup)
        shutil.copy2(shim, sdk)
        if digest(sdk) != replacement: raise ValueError('Installed shim verification failed')
    config = json.loads((ROOT/'config/backend.example.json').read_text())
    config.update(client_exe=str(exe.resolve()), sdk_path=str(sdk.resolve()), sdk_sha256=digest(sdk))
    (ROOT/'data').mkdir(exist_ok=True)
    (ROOT/'config/backend.json').write_text(json.dumps(config, indent=2)+'\n')
    print('Client verified; local config and 9 reviewed proof ranges prepared.')
    if not install:
        print('EOS library was not changed. Use -InstallLocalEOS for the local lobby.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-root', required=True, type=pathlib.Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--install-eos', action='store_true')
    group.add_argument('--restore-eos', action='store_true')
    args = parser.parse_args()
    prepare(args.client_root.resolve(), args.install_eos, args.restore_eos)
