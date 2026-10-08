"""Fixed proof-bound GameState BeginPlay scalar property experiment."""
import struct
from .unreal import BitWriter


def _validate_reviewed_override(serializer, lifecycle, accepted, actors):
    """Bind reviewed client netmode and WorldSettings chain to accepted GUID cache."""
    p = serializer.get('game_specific_predicate') or {}
    if (p.get('status'), p.get('required_helper_result'), p.get('predicate_rva'),
        p.get('helper_rva'), p.get('caller_optional_standalone'), p.get('functions_invoked'),
        p.get('reviewed_code_matches'), p.get('inferred_helper_result'),
        p.get('predicate_would_accept_true_bool')) != (
        'verified_client_predicate', 3, '0x56f0e70', '0x3b847b0', False, False, True, 3, True):
        raise ValueError('Reviewed exact gameplay client predicate proof required')
    expected_ranges = {'0x5ef7800':116, '0x56f0e70':74, '0x3b847b0':138,
        '0x4236c80':45, '0x1505900':69, '0x3b82890':130, '0x3b82920':36,
        '0x4733960':160, '0x41861f0':8}
    if p.get('reviewed_code_ranges') != expected_ranges:
        raise ValueError('Reviewed exact netmode and lifecycle pointer-chain code required')
    if not isinstance(actors, dict):
        raise ValueError('Independent accepted actor/driver snapshot required for override')
    identity_keys = ('pid','exe','process_created_filetime','sha256')
    reference = serializer.get('client_proof') or {}
    if any(reference.get(key) is None for key in identity_keys) or any(
        tuple(snapshot.get('client_proof', {}).get(key) for key in identity_keys) !=
        tuple(reference[key] for key in identity_keys) for snapshot in (actors, lifecycle)):
        raise ValueError('Predicate and accepted driver proofs must bind the same exact process')
    def bind(left, right, expected_class):
        if not isinstance(left, dict) or not isinstance(right, dict) or not left.get('address'):
            raise ValueError('Nonnull exact predicate pointer binding required')
        if any(left.get(key) != right.get(key) for key in ('address','object_index','class')) or expected_class not in left.get('ancestors', []):
            raise ValueError('Predicate pointer identity or reflected ancestry mismatch')
    bind(p.get('actor'), accepted, 'GameStateBase')
    world = lifecycle.get('world', {}).get('identity', {})
    bind(p.get('world'), world, 'World')
    bind(p.get('owning_world'), world, 'World')
    bind(p.get('owning_level'), lifecycle.get('level', {}).get('identity'), 'Level')
    bind(p.get('persistent_level'), p.get('owning_level'), 'Level')
    if accepted.get('outer_address') != p['owning_level']['address'] or p['owning_level'].get('outer_address') != world.get('address'):
        raise ValueError('Actual GameState outer/level/world chain required')
    settings = p.get('world_settings') or {}
    if 'WorldSettings' not in settings.get('ancestors', []) or not settings.get('address') or settings.get('outer_address') != p['persistent_level']['address']:
        raise ValueError('Actual PersistentLevel WorldSettings receiver required')
    for key, name, offset in (('driver_field_metadata','NetDriver',0x58),
                             ('server_connection_metadata','ServerConnection',0x138),
                             ('persistent_level_metadata','PersistentLevel',0x50),
                             ('world_settings_metadata','WorldSettings',0x2d0)):
        metadata = p.get(key) or {}
        if (metadata.get('name'), metadata.get('offset_in_object'), metadata.get('element_size'), metadata.get('array_dim')) != (name,offset,8,1) or metadata.get('type') not in ('ObjectProperty','ObjectPropertyBase'):
            raise ValueError('Exact fresh reflected lifecycle object fields required')
    name = p.get('net_driver_name') or {}
    metadata = name.get('metadata') or {}
    if (metadata.get('name'),metadata.get('type'),metadata.get('offset_in_object'),metadata.get('element_size'),metadata.get('array_dim')) != ('NetDriverName','NameProperty',0x1f0,8,1) or name.get('number') != 0 or not isinstance(name.get('index'),int) or name['index'] <= 0 or name['index'] != name.get('builtin_11a_index') or (name.get('resolved'),name.get('builtin_11a_resolved')) != ('GameNetDriver','GameNetDriver'):
        raise ValueError('Exact built-in GameNetDriver name branch required')
    virtual = p.get('driver_virtual_4b0') or {}
    leaf = '4883b938010000000f94c0c3'
    if virtual.get('rva') != '0x423d720' or virtual.get('inferred_return') is not False or not virtual.get('code_hex','').startswith(leaf):
        raise ValueError('Reviewed actual driver ServerConnection zero-test leaf required')
    driver = p.get('driver') or {}
    candidates = [d for d in actors.get('net_drivers', []) if d.get('address') == driver.get('address')]
    if len(candidates) != 1:
        raise ValueError('Predicate driver must be an independently accepted current driver')
    current_driver = candidates[0]
    bind(driver, current_driver, 'NetDriver')
    bind(p.get('driver_server_connection'), current_driver.get('server_connection'), 'NetConnection')
    matches = [m for m in actors.get('network_guid_actor_matches', []) if
        m.get('actor', {}).get('address') == accepted.get('address') and
        m.get('guid_cache') == current_driver.get('guid_cache')]
    if len(matches) != 1 or not current_driver.get('guid_cache'):
        raise ValueError('Accepted GameState GUID must belong to the predicate driver cache')
    bind(matches[0].get('actor'), accepted, 'GameStateBase')
    callbacks = p.get('world_settings_callbacks') or {}
    expected = {'0x870':('0x47bb130','48895c2410488974241848897c2420554154415541564157488d6c24c94881ec'),
        '0x878':('0x47bb5c0','40534883ec20e8c5723cff488bd8f680ad010000027513488d88a8080000e81d')}
    if set(callbacks) != set(expected) or any(
        (callbacks[key].get('rva'), callbacks[key].get('code_prefix_hex')) != value
        for key,value in expected.items()):
        raise ValueError('Reviewed exact WorldSettings callback targets required')


