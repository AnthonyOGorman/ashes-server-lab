"""Install/remove ONLY the staged trial after a coordinated game shutdown."""
import argparse
import csv
import hashlib
import io
import json
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath

HOME = Path(__file__).resolve().parent
GAME = Path(r'E:\Games\Steam Library\steamapps\common\Ashes of Creation\Game\AOC\Binaries\Win64')
EXE = 'AOCClient-Win64-Shipping.exe'


def check_window():
    lease = json.loads((HOME / 'session-access.json').read_text())
    if not (lease.get('coordinated_window') and lease.get('allow_ue4ss_install')
            and lease.get('owner_thread') == '01a116ae-2ec4-7de0-b563-31251b0c4533'
            and 0 < lease.get('expires_at', 0) - time.time() <= 900):
        raise RuntimeError('UE4SS installation window has not been released by the server developer')
    listing = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ' + EXE, '/FO', 'CSV', '/NH'],
                             capture_output=True, text=True, check=True, timeout=10).stdout
    if any(row and row[0].lower() == EXE.lower() for row in csv.reader(io.StringIO(listing))):
        raise RuntimeError('Exit the Ashes client before changing the trial installation')


def target(directory, name):
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:
        raise ValueError('Invalid trial file path')
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError('Trial file must remain inside the checked game directory')
    if name != 'dwmapi.dll' and not name.startswith('ue4ss/'):
        raise ValueError('Trial file is outside the isolated proxy/ue4ss paths')
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(directory=GAME, stage_path=None, manifest_path=None):
    stage_path = stage_path or HOME / 'vendor/trial-package'
    manifest_path = manifest_path or HOME / 'vendor/stage-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if (directory / 'dwmapi.dll').exists() or (directory / 'ue4ss').exists():
        raise RuntimeError('An existing proxy or ue4ss directory must not be overwritten')
    files = manifest['files']
    for name, info in files.items():
        target(directory, name)
        source = target(stage_path, name)
        if source.stat().st_size != info['size'] or digest(source) != info['sha256']:
            raise RuntimeError('Staged trial file changed: ' + name)
    created = []
    created_dirs = set()
    try:
        for name in files:
            destination = target(directory, name)
            parent = destination.parent
            while parent != directory.resolve() and not parent.exists():
                created_dirs.add(parent)
                parent = parent.parent
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive create prevents a raced external install from being overwritten.
            with destination.open('xb') as dest, target(stage_path, name).open('rb') as source:
                created.append(name)
                shutil.copyfileobj(source, dest)
    except Exception:
        for name in reversed(created):
            target(directory, name).unlink()
        for parent in sorted(created_dirs, key=lambda p: len(p.parts), reverse=True):
            try:
                parent.rmdir()
            except OSError:
                pass
        raise
    return {'installed_at': time.time(), 'game_directory': str(directory.resolve()),
            'files': files, 'mods_enabled': [], 'live_compatibility': 'not_verified'}


def uninstall(manifest):
    directory = Path(manifest['game_directory']).resolve()
    if directory != GAME.resolve():
        raise RuntimeError('Uninstall must use the exact documented game directory')
    # Validate ALL identities and containment before removing any file.
    for name, info in manifest['files'].items():
        path = target(directory, name)
        if not path.is_file() or digest(path) != info['sha256']:
            raise RuntimeError('Installed file changed; leave it for review: ' + name)
    parents = set()
    for name in reversed(list(manifest['files'])):
        path = target(directory, name)
        path.unlink()
        parent = path.parent
        while parent != directory:
            parents.add(parent)
            parent = parent.parent
    for parent in sorted(parents, key=lambda p: len(p.parts), reverse=True):
        try:
            parent.rmdir()  # Empty directories only; preserve any new logs/cache files.
        except OSError:
            pass
    return {'removed_manifest_files': len(manifest['files']), 'other_files_preserved': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'uninstall'))
    args = parser.parse_args()
    check_window()
    installed = HOME / 'vendor/installed-manifest.json'
    if args.action == 'install':
        if installed.exists():
            raise RuntimeError('Review previous installed manifest before another install')
        result = install()
        installed.write_text(json.dumps(result, indent=2))
    else:
        result = uninstall(json.loads(installed.read_text()))
        installed.rename(installed.with_name('removed-' + str(time.time_ns()) + '.json'))
    print(json.dumps(result))
