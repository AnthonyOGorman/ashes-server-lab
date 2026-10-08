"""Read-only adapters. No game invocation, server POST or shared-file writes."""
from __future__ import annotations

import json
import math
import struct
import sys
import time
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / 'tools'))


class Unavailable(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Unavailable('Server telemetry must remain on the fixed loopback endpoint')


class ServerTelemetry:
    PATHS = {'state': '/api/state', 'connections': '/api/connections',
             'world': '/api/world-view', 'events': '/api/events'}

    def get(self, kind):
        url = 'http://127.0.0.1:8865' + self.PATHS[kind]
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(Request(url, method='GET'), timeout=3) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise Unavailable('Server response exceeded telemetry budget')
        value = json.loads(raw)
        if kind == 'state':
            value = {k: value.get(k) for k in ('backend', 'client', 'client_launch',
                     'movement_settings', 'online_players', 'connections', 'geometry_error')}
        elif kind == 'world':
            # Trails and geometry are unrelated to the small observation tools.
            value = {'players': [{k: v for k, v in p.items() if k != 'trail'}
                                for p in value.get('players', [])]}
        return {'source': 'server_observation', 'observed_at': time.time(), 'data': value}


class NativeTelemetry:
    def __init__(self, pid=None, seed_path=None):
        self.pid = pid
        own_seed = WORKSPACE / 'client-testing/binding.json'
        self.seed_path = seed_path or (own_seed if own_seed.is_file() else WORKSPACE / 'CPP/data/client-inspection.json')
        self.bound_process = None

    @staticmethod
    def same_process(a, b):
        return all(a.get(k) == b.get(k) for k in
                   ('pid', 'exe', 'sha256', 'process_created_filetime'))

    def proof(self):
        from protocol_proof import client_proof
        if self.pid is None:
            seed = json.loads(self.seed_path.read_text(encoding='utf-8'))
            self.pid = seed['client_proof']['pid']
        fresh = client_proof(self.pid)
        if self.bound_process is not None and not self.same_process(self.bound_process, fresh):
            raise Unavailable('Client lifetime changed; start a new bridge for the new session')
        self.bound_process = fresh
        return fresh

    @staticmethod
    def identity(probe, address, expected=None):
        if not address:
            raise Unavailable('Required live object is absent')
        # Bypass the legacy probe object cache for every identity check.
        probe.reflection.cache.pop(address, None)
        obj = probe.identity(address, expected)
        index = obj['object_index']
        if not 0 <= index < probe.reflection.count:
            raise Unavailable('Object index is outside live GObjects')
        chunk = probe.reader.unpack(probe.reflection.chunks + (index // 65536) * 8, '<Q')[0]
        item = probe.reader.read(chunk + (index % 65536) * 24, 24)
        pointer, flags = struct.unpack_from('<QI', item)
        serial = struct.unpack_from('<i', item, 16)[0]
        if pointer != address or serial <= 0 or flags & 0x10200000:
            raise Unavailable('Object was destroyed or its weak identity changed')
        return {**obj, 'serial': serial}

    @staticmethod
    def address(field):
        value = field.get('value')
        return int(value['address'], 16) if value else 0

    @staticmethod
    def values(fields):
        return {k: v.get('value') if v.get('status') == 'read' else
                {'unavailable': v.get('status'), 'error': v.get('error')}
                for k, v in fields.items()}

    @staticmethod
    def text_field(probe, address, name):
        prop = probe.properties_for(address).get(name)
        if not prop or prop['type'] != 'StrProperty' or prop['element_size'] != 16:
            return {'unavailable': 'not_a_reflected_FString'}
        data, count, capacity = probe.reader.unpack(address + prop['offset_in_object'], '<Qii')
        if not 0 <= count <= capacity <= 4096:
            raise Unavailable('Invalid bounded FString')
        if count == 0:
            return ''
        raw = probe.reader.read(data, count * 2)
        if raw[-2:] != b'\x00\x00':
            raise Unavailable('Unterminated FString')
        return raw[:-2].decode('utf-16-le')

    def sample(self):
        from dump_runtime_reflection import Reader, ReadError
        from inspect_movement_prerequisites import MovementProbe
        from protocol_proof import EXPECTED_EXE
        before = self.proof()
        seed = json.loads(self.seed_path.read_text(encoding='utf-8'))
        if not self.same_process(before, seed.get('client_proof', {})):
            raise Unavailable('Inspection seed belongs to another client lifetime')
        # Old snapshots supply candidate addresses ONLY. Values and links are reread.
        local = seed.get('local_players', [])
        if len(local) != 1:
            raise Unavailable('Exactly one inspected LocalPlayer is required')
        reader = Reader(self.pid, EXPECTED_EXE, budget=8 * 1024 * 1024)
        try:
            probe = MovementProbe(reader)
            local_address = int(local[0]['address'], 16)
            local_id = self.identity(probe, local_address, 'LocalPlayer')
            for key in ('object_index', 'name', 'class', 'serial'):
                if local[0].get(key) != local_id[key]:
                    raise Unavailable('LocalPlayer seed identity changed; refresh inspection')
            controller_address = self.address(probe.fields(local_address, ['PlayerController'])['PlayerController'])
            controller = self.identity(probe, controller_address, 'PlayerController')
            links = probe.fields(controller_address, ['Pawn', 'AcknowledgedPawn', 'PlayerState'])
            pawn_address = self.address(links['Pawn'])
            if not pawn_address or self.address(links['AcknowledgedPawn']) != pawn_address:
                raise Unavailable('The local controller has no acknowledged possessed pawn')
            pawn = self.identity(probe, pawn_address, 'Pawn')
            pawn_links = probe.fields(pawn_address, ['Controller', 'RootComponent', 'CharacterMovement', 'PlayerState'])
            if self.address(pawn_links['Controller']) != controller_address:
                raise Unavailable('Possessed pawn does not point back to the local controller')
            root_address = self.address(pawn_links['RootComponent'])
            movement_address = self.address(pawn_links['CharacterMovement'])
            root = self.identity(probe, root_address, 'SceneComponent')
            movement_id = self.identity(probe, movement_address, 'CharacterMovementComponent')
            root_values = probe.fields(root_address, ['AttachParent', 'RelativeLocation'])
            if root_values['AttachParent'].get('status') != 'read' or root_values['AttachParent'].get('value') is not None:
                raise Unavailable('Unattached root required to interpret world position')
            position = root_values['RelativeLocation'].get('value')
            if not isinstance(position, list) or len(position) != 3 or not all(math.isfinite(v) for v in position):
                raise Unavailable('Fresh finite reflected world position unavailable')
            movement = self.values(probe.fields(movement_address, [
                'Velocity', 'Acceleration', 'MovementMode', 'CustomMovementMode',
                'MaxWalkSpeed', 'MaxRunSpeed', 'MaxSprintSpeed', 'GravityScale',
                'bUseMovementSpeedStat', 'bPredictMovement', 'bDeferServerMoves']))
            pawn_state = self.values(probe.fields(pawn_address, ['Role', 'RemoteRole', 'CustomTimeDilation']))
            player_state_address = self.address(links['PlayerState'])
            player_state = self.identity(probe, player_state_address, 'PlayerState') if player_state_address else None
            player_name = self.text_field(probe, player_state_address, 'PlayerNamePrivate') if player_state_address else {'unavailable': 'Controller.PlayerState is null'}
            level_address = int(pawn['outer_address'], 16)
            level = self.identity(probe, level_address, 'Level')
            world_address = self.address(probe.fields(level_address, ['OwningWorld'])['OwningWorld'])
            world = self.identity(probe, world_address, 'World')
            world_fields = self.values(probe.fields(world_address, ['bBegunPlay', 'bActorsInitialized', 'StreamingLevels']))
            from .floor import observe_floor
            try:
                floor = observe_floor(probe, movement_address)
            except (Unavailable, ReadError, KeyError, TypeError, ValueError) as exc:
                floor = {'status': 'unavailable', 'error': str(exc)}
            # Detect teardown/component swaps during this non-atomic snapshot.
            for address, expected in ((local_address, local_id), (controller_address, controller),
                                      (pawn_address, pawn), (root_address, root),
                                      (movement_address, movement_id), (world_address, world)):
                if self.identity(probe, address) != expected:
                    raise Unavailable('Object identity changed during the observation')
            if probe.fields(controller_address, ['Pawn', 'AcknowledgedPawn', 'PlayerState']) != links or probe.fields(pawn_address, ['Controller', 'RootComponent', 'CharacterMovement', 'PlayerState']) != pawn_links:
                raise Unavailable('Possession/component links changed during observation')
            after = self.proof()
            return {'source': 'native_reflection_read_only', 'client_proof': after,
                    'started_at': before['observed_at'], 'observed_at': time.time(),
                    'local_player': local_id, 'controller': controller, 'pawn': pawn,
                    'root': root, 'position_cm': position, 'movement': movement,
                    'floor': floor,
                    'movement_component': movement_id, 'pawn_state': pawn_state,
                    'player_state': player_state, 'player_name': player_name,
                    'player_name_source': 'PlayerState.PlayerNamePrivate; displayed character name may come from CharacterInfo',
                    'pawn_player_state': pawn_links['PlayerState'].get('value'),
                    'world': {'identity': world, 'level': level, 'fields': world_fields,
                              'all_streaming_cells_visible': 'not_measured'},
                    'resources': {'health': 'not_mapped', 'mana': 'not_mapped', 'stamina': 'not_mapped'},
                    'bytes_read': reader.bytes_read, 'snapshot_atomic': False,
                    'functions_invoked': False, 'memory_written': False}
        except (ReadError, KeyError, TypeError) as exc:
            raise Unavailable(str(exc)) from exc
        finally:
            reader.close()