def validate_game_state_begin_play(layouts, serializer, lifecycle, accepted, *, actors=None):
    if layouts.get('errors') or serializer.get('native_only', True) or serializer.get('observed_bool_value') is not False:
        raise ValueError('Clean actual live gameplay GameState proof required')
    layout = next((p for p in layouts.get('layouts', []) if p.get('class') == 'AoCGameStateBP_C'), None)
    if layout is None or layout['class_index'] != serializer.get('game_state_class_index'):
        raise ValueError('Actual GameState class index must match current RepLayout')
    parent = next((p for p in layout['parents'] if p.get('parent_index') == 15), None)
    command = next((c for c in layout['commands'] if c.get('command_index') == 20), None)
    if parent is None or command is None:
        raise ValueError('Exact BeginPlay parent15/command20 required')
    prop = parent['property']
    expected = ('bReplicatedHasBegunPlay', 'BoolProperty', 0x390, 1, 1)
    if tuple(prop.get(k) for k in ('name', 'type', 'offset_in_object', 'element_size', 'array_dim')) != expected:
        raise ValueError('Exact reflected scalar BeginPlay bool required')
    if prop.get('bool_layout') != {'field_size':1,'byte_offset':0,'byte_mask':1,'field_mask':255} or not {'Net','RepNotify'}.issubset(prop.get('flag_names', [])):
        raise ValueError('Exact native bool masks and replication notification required')
    if struct.unpack_from('<H', bytes.fromhex(parent['record_hex']), 0x1c)[0] != 20:
        raise ValueError('BeginPlay parent start command must agree')
    if (command.get('parent_index'), command.get('command_type_byte'), command.get('uninterpreted_word_14'), command.get('property_address')) != (15,21,21,prop['address']):
        raise ValueError('Exact scalar bool command and handle21 required')
    if any(c['command_type_byte'] == 0 for c in layout['commands'][:21]):
        raise ValueError('Unexpected dynamic array spans before bool handle')
    if serializer.get('property', {}).get('address') != prop['address'] or (serializer.get('net_serialize_rva'),serializer.get('net_serialize_virtual_offset')) != ('0x170acb0','0xc8'):
        raise ValueError('Current exact one-bit BoolProperty serializer required')
    notify = serializer.get('notify', {})
    if (notify.get('name'),notify.get('exec_rva'),notify.get('virtual_offset'),notify.get('target_evidence')) != ('OnRep_ReplicatedHasBegunPlay','0x4044410','0x898','actual_accepted_BP_actor_virtual_target') or notify.get('implementation_rva') not in ('0x4022bf0','0x5ef7800'):
        raise ValueError('Exact gameplay actor BeginPlay notification target required')
    if serializer.get('actor_roles', {}).get('Role') == 4 or serializer.get('actor_roles', {}).get('Role') not in (1,2,3):
        raise ValueError('Actual GameState must have a verified non-authority client role')
    gs = lifecycle.get('game_state', {})
    identity = gs.get('identity', {})
    world = lifecycle.get('world', {})
    world_gs = world.get('fields', {}).get('GameState', {})
    begun = gs.get('fields', {}).get('bReplicatedHasBegunPlay', {})
    if identity.get('address') != accepted.get('address') or identity.get('class') != 'AoCGameStateBP_C' or serializer.get('actor_address') != identity.get('address') or notify.get('receiver_address') != identity.get('address'):
        raise ValueError('Exact accepted retained gameplay GameState required')
    if world.get('identity', {}).get('name') != 'Verra_World_Master' or world_gs.get('status') != 'read' or (world_gs.get('value') or {}).get('address') != identity.get('address'):
        raise ValueError('Actual Verra UWorld.GameState must point to same accepted actor')
    if begun.get('status') != 'read' or begun.get('value') is not False or begun.get('metadata', {}).get('address') != prop['address']:
        raise ValueError('Fresh exact GameState BeginPlay flag must be observed false')
    if notify['implementation_rva'] == '0x5ef7800':
        _validate_reviewed_override(serializer, lifecycle, accepted, actors)
    return {'wire_handle':21, 'raw_bool_bits':1, 'value':True}


def encode_game_state_begin_play_content():
    stream = BitWriter().write(0,1).packed(21).write(1,1).packed(0)
    block = BitWriter().write(1,1).write(1,1).packed(stream.bits).raw(bytes(stream.data),stream.bits)
    return bytes(block.data), block.bits
