"""Offline exact-client movement coverage; client positions are observations."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from lab.movement_rpc import decode_pawn_movement_rpc
from lab.movement_serialization import decode_server_move_argument, decode_move_response_argument
from lab.unreal import DecodeError, decode_packet
from tools.import_capture import iter_capture


def analyze(capture, server_address, server_port, tshark=None):
    capture = Path(capture).resolve()
    counts, errors, records = Counter(), Counter(), []
    for row in iter_capture(capture, tshark, ()):
        if row['kind'] != 'game_96760c50' or server_port not in (
                row['source']['port'], row['destination']['port']):
            continue
        source, destination = row['source'], row['destination']
        if source['address'] == server_address and source['port'] == server_port:
            direction = 'server'
        elif destination['address'] == server_address and destination['port'] == server_port:
            direction = 'client'
        else:
            continue
        packet = decode_packet(bytes.fromhex(row['hex']), direction)
        for bunch in packet.get('bunches', []):
            if bunch['channel'] != 9 or any(bunch.get(flag) for flag in
                    ('exports', 'must_map', 'partial', 'open', 'close')):
                continue
            try:
                envelope = decode_pawn_movement_rpc(bytes.fromhex(bunch['payload_hex']),
                    bunch['payload_bits'], direction)
            except (DecodeError, ValueError):
                continue
            for field in envelope['fields']:
                if 'rpc' not in field:
                    continue
                name = field['rpc']
                counts[name + '_observed'] += 1
                entry = {'frame': row['frame'], 'capture_time': row['ts'],
                    'direction': direction, 'rpc': name, 'argument_bits': field['argument_bits']}
                try:
                    decoder = decode_server_move_argument if direction == 'client' else decode_move_response_argument
                    entry['decoded'] = decoder(bytes.fromhex(field['argument_hex']), field['argument_bits'])
                    counts[name + '_decoded'] += 1
                except (DecodeError, ValueError) as exc:
                    entry['decode_error'] = str(exc)
                    errors[name + ': ' + str(exc)] += 1
                records.append(entry)
    moves = [move for entry in records for move in entry.get('decoded', {}).get('moves', [])]
    new_moves = [move for move in moves if move['kind'] == 'new']
    timestamps = {move['timestamp'] for move in moves}
    acknowledgements = [entry['decoded']['timestamp'] for entry in records
        if entry.get('decoded', {}).get('acknowledgement')]
    corrections = [entry['decoded'] for entry in records
        if entry.get('decoded', {}).get('acknowledgement') is False]
    summary = {'decoded_moves': len(moves), 'decoded_new_moves': len(new_moves),
        'ack_timestamps_matching_decoded_moves': sum(ts in timestamps for ts in acknowledgements),
        'ack_timestamps_unmatched': sum(ts not in timestamps for ts in acknowledgements),
        'decoded_corrections': len(corrections),
        'correction_timestamps_matching_decoded_moves': sum(x['timestamp'] in timestamps for x in corrections)}
    if new_moves:
        locations = [move['client_location'] for move in new_moves]
        summary.update(first_client_location=locations[0], last_client_location=locations[-1],
            client_location_bounds=[[min(v[i] for v in locations), max(v[i] for v in locations)] for i in range(3)],
            new_moves_with_nonzero_acceleration=sum(any(move['acceleration']) for move in new_moves))
    digest = hashlib.sha256()
    with capture.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return {'source_capture': str(capture), 'capture_sha256': digest.hexdigest(),
        'server_endpoint': {'address': server_address, 'port': server_port},
        'scope': 'complete channel9 movement RPCs under exact-client max198 cache',
        'counts': dict(counts), 'unsupported_or_malformed': dict(errors),
        'summary': summary, 'records': records, 'movement_proved': False,
        'limits': ['Historical capture only; no fresh input or current walking proof.',
            'Client locations and acceleration are not server-authoritative movement.',
            'Base/bone references and root-motion corrections fail closed.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--server-address', required=True)
    parser.add_argument('--server-port', required=True, type=int)
    parser.add_argument('--tshark', type=Path)
    args = parser.parse_args()
    if args.capture.resolve() == args.output.resolve():
        parser.error('Output must differ from source capture')
    report = analyze(args.capture, args.server_address, args.server_port, args.tshark)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('counts', 'unsupported_or_malformed', 'summary')}))


if __name__ == '__main__':
    main()
