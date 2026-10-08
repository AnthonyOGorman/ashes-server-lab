"""Bounded read-only owner-scope Stamina evaluated cache and received values."""
import math
import struct
import time

from ashes_testing.telemetry import NativeTelemetry, Unavailable

RECORDS = {'current': 0x5429E4778C77030C, 'maximum': 0x5429E671574D01B4}


def amounts(bits):
    values = {k: struct.unpack('<f', struct.pack('<I', v))[0] for k, v in bits.items()}
    if (not all(math.isfinite(v) for v in values.values()) or
            not 0 < values['maximum'] <= 1000000 or not 0 <= values['current'] <= values['maximum']):
        raise Unavailable('Finite bounded current/max Stamina required')
    return values


def sample(native, pawn_sample):
    from dump_runtime_reflection import Reader
    from inspect_movement_prerequisites import MovementProbe
    from inspect_character_stats import hash_entry
    from protocol_proof import EXPECTED_EXE
    proof = native.proof()
    if (not native.same_process(proof, pawn_sample['client_proof']) or
            not 0 <= time.time() - pawn_sample['observed_at'] <= .5):
        raise Unavailable('Fresh same-lifetime pawn sample required for Stamina')
    reader = Reader(proof['pid'], EXPECTED_EXE, budget=512 * 1024)
    try:
        probe = MovementProbe(reader)
        pawn_address = int(pawn_sample['pawn']['address'], 16)
        if native.identity(probe, pawn_address, 'Pawn') != pawn_sample['pawn']:
            raise Unavailable('Stamina pawn identity changed')
        prop = probe.properties_for(pawn_address)['StatsComponent']
        if (prop['type'], prop['offset_in_object'], prop['element_size']) != ('ObjectProperty', 0xF60, 8):
            raise Unavailable('Reviewed owned StatsComponent property required')
        stats_address = reader.unpack(pawn_address + 0xF60, '<Q')[0]
        stats = native.identity(probe, stats_address, 'ActorComponent')
        if stats['outer_address'] != pawn_sample['pawn']['address']:
            raise Unavailable('StatsComponent is not owned by the current pawn')
        props = probe.properties_for(stats_address)
        if (props['StatsInt32']['type'], props['StatsInt32']['offset_in_object'], props['StatsInt32']['element_size']) != ('MapProperty', 0x668, 0x50):
            raise Unavailable('Reviewed native evaluated StatInt32 cache required')
        owner = props['StatRepInt32Owner']
        if (owner['type'], owner['offset_in_object'], owner['element_size'], owner.get('referenced_type')) != ('StructProperty', 0x890, 0x120, 'StatInt32Rep'):
            raise Unavailable('Stamina requires the reviewed owner replication wrapper')
        if reader.read(reader.base + 0x6175EC0, 12) != bytes.fromhex('8b0189442408f30f10442408c3'):
            raise Unavailable('Reviewed float-bit stat leaf changed')
        index, serial = reader.unpack(reader.base + 0xD932BA0, '<ii')
        if not 0 <= index < probe.reflection.count or serial <= 0:
            raise Unavailable('Live design manager weak identity required')
        chunk = reader.unpack(probe.reflection.chunks + (index // 65536) * 8, '<Q')[0]
        item = reader.read(chunk + (index % 65536) * 24, 24)
        manager_address, flags = struct.unpack_from('<QI', item)
        if struct.unpack_from('<i', item, 16)[0] != serial or flags & 0x10200000:
            raise Unavailable('Design manager weak identity changed')
        manager = native.identity(probe, manager_address, 'DesignDataManagerBase')
        table = hash_entry(reader, manager_address + 0x1F0, 0xB0, 0x4A74AE5ED850DC97)
        if not table:
            raise Unavailable('Current StatTypeDef table required')
        cache_bits, cache_entries = {}, {}
        for name, record in RECORDS.items():
            entry = hash_entry(reader, table + 8, 24, record)
            definition = reader.unpack(entry + 8, '<Q')[0] if entry else 0
            if (not definition or reader.unpack(definition + 8, '<Q')[0] != record or
                    reader.unpack(definition + 0x79, '<B')[0] != 0 or
                    reader.read(definition + 0x246, 2) != b'\x01\x00'):
                raise Unavailable('Stamina record/float type/owner scope/bucket guard changed')
            cached = hash_entry(reader, stats_address + 0x668, 56, record)
            if not cached:
                raise Unavailable('Evaluated current/max Stamina cache missing')
            cache_entries[name] = cached
            cache_bits[name] = reader.unpack(cached + 12, '<I')[0]
        values = amounts(cache_bits)
        wrapper = stats_address + 0x890
        header = reader.read(wrapper + 0x108, 24)
        data, count, capacity, delegate = struct.unpack('<QiiQ', header)
        if not data or not delegate or not 0 < count <= capacity <= 2048:
            raise Unavailable('Current initialized bounded owner stat receipt required')
        raw = reader.read(data, count * 40)
        received = {}
        for name, record in RECORDS.items():
            matches = [raw[i * 40:(i + 1) * 40] for i in range(count)
                       if struct.unpack_from('<Q', raw, i * 40 + 16)[0] == record]
            if len(matches) != 1 or struct.unpack_from('<i', matches[0])[0] <= 0:
                raise Unavailable('Unique accepted current/max owner stat item required')
            received[name] = struct.unpack_from('<I', matches[0], 24)[0]
        if reader.read(wrapper + 0x108, 24) != header:
            raise Unavailable('Stamina owner receipt changed during read')
        if any(reader.unpack(address + 12, '<I')[0] != cache_bits[name] for name, address in cache_entries.items()):
            raise Unavailable('Evaluated Stamina changed during read')
        if (native.identity(probe, stats_address) != stats or native.identity(probe, pawn_address) != pawn_sample['pawn']
                or native.identity(probe, manager_address) != manager
                or reader.unpack(pawn_address + 0xF60, '<Q')[0] != stats_address
                or not native.same_process(proof, native.proof())):
            raise Unavailable('Stamina owner/component/manager/client identity changed')
        return {'status': 'read', 'observed_at': time.time(), 'client_proof': proof,
                'stats_component': stats, 'evaluated': values, 'evaluated_bits': cache_bits,
                'received_owner_bits': received,
                'received_equals_evaluated': {k: received[k] == cache_bits[k] for k in RECORDS},
                'scope': 1, 'record_ids': {k: hex(v) for k, v in RECORDS.items()},
                'source': 'current native evaluated StatsInt32 value+12 and accepted owner FastArray',
                'bytes_read': reader.bytes_read, 'snapshot_atomic': False,
                'functions_invoked': False, 'memory_written': False,
                'claim': 'current evaluated amounts and receipt; setup100 alone is not sprint-cost proof'}
    finally:
        reader.close()
