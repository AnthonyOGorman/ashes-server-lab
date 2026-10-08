"""Read-only live GameState BeginPlay property serializer and native notify thunk."""
import argparse
import json
from pathlib import Path
from dump_runtime_reflection import Reader, Reflection, ReadError, pointer
from protocol_proof import client_proof
from inspect_player_state import PlayerProbe


def infer_driver_is_server(code, server_connection):
    """Recognize only reviewed leaf grammars; never execute the virtual function."""
    # cmp qword ptr [rcx+138],0; sete al; ret, optionally preceded by xor eax,eax.
    leaf = bytes.fromhex('48 83 b9 38 01 00 00 00 0f 94 c0 c3')
    if code.startswith(leaf) or code.startswith(b'\x33\xc0' + leaf):
        return server_connection == 0
    return None


def predicate_proof(reader, probe, gs, world):
    report = {'status': 'unverified', 'required_helper_result': 3,
              'predicate_rva': '0x56f0e70', 'helper_rva': '0x3b847b0',
              'caller_optional_standalone': False, 'functions_invoked': False,
              'movement_proved': False}
    try:
        # Match exact original PE slices, not decompiler-inferred signatures.
        evidence = Path(__file__).resolve().parents[1] / 'evidence'
        code_ranges = {}
        for rva in (0x5ef7800, 0x56f0e70, 0x3b847b0, 0x4236c80, 0x1505900,
                    0x3b82890, 0x3b82920):
            code = (evidence / f'protocol_function_{rva:x}.bin').read_bytes()
            if reader.read(reader.base+rva, len(code)) != code:
                raise ReadError(f'Reviewed machine code mismatch at {rva:#x}')
            code_ranges[hex(rva)] = len(code)
        for rva, filename, size in ((0x4733960, 'protocol_fragment_4733960.bin', 160),
                                    (0x41861f0, 'protocol_fragment_41861f0.bin', 8)):
            code = (evidence/filename).read_bytes()[:size]
            if len(code) != size or reader.read(reader.base+rva, size) != code:
                raise ReadError(f'Reviewed lifecycle machine code mismatch at {rva:#x}')
            code_ranges[hex(rva)] = size
        report['reviewed_code_matches'] = True
        report['reviewed_code_ranges'] = code_ranges
        report['actor'] = probe.identity(gs, 'GameStateBase')
        report['world'] = probe.identity(world, 'World')
        name_prop = probe.property(gs, 'NetDriverName', 0x1f0, 8)
        if name_prop['type'] != 'NameProperty':
            raise ReadError('NetDriverName must be reflected NameProperty')
        name, number = reader.unpack(gs+0x1f0, '<II')
        # Exact1505900 uses initialized name pool EName mapping+14040, index11a.
        if reader.read(reader.base+0xd5edc59, 1) != b'\x01':
            raise ReadError('Built-in name mapping is not initialized')
        built_in = reader.unpack(reader.base+0xd5edec0+0x14040+0x11a*4, '<I')[0]
        report['net_driver_name'] = {'metadata': name_prop, 'index': name, 'number': number,
            'resolved': probe.reflection.names.get(name, number), 'builtin_11a_index': built_in,
            'builtin_11a_resolved': probe.reflection.names.get(built_in, 0)}
        if name != built_in or number != 0:
            raise ReadError('Named-driver lookup branch has not been reviewed')
        outer = int(probe.identity(gs, 'GameStateBase')['outer_address'], 16)
        owning = probe.object_field(outer, 'OwningWorld', 0xe0, 'World')
        if not owning or int(owning['address'], 16) != world:
            raise ReadError('GameState owning world disagrees with accepted Verra world')
        report['owning_level'] = probe.identity(outer, 'Level')
        report['owning_world'] = owning
        driver = probe.object_field(world, 'NetDriver', 0x58, 'NetDriver')
        if not driver:
            raise ReadError('Null driver fallback is not authorized by this proof')
        address = int(driver['address'], 16)
        connection = probe.object_field(address, 'ServerConnection', 0x138, 'NetConnection')
        target = reader.unpack(reader.unpack(address, '<Q')[0]+0x4b0, '<Q')[0]
        if not reader.base <= target < reader.base+reader.image_size:
            raise ReadError('Driver virtual4b0 must belong to exact executable')
        code = reader.read(target, 48)
        is_server = infer_driver_is_server(code, 0 if connection is None else int(connection['address'], 16))
        report['driver'] = driver
        report['driver_field_metadata'] = probe.property(world, 'NetDriver', 0x58, 8)
        report['driver_server_connection'] = connection
        report['server_connection_metadata'] = probe.property(address, 'ServerConnection', 0x138, 8)
        report['driver_virtual_4b0'] = {'rva': hex(target-reader.base), 'code_hex': code.hex(),
            'inferred_return': is_server, 'inference': 'exact cmp ServerConnection+138/zero leaf only'}
        report['inferred_helper_result'] = 3 if is_server is False else None
        level = probe.object_field(world, 'PersistentLevel', 0x50, 'Level')
        if not level:
            raise ReadError('World.PersistentLevel is null')
        settings = probe.object_field(int(level['address'], 16), 'WorldSettings', 0x2d0, 'WorldSettings')
        if not settings:
            raise ReadError('PersistentLevel.WorldSettings is null')
        settings_address = int(settings['address'], 16)
        settings_table = reader.unpack(settings_address, '<Q')[0]
        callbacks = {}
        for offset in (0x870, 0x878):
            callback = reader.unpack(settings_table+offset, '<Q')[0]
            if not reader.base <= callback < reader.base+reader.image_size:
                raise ReadError('WorldSettings callback must belong to exact executable')
            callbacks[hex(offset)] = {'rva': hex(callback-reader.base),
                'code_prefix_hex': reader.read(callback, 32).hex()}
        report['persistent_level'] = level
        report['persistent_level_metadata'] = probe.property(world, 'PersistentLevel', 0x50, 8)
        report['world_settings'] = settings
        report['world_settings_metadata'] = probe.property(int(level['address'], 16), 'WorldSettings', 0x2d0, 8)
        report['world_settings_callbacks'] = callbacks
        report['status'] = 'verified_client_predicate' if is_server is False else 'unverified_driver_virtual'
        report['predicate_would_accept_true_bool'] = is_server is False
    except (ReadError, OSError, UnicodeError) as exc:
        report['error'] = str(exc)
    return report


