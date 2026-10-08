"""Fixed controller PlayerState scalar grammar with exact reviewed receiver guard."""
import struct

from .unreal import BitWriter
from .world_bootstrap import NetGUID


def _dynamic_guid(value):
    if not isinstance(value, dict) or set(value) != {'object_id', 'server_id', 'randomizer'}:
        raise ValueError('Exact known dynamic PlayerState GUID required')
    try:
        oid = int(value['object_id'], 16) if isinstance(value['object_id'], str) else value['object_id']
    except (TypeError, ValueError):
        raise ValueError('Invalid PlayerState object ID') from None
    sid, rand = value['server_id'], value['randomizer']
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (oid, sid, rand)) or not (
        2 <= oid < 2**64 and oid % 2 == 0 and 0 < sid < 2**32 and 0 <= rand < 2**32):
        raise ValueError('Nonnull bounded dynamic PlayerState GUID required')
    return NetGUID(oid, sid, rand)


def validate_controller_player_state_wire(layouts, serializer, actors, controller_cache,
                                          controller_guid, player_state_guid):
    """Validate wire prerequisites only. Caller must separately validate fresh live proofs.

    This is not dispatch authorization: validate_controller_player_state adds the
    unresolved exact RepNotify receiver check.
    """
    target = _dynamic_guid(player_state_guid)
    _dynamic_guid(controller_guid)
    if layouts.get('errors'):
        raise ValueError('Clean exact controller RepLayout required')
    candidates = [l for l in layouts.get('layouts', []) if l.get('class') == 'AoCPlayerControllerBP_C']
    if len(candidates) != 1:
        raise ValueError('One exact controller RepLayout required')
    layout = candidates[0]
    if controller_cache.get('class') != layout['class'] or any(
        layout.get(k) != controller_cache.get(k) or layout.get(k) is None
        for k in ('class_index', 'class_serial')):
        raise ValueError('Current controller class cache/layout identity must agree')
    parent = next((p for p in layout.get('parents', []) if p.get('parent_index') == 13), None)
    command = next((c for c in layout.get('commands', []) if c.get('command_index') == 18), None)
    if parent is None or command is None:
        raise ValueError('Exact PlayerState parent13/command18 required')
    prop = parent['property']
    if tuple(prop.get(k) for k in ('name', 'type', 'owner_class', 'offset_in_object',
                                 'element_size', 'array_dim', 'referenced_type')) != (
        'PlayerState', 'ObjectProperty', 'Controller', 0x370, 8, 1, 'PlayerState') or not {
        'Net', 'RepNotify'}.issubset(prop.get('flag_names', [])):
        raise ValueError('Exact replicated controller PlayerState scalar required')
    if struct.unpack_from('<H', bytes.fromhex(parent['record_hex']), 0x1c)[0] != 18 or (
        command.get('parent_index'), command.get('command_type_byte'),
        command.get('uninterpreted_word_14'), command.get('property_address')) != (
        13, 8, 19, prop['address']) or any(c['command_type_byte'] == 0 for c in layout['commands'][:19]):
        raise ValueError('Verified scalar traversal to handle19 required')
    if serializer.get('property', {}).get('address') != prop['address'] or (
        serializer.get('net_serialize_virtual_offset'), serializer.get('net_serialize_rva'),
        serializer.get('serialize_object_virtual_offset'), serializer.get('serialize_object_rva'),
        serializer.get('internal_load_object_rva'), serializer.get('guid_reader_rva')) != (
        '0xc8', '0x170af50', '0x340', '0x42875a0', '0x42740f0', '0x141e960'):
        raise ValueError('Exact direct known-GUID object serializer proof required')
    def accepted(guid, expected):
        matches = [m for m in actors.get('network_guid_actor_matches', []) if m.get('guid') == guid]
        if len(matches) != 1:
            raise ValueError('Unique accepted current GUID object required')
        match = matches[0]
        actor = match.get('actor') or {}
        if actor.get('class') != expected or not actor.get('address') or (
            match.get('weak_object_index') != actor.get('object_index')) or not isinstance(
            match.get('weak_object_serial'), int) or match['weak_object_serial'] <= 0:
            raise ValueError('Exact accepted actor class/index/serial required')
        return match
    pc, ps = accepted(controller_guid, 'AoCPlayerControllerBP_C'), accepted(player_state_guid, 'AoCPlayerStateBP_C')
    if not pc.get('guid_cache') or pc['guid_cache'] != ps.get('guid_cache') or (
        pc['actor'].get('outer_address') != ps['actor'].get('outer_address')):
        raise ValueError('Controller and PlayerState must share accepted cache and level')
    if 'player_state' not in pc['actor'] or pc['actor']['player_state'] is not None:
        raise ValueError('Current controller PlayerState must be explicitly observed null')
    if serializer.get('actor_address') != pc['actor']['address']:
        raise ValueError('Serializer proof must bind the actual accepted controller')
    return {'wire_handle': 19, 'guid_bits': 128, 'player_state_guid': target.as_dict(),
            'content_bits': 145, 'actor_block_bits': 163, 'dispatch_authorized': False}


def validate_controller_player_state(*args, receiver=None, **kwargs):
    result = validate_controller_player_state_wire(*args, **kwargs)
    if receiver is None:
        raise ValueError('Actual accepted controller OnRep_PlayerState target is unreviewed; dispatch refused')
    serializer, actors = args[1], args[2]
    controller_guid, player_state_guid = args[4], args[5]
    ps = next(m['actor'] for m in actors['network_guid_actor_matches'] if m['guid'] == player_state_guid)
    if (receiver.get('functions_invoked') is not False or
        receiver.get('actor_address') != serializer['actor_address'] or
        receiver.get('player_state_address') != ps['address'] or
        receiver.get('controller_guid') != controller_guid or receiver.get('player_state_guid') != player_state_guid or
        receiver.get('controller_notify_rva') != '0x3eebc80' or
        receiver.get('player_state_initialize_rva') != '0x44119c0' or
        receiver.get('player_state_set_owner_rva') != '0x3b8f7b0' or
        receiver.get('controller_notify_bytes') != '488bd1488b89700300004885c9740a488b0148ffa040080000c3' or
        receiver.get('player_state_initialize_bytes') != '488b0148ffa0e0050000'):
        raise ValueError('Exact reviewed controller notification/PlayerState initialization chain required')
    return {**result, 'dispatch_authorized': True, 'receiver_effect': 'initialize_PlayerState_owner_to_controller'}


def encode_controller_player_state_content(player_state_guid):
    """Offline fixed handle19 encoder; requires external accepted/fresh proof before dispatch."""
    guid = _dynamic_guid(player_state_guid)
    stream = BitWriter().write(0, 1).packed(19)
    guid.write(stream)
    stream.packed(0)
    block = BitWriter().write(1, 1).write(1, 1).packed(stream.bits).raw(bytes(stream.data), stream.bits)
    return bytes(block.data), block.bits
