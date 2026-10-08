"""Existing StatsComponent export and independently captured stat item codec."""
from .controller_player_state import _dynamic_guid
from .character_info_component import encode_character_info_empty_content
from .world_bootstrap import ObjectRef, encode_exports
from .unreal import BitWriter

CAPTURED_STATS_CHECKSUM = 4031330514
GRAVITY_STAT_GUID = 0x5429e5e8643f0018


def encode_stats_export(pawn_guid, component_guid):
    pawn, component = _dynamic_guid(pawn_guid), _dynamic_guid(component_guid)
    if pawn == component:
        raise ValueError('Distinct existing component identity required')
    return encode_exports([ObjectRef(component, 'StatsComponent',
        ObjectRef(pawn, no_load=True), CAPTURED_STATS_CHECKSUM, True)])


def encode_stats_empty_content(component_guid):
    return encode_character_info_empty_content(component_guid)


def encode_stat_int32_item(replication_id, record, value_bits, *, extra=None):
    """Native 0x6164bf0: raw ID64, value32, conditional base/equipment32.

    extra must be supplied only when the exact stat definition byte +0x247
    enables those fields. This function does not select a component field.
    """
    if not 0 < replication_id <= 0x7fffffff or not 0 < record < 1 << 64:
        raise ValueError('Bounded nonzero record and replication IDs required')
    writer = BitWriter().write(replication_id, 32).write(record, 64).write(value_bits, 32)
    if extra is not None:
        if len(extra) != 2:
            raise ValueError('Exactly base and equipment values required')
        for value in extra:
            writer.write(value, 32)
    return bytes(writer.data), writer.bits


def encode_stat_array(array_key, base_key, items):
    # ReceiveCustomDeltaProperty 0x44e4620 reads SupportsFastArrayDeltaStruct
    # into params+0x4f. StatInt32Rep with flags0 uses the normal full-item path.
    writer = BitWriter().write(1, 1).write(array_key, 32).write(base_key, 32)
    writer.write(0, 32).write(len(items), 32)
    for item in items:
        raw, bits = encode_stat_int32_item(**item)
        writer.raw(raw, bits)
    return bytes(writer.data), writer.bits


def encode_gravity_content(component_guid):
    delta, count = encode_stat_array(1, 0, [dict(replication_id=1,
        record=GRAVITY_STAT_GUID, value_bits=0x3f000000)])
    content = BitWriter().uint(6, 23).packed(count).raw(delta, count)
    header = BitWriter().write(0, 1).write(0, 1)
    _dynamic_guid(component_guid).write(header)
    header.write(1, 1).packed(content.bits).raw(bytes(content.data), content.bits)
    return bytes(header.data), header.bits


def validate_gravity_update(mapping, cache, component_guid, *, expected_item_count=0, expected_flags=0):
    if mapping.get('functions_invoked') is not False or mapping['accepted_component_guids'] != [component_guid]:
        raise ValueError('Exact accepted existing StatsComponent GUID required')
    if mapping['array_item_count'] != expected_item_count or mapping['array_flags'] != expected_flags:
        raise ValueError('Exact current stat array state required')
    if int(mapping['delegate_wrapper'], 16) == 0:
        raise ValueError('Initialized native stat delegate required')
    candidates = [c for c in cache['candidate_caches'] if c['class'] == 'AoCStatsComponent']
    if len(candidates) != 1:
        raise ValueError('One initialized StatsComponent class cache required')
    cls = candidates[0]
    if not cls['header_weak_class_matches'] or not cls['fields_base_matches'] or cls['normal_rpc_field_maximum'] != 23:
        raise ValueError('Exact live stats field maximum23 required')
    fields = [f for f in cls['fields'] if f['field_net_index'] == 6]
    if len(fields) != 1 or fields[0]['name'] != 'StatRepInt32EveryoneProxy' or fields[0]['kind'] != 'FProperty':
        raise ValueError('Exact live gravity replication property field6 required')
    if fields[0]['field_address'] != mapping['property']['address']:
        raise ValueError('Reflected gravity wrapper and network cache must agree')
    return {'dispatch_authorized': True, 'gravity_value': 0.5, 'field_index': 6}


def validate_speed_update(mapping, cache, component_guid):
    result = validate_gravity_update(mapping, cache, component_guid, expected_item_count=1, expected_flags=1)
    if mapping.get('replicated_items') != [{'replication_id':1, 'record':hex(GRAVITY_STAT_GUID), 'value_bits':'0x3f000000'}]:
        raise ValueError('Exactly the verified gravity item must precede speed initialization')
    if mapping.get('movement_speed_value_bits') != 0:
        raise ValueError('Current zero movement-speed stat required')
    return result


def encode_speed_content(component_guid):
    delta, count = encode_stat_array(2, 1, [dict(replication_id=2,
        record=0x6357c09a5679, value_bits=0x3fd47ae1)])
    content = BitWriter().uint(6, 23).packed(count).raw(delta, count)
    header = BitWriter().write(0, 1).write(0, 1)
    _dynamic_guid(component_guid).write(header)
    header.write(1, 1).packed(content.bits).raw(bytes(content.data), content.bits)
    return bytes(header.data), header.bits


def validate_stats_export(actors, receiver, pawn_guid, component_guid):
    pawn = next((m['actor'] for m in actors.get('network_guid_actor_matches', [])
                 if m['guid'] == pawn_guid and m['actor']['class'] == 'PlayerPawn_C'), None)
    if pawn is None or actors.get('errors'):
        raise ValueError('Fresh accepted gameplay pawn required')
    component = _dynamic_guid(component_guid)
    if any(m['guid'] == component.as_dict() for m in actors['network_guid_actor_matches']):
        raise ValueError('Unused component GUID required')
    identity = receiver['component']
    if (identity.get('name'), identity.get('class'), identity.get('outer_address')) != (
            'StatsComponent', 'AoCStatsComponent', pawn['address']):
        raise ValueError('Exact existing pawn StatsComponent required')
    if receiver.get('functions_invoked') is not False or receiver['fields']['bReplicates'].get('value') is not True:
        raise ValueError('Read-only replicated component proof required')
    pre, post = [receiver['virtual_targets'][k] for k in ('0x2a8', '0x2b0')]
    if pre['rva'] != '0x15f4670' or not pre['bytes'].startswith('e97b7cd2ff') or (
            post['rva'] != '0x6132120' or receiver.get('native_receive_bytes_match') is not True):
        raise ValueError('Reviewed receive targets required')
    if receiver.get('pending_integer_count') != 0 or receiver.get('pending_float_count') != 0:
        raise ValueError('Property-empty export requires empty pending stat queues')
    return {'dispatch_authorized': True, 'component': identity,
            'stat_values_supplied': False}