def inspect(snapshot, native_only=False):
    metadata = json.loads(Path(snapshot).read_text(encoding='utf-8'))
    reader = Reader(metadata['pid'], Path(metadata['exe']))
    try:
        reflection = Reflection(reader)
        cls = next(c for c in metadata['classes'] if c['name'] == 'GameStateBase')
        address = int(cls['address'], 16)
        if reflection.obj(address)['name'] != 'GameStateBase':
            raise ReadError('Exact current GameStateBase class required')
        props = reflection.properties(reader.unpack(address+0x70, '<Q')[0], cls['size'])
        prop = next(p for p in props if p['name'] == 'bReplicatedHasBegunPlay')
        if (prop['type'], prop['offset_in_object'], prop['element_size'], prop['array_dim']) != ('BoolProperty', 0x390, 1, 1):
            raise ReadError('Exact reflected BeginPlay bool required')
        field = int(prop['address'], 16)
        table = reader.unpack(field, '<Q')[0]
        serializer = reader.unpack(table+0xc8, '<Q')[0]
        if not reader.base <= serializer < reader.base+reader.image_size:
            raise ReadError('Property serializer must belong to exact executable')
        head = reader.unpack(address+0x68, '<Q')[0]
        seen = set()
        matches = []
        while head and len(seen) < 1024:
            if not pointer(head) or head in seen:
                raise ReadError('Invalid/cyclic UField list')
            seen.add(head)
            obj = reflection.obj(head)
            if obj['name'] == 'OnRep_ReplicatedHasBegunPlay':
                if reflection.class_name(obj['class_address']) != 'Function':
                    raise ReadError('Notify must be actual UFunction')
                target = reader.unpack(head+0xf8, '<Q')[0]
                if not reader.base <= target < reader.base+reader.image_size:
                    raise ReadError('Notify exec must be current executable')
                matches.append({'name':obj['name'], 'address':hex(head), 'exec_rva':hex(target-reader.base),
                    'flags':hex(reader.unpack(head+0xd0, '<I')[0])})
            head = reader.unpack(head+0x48, '<Q')[0]
        if head or len(matches) != 1:
            raise ReadError('Exactly one bounded current native notify required')
        lifecycle = None
        gs_class = address
        if not native_only:
            lifecycle = json.loads((Path(snapshot).parent/f'world_lifecycle_prerequisites_{metadata["pid"]}.json').read_text(encoding='utf-8'))
            gs_class = int(next(c for c in metadata['classes'] if c['name'] == 'AoCGameStateBP_C')['address'], 16)
            if reflection.obj(gs_class)['name'] != 'AoCGameStateBP_C':
                raise ReadError('Actual loaded gameplay GameState class required')
        gs = reader.unpack(gs_class+0x150, '<Q')[0] if native_only else int(lifecycle['game_state']['identity']['address'], 16)
        if reflection.obj(gs)['class_address'] != gs_class:
            raise ReadError('Actual GameState object must match verified reflected class')
        begun_value = bool(reader.read(gs+0x390, 1)[0] & prop['bool_layout']['field_mask'])
        if not native_only:
            probe = PlayerProbe(reader)
            world = int(lifecycle['world']['identity']['address'], 16)
            linked = probe.object_field(world, 'GameState', 0x1d0, 'GameStateBase')
            if not linked or int(linked['address'], 16) != gs or probe.identity(world, 'World')['name'] != 'Verra_World_Master':
                raise ReadError('Actual Verra World must still reference exact gameplay GameState')
        gs_table = reader.unpack(gs, '<Q')[0]
        notify_target = reader.unpack(gs_table+0x898, '<Q')[0]
        if not reader.base <= notify_target < reader.base+reader.image_size:
            raise ReadError('Notify implementation must belong to current executable')
        matches[0].update(implementation_rva=hex(notify_target-reader.base), virtual_offset='0x898',
            receiver_address=hex(gs), target_evidence='native_CDO_only' if native_only else 'actual_accepted_BP_actor_virtual_target')
        prerequisite = None if native_only else predicate_proof(reader, probe, gs, world)
        return {'pid':metadata['pid'], 'exe':metadata['exe'], 'access':'PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION',
            'property':prop, 'net_serialize_rva':hex(serializer-reader.base), 'net_serialize_virtual_offset':'0xc8',
            'notify':matches[0], 'game_state_class_index':reflection.obj(gs_class)['index'],
            'native_only':native_only, 'actor_address':hex(gs), 'observed_bool_value':begun_value,
            'actor_roles':PlayerProbe(reader).actor_roles(gs), 'game_specific_predicate': prerequisite,
            'bytes_read':reader.bytes_read}
    finally:
        reader.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-only', action='store_true', help='Offline native CDO research only; cannot authorize experiment')
    args = parser.parse_args()
    result = inspect(args.snapshot, args.native_only)
    result['client_proof'] = client_proof(result['pid'])
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
