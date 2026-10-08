"""Prepare a pinned dependency under client-testing only. Never installs it."""
import hashlib
import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path, PurePosixPath

HOME = Path(__file__).resolve().parent
PINNED_SHA = '938dc9901e6452cad3120280681c93a00ae12df2b259668815a150e221a35563'


def stage():
    manifest = json.loads((HOME / 'vendor/release-manifest.json').read_text(encoding='utf-8-sig'))
    archive = HOME / 'vendor' / manifest['asset']
    if archive.parent != HOME / 'vendor' or hashlib.sha256(archive.read_bytes()).hexdigest() != PINNED_SHA:
        raise ValueError('Pinned archive hash/path mismatch')
    output = HOME / 'vendor/trial-package'
    output.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or ':' in info.filename or '\\' in info.filename:
                raise ValueError('Unsafe archive member')
            if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Archive symlink is not permitted')
        z.extractall(output)
    mods = output / 'ue4ss/Mods'
    # Disable every bundled mod, including console and cheat manager enablers.
    entries = json.loads((mods / 'mods.json').read_text())
    for entry in entries:
        entry['mod_enabled'] = False
    entries.append({'mod_name': 'AshesObserve', 'mod_enabled': False})
    (mods / 'mods.json').write_text(json.dumps(entries, indent=2), encoding='utf-8')
    (mods / 'mods.txt').write_text('\n'.join(e['mod_name'] + ' : 0' for e in entries) + '\n', encoding='utf-8')
    observer = mods / 'AshesObserve/Scripts'
    observer.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HOME / 'ue4ss/AshesObserve/Scripts/main.lua', observer / 'main.lua')
    nonce = uuid.uuid4().hex
    config = {'output': str(HOME / 'runs/ue4ss-observation.json').replace('\\', '/'),
              'stop_file': str(HOME / 'ue4ss/STOP').replace('\\', '/'), 'run_nonce': nonce}
    (observer / 'binding.lua').write_text('return {\n' + ''.join('  ' + k + ' = ' + json.dumps(v) + ',\n' for k, v in config.items()) + '}\n', encoding='utf-8')
    ini_path = output / 'ue4ss/UE4SS-settings.ini'
    ini = ini_path.read_text()
    # These are settings actually present in this pinned package.
    values = {'ControllingModsTxt': str(mods / 'mods.txt').replace('\\', '/'),
              'ModsFolderPath': str(mods).replace('\\', '/'),
              'SecondsToScanBeforeGivingUp': '30', 'UseCache': '0',
              'ConsoleEnabled': '0', 'GuiConsoleEnabled': '0', 'GuiConsoleVisible': '0',
              'EnableDumping': '0'}
    for name, value in values.items():
        ini, count = re.subn(r'^' + name + r'\s*=.*$', name + ' = ' + value, ini, flags=re.M)
        if count != 1:
            raise ValueError('Expected one setting: ' + name)
    # Proxy and all config/log/cache files remain in the staged directory.
    ini_path.write_text(ini, encoding='utf-8')
    files = {str(p.relative_to(output)).replace('\\', '/'): {'size': p.stat().st_size,
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in output.rglob('*') if p.is_file()}
    result = {'archive_sha256': PINNED_SHA, 'stage': str(output), 'run_nonce': nonce,
              'mods_enabled': [], 'installed': False, 'compatibility': 'untested', 'files': files}
    (HOME / 'vendor/stage-manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    result = stage()
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}))
