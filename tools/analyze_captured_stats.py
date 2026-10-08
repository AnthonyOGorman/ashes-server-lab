"""Find stats subobject exports in an existing offline game capture; no replay."""
import argparse
from collections import Counter
import json
from pathlib import Path
from lab.unreal import decode_packet, DecodeError
from lab.world_bootstrap import decode_exports
from tools.import_capture import iter_capture


def analyze(capture):
    counts = Counter()
    matches = []
    player_state_fragments = []
    pawn_stats_fragments = []
    for row in iter_capture(Path(capture), None, ()):
        if row['kind'] != 'game_96760c50' or row['source']['port'] != 7436:
            continue
        counts['server_packets'] += 1
        try:
            decoded = decode_packet(bytes.fromhex(row['hex']), 'server')
            for bunch in decoded.get('bunches', []):
                if bunch['channel'] == 4 and row.get('frame', 0) <= 4000:
                    player_state_fragments.append({'frame': row['frame'], 'bunch': bunch})
                if bunch['channel'] == 9 and 3790 <= row.get('frame', 0) <= 3820:
                    pawn_stats_fragments.append({'frame': row['frame'], 'bunch': bunch})
                if not bunch.get('exports'):
                    continue
                counts['export_bunches'] += 1
                exports = decode_exports(bytes.fromhex(bunch['payload_hex']), bunch['payload_bits'])
                selected = [o for o in exports['objects'] if o['path'] == 'StatsComponent']
                if selected:
                    matches.append({'frame': row.get('frame'), 'channel': bunch['channel'],
                        'objects': selected, 'bunch': bunch, 'decoded_exports': exports})
        except (DecodeError, ValueError, KeyError):
            counts['decode_errors'] += 1
    return {'capture': str(capture), 'counts': dict(counts), 'matches': matches,
            'first_player_state_fragments': player_state_fragments,
            'first_pawn_stats_fragments': pawn_stats_fragments,
            'replayed': False, 'scope': 'offline game server export evidence only'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = analyze(args.capture)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'counts': result['counts'], 'stats_exports':
        [{'frame': m['frame'], 'channel': m['channel'], 'checksums':
          [o['checksum'] for o in m['objects'] if o['path'] == 'StatsComponent']}
         for m in result['matches'] if any(o['path'] == 'StatsComponent' for o in m['objects'])],
        'player_state_fragments': len(result['first_player_state_fragments']),
        'pawn_stats_fragments': len(result['first_pawn_stats_fragments'])}))
