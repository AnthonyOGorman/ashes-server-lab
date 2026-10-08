"""Bounded reflected CurrentFloor observation; no traces, calls, or writes."""
import math
import struct

from .telemetry import NativeTelemetry, Unavailable


def reflected_struct(probe, prop, expected, expected_size):
    if (prop.get('type') != 'StructProperty' or prop.get('array_dim') != 1 or
            prop.get('referenced_type') != expected or prop.get('element_size') != expected_size):
        raise Unavailable('Unexpected reflected floor struct layout')
    address = probe.reader.unpack(int(prop['address'], 16) + 0x70, '<Q')[0]
    obj = probe.reflection.obj(address)
    if obj['name'] != expected or probe.reflection.class_name(obj['class_address']) != 'ScriptStruct':
        raise Unavailable('Floor struct identity changed')
    size = probe.reader.unpack(address + 0x78, '<i')[0]
    if size != expected_size:
        raise Unavailable('Floor struct size changed')
    head = probe.reader.unpack(address + 0x70, '<Q')[0]
    fields = probe.reflection.properties(head, size)
    names = [field['name'] for field in fields]
    if len(fields) > 64 or len(set(names)) != len(names):
        raise Unavailable('Floor fields are ambiguous or exceed the bound')
    for field in fields:
        if (field['array_dim'] != 1 or field['offset_in_object'] < 0 or
                field['element_size'] <= 0 or field['offset_in_object'] + field['element_size'] > size):
            raise Unavailable('Floor field exceeds its reflected struct')
    return {field['name']: field for field in fields}


def weak_component(probe, address):
    index, serial = probe.reader.unpack(address, '<ii')
    if serial == 0 and index in (0, -1):
        return None
    if serial <= 0 or not 0 <= index < probe.reflection.count:
        raise Unavailable('Floor component weak index or serial is invalid')
    chunk = probe.reader.unpack(probe.reflection.chunks + (index // 65536) * 8, '<Q')[0]
    item = probe.reader.read(chunk + (index % 65536) * 24, 24)
    pointer, flags = struct.unpack_from('<QI', item)
    current_serial = struct.unpack_from('<i', item, 16)[0]
    if not pointer or current_serial != serial or flags & 0x10200000:
        raise Unavailable('Floor component weak identity expired')
    identity = NativeTelemetry.identity(probe, pointer, 'PrimitiveComponent')
    if identity['object_index'] != index or identity['serial'] != serial:
        raise Unavailable('Floor component weak identity changed')
    return identity


def outer_identity(probe, address):
    # Packages can have no allocated weak serial. Keep the strict weak guard on
    # components/actors/levels; label the weaker package identity explicitly.
    probe.reflection.cache.pop(address, None)
    identity = probe.identity(address)
    if identity['class'] != 'Package':
        return NativeTelemetry.identity(probe, address)
    index = identity['object_index']
    if not 0 <= index < probe.reflection.count:
        raise Unavailable('Floor package index exceeds GObjects')
    chunk = probe.reader.unpack(probe.reflection.chunks + (index // 65536) * 8, '<Q')[0]
    item = probe.reader.read(chunk + (index % 65536) * 24, 24)
    pointer, flags = struct.unpack_from('<QI', item)
    serial = struct.unpack_from('<i', item, 16)[0]
    if pointer != address or serial < 0 or flags & 0x10200000:
        raise Unavailable('Floor package identity expired')
    return {**identity, 'serial': serial if serial > 0 else None,
            'identity_check': 'GObjects pointer/index/class/name; package weak serial may be unallocated'}


def observe_floor(probe, movement_address):
    prop = probe.properties_for(movement_address).get('CurrentFloor')
    if not prop:
        raise Unavailable('CurrentFloor is not reflected')
    fields = reflected_struct(probe, prop, 'FindFloorResult', 272)
    offset = prop['offset_in_object']
    if not 0 <= offset <= 65536:
        raise Unavailable('CurrentFloor offset exceeds observation bound')
    base = movement_address + offset
    before = probe.reader.read(base, 272)

    def scalar(base_address, field, kind, size):
        if field['type'] != kind or field['element_size'] != size:
            raise Unavailable('Floor scalar layout changed')
        decoded = probe.decode(base_address, field)
        if decoded['status'] != 'read':
            raise Unavailable('Floor scalar unavailable')
        value = decoded['value']
        if isinstance(value, float) and not math.isfinite(value):
            raise Unavailable('Nonfinite floor value')
        return value

    values = {name: scalar(base, fields[name], 'BoolProperty', 1)
              for name in ('bBlockingHit', 'bWalkableFloor', 'bLineTrace')}
    values.update({name: scalar(base, fields[name], 'FloatProperty', 4)
                   for name in ('FloorDist', 'LineDist')})
    hit_prop = fields['HitResult']
    hit_fields = reflected_struct(probe, hit_prop, 'HitResult', 256)
    hit_base = base + hit_prop['offset_in_object']
    hit = {name: scalar(hit_base, hit_fields[name], 'BoolProperty', 1)
           for name in ('bBlockingHit', 'bStartPenetrating')}
    for name in ('ImpactPoint', 'ImpactNormal'):
        vector = hit_fields[name]
        expected = 'Vector_NetQuantize' if name == 'ImpactPoint' else 'Vector_NetQuantizeNormal'
        if (vector['type'] != 'StructProperty' or vector['element_size'] != 24 or
                vector.get('referenced_type') != expected):
            raise Unavailable('Floor contact vector layout changed')
        hit[name] = list(probe.reader.unpack(hit_base + vector['offset_in_object'], '<ddd'))
        if not all(math.isfinite(value) for value in hit[name]):
            raise Unavailable('Nonfinite floor contact vector')
    component_prop = hit_fields['Component']
    if component_prop['type'] != 'WeakObjectProperty' or component_prop['element_size'] != 8:
        raise Unavailable('Floor component is not a reflected weak object')
    component = weak_component(probe, hit_base + component_prop['offset_in_object'])
    parents = []
    if component:
        current = component
        seen = {component['address']}
        for _ in range(6):
            parent = int(current['outer_address'], 16)
            if not parent:
                break
            current = outer_identity(probe, parent)
            if current['address'] in seen:
                raise Unavailable('Floor outer chain contains a cycle')
            seen.add(current['address'])
            parents.append(current)
        if NativeTelemetry.identity(probe, int(component['address'], 16)) != component:
            raise Unavailable('Floor component identity changed')
        for identity in parents:
            if outer_identity(probe, int(identity['address'], 16)) != identity:
                raise Unavailable('Floor component outer identity changed')
    if probe.reader.read(base, 272) != before:
        raise Unavailable('CurrentFloor changed during observation; resample')
    return {'status': 'read', 'source': 'reflected CurrentFloor cached native result',
            'fields': values, 'hit': hit, 'component': component, 'outer_chain': parents,
            'claim': 'cached floor contact at the current pawn location; does not prove route coverage',
            'snapshot_atomic': False, 'functions_invoked': False, 'memory_written': False}
