"""Gate local tether identifiers on the exact installed local SDK hash."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SDK=Path(r'E:\Games\Steam Library\steamapps\common\Ashes of Creation\Game\AOC\Binaries\Win64\EOSSDK-Win64-Shipping.dll')
def local_tether_tags():
    profile=ROOT/'data/eos-local-compat.json'
    if not profile.exists():return {}
    settings=json.loads(profile.read_text(encoding='utf-8'))
    if set(settings)!={'mode','sdk_sha256'} or settings['mode']!='local-compatibility':
        raise ValueError('Explicit local EOS compatibility profile required')
    expected=settings['sdk_sha256']
    if not isinstance(expected,str) or len(expected)!=64 or hashlib.sha256(SDK.read_bytes()).hexdigest()!=expected:
        raise ValueError('Local EOS profile does not match the installed SDK')
    return {'eac_deployment_id':'eeeeeeee000000000000000000000001',
            'eac_sandbox_id':'eeeeeeee000000000000000000000002'}
