"""Read current-world streaming levels and data-layer state without game calls."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct

from dump_runtime_reflection import Reader, ReadError, pointer
from export_static_collision import CollisionProbe
from protocol_proof import EXPECTED_EXE, client_proof


def inspect(pid, pawn):
    reader = Reader(pid, EXPECTED_EXE)
    try:
        probe = CollisionProbe(reader)
        identity = probe.p.identity(pawn, 'PlayerPawn_C')
        world = probe.world(pawn)
        if world is None:
            raise ReadError('Current pawn world required')
        result = {'pid': pid, 'client_proof': client_proof(pid), 'pawn': identity,
                  'world': probe.p.identity(world, 'World'), 'levels': [],
                  'world_data_layers': [], 'data_layers': [], 'errors': [],
                  'functions_invoked': False, 'memory_written': False}
        def names(address, name):
            prop = probe.p.properties_for(address)[name]
            data, count, inner = probe.array(address, prop, 4096)
            if inner['type'] != 'NameProperty' or inner['element_size'] != 8:
                raise ReadError('Reflected FName array required')
            return [probe.p.reflection.names.get(index, number) for index, number in
                    struct.iter_unpack('<II', reader.read(data, count * 8))] if count else []
        for address, obj in probe.p.reflection.objects():
            ancestors = [name for _, name in probe.p.chain(obj['class_address'])]
            if not any(name in ancestors for name in
                       ('LevelStreaming', 'WorldDataLayers', 'DataLayerInstance')):
                continue
            if obj['flags'] and int(obj['flags'], 16) & 0x10:
                continue
            if probe.world(address) != world:
                continue
            try:
                row = {'identity': probe.p.identity(address)}
                if 'LevelStreaming' in ancestors:
                    row['fields'] = probe.p.fields(address, ['PackageNameToLoad',
                        'bShouldBeVisible', 'bShouldBeLoaded', 'bClientOnlyVisible',
                        'LoadedLevel', 'bShouldBeAlwaysLoaded'])
                    level = row['fields']['LoadedLevel'].get('value')
                    if level:
                        row['loaded_level_fields'] = probe.p.fields(int(level['address'], 16),
                                                                    ['bIsVisible'])
                    result['levels'].append(row)
                elif 'WorldDataLayers' in ancestors:
                    row['replicated_names'] = {name: names(address, name) for name in
                        ('RepActiveDataLayerNames', 'RepLoadedDataLayerNames',
                         'RepEffectiveActiveDataLayerNames', 'RepEffectiveLoadedDataLayerNames')}
                    result['world_data_layers'].append(row)
                else:
                    row['fields'] = probe.p.fields(address, ['InitialRuntimeState',
                                                          'Parent', 'DataLayerAsset'])
                    result['data_layers'].append(row)
            except (ReadError, KeyError) as exc:
                result['errors'].append({'address': hex(address), 'reason': str(exc)})
        counts = Counter()
        for row in result['levels']:
            fields = row['fields']
            counts['levels'] += 1
            counts['loaded'] += bool(fields['LoadedLevel'].get('value'))
            counts['wanted_visible'] += bool(fields['bShouldBeVisible'].get('value'))
            counts['visible'] += bool(row.get('loaded_level_fields', {}).get('bIsVisible', {}).get('value'))
        result['counts'] = dict(counts)
        if probe.p.identity(pawn, 'PlayerPawn_C') != identity:
            raise ReadError('Pawn changed during streaming inspection')
        return result
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--pawn', type=lambda value: int(value, 0), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.pid, args.pawn)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'counts': report['counts'], 'world_data_layers':
                     [row['replicated_names'] for row in report['world_data_layers']],
                     'data_layer_count': len(report['data_layers']), 'errors': report['errors'][:3]}))
