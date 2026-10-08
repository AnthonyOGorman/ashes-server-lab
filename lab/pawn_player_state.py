"""Fixed accepted-pawn PlayerState association with reviewed receiver guard."""
import struct
from .controller_player_state import _dynamic_guid
from .unreal import BitWriter

def validate_pawn_player_state(layouts, receiver, actors, cache, pawn_guid, ps_guid):
    _dynamic_guid(pawn_guid)
    _dynamic_guid(ps_guid)
    if layouts.get('errors') or receiver.get('functions_invoked') is not False:
        raise ValueError('Clean layouts and read-only receiver proof required')
    candidates = [x for x in layouts.get('layouts', []) if x.get('class') == 'PlayerPawn_C']
    if len(candidates) != 1:
        raise ValueError('One exact pawn layout required')
    layout = candidates[0]
    if cache.get('class') != 'PlayerPawn_C' or any(layout.get(k) != cache.get(k) or layout.get(k) is None
            for k in ('class_index', 'class_serial')):
        raise ValueError('Current pawn cache/layout identity required')
    parent = next((x for x in layout['parents'] if x['parent_index'] == 15), None)
    command = next((x for x in layout['commands'] if x['command_index'] == 20), None)
    if not parent or not command:
        raise ValueError('Pawn PlayerState parent15/command20 required')
    prop = parent['property']
    if tuple(prop.get(k) for k in ('name','type','owner_class','offset_in_object','element_size','array_dim','referenced_type')) != (
            'PlayerState','ObjectProperty','Pawn',0x388,8,1,'PlayerState') or not {'Net','RepNotify'}.issubset(prop.get('flag_names', [])):
        raise ValueError('Exact replicated Pawn.PlayerState property required')
    if struct.unpack_from('<H', bytes.fromhex(parent['record_hex']), 0x1c)[0] != 20 or (
            command['parent_index'],command['command_type_byte'],command['uninterpreted_word_14'],command['property_address']) != (
            15,8,21,prop['address']) or any(c['command_type_byte'] == 0 for c in layout['commands'][:21]):
        raise ValueError('Verified scalar traversal to handle21 required')
    def accepted(guid, cls):
        items = [m for m in actors['network_guid_actor_matches'] if m['guid'] == guid]
        if len(items) != 1:
            raise ValueError('Unique accepted GUID required')
        m = items[0]
        if m['actor']['class'] != cls or m['weak_object_index'] != m['actor']['object_index'] or not isinstance(m['weak_object_serial'], int) or m['weak_object_serial'] <= 0:
            raise ValueError('Accepted actor index/serial required')
        return m
    pawn, ps = accepted(pawn_guid, 'PlayerPawn_C'), accepted(ps_guid, 'AoCPlayerStateBP_C')
    if not pawn.get('guid_cache') or pawn['guid_cache'] != ps.get('guid_cache') or pawn['actor']['outer_address'] != ps['actor']['outer_address']:
        raise ValueError('Pawn/PlayerState shared current cache and level required')
    if pawn['actor'].get('player_state', 'missing') is not None:
        raise ValueError('Pawn PlayerState must be explicitly null')
    if any(receiver.get(k) != v for k,v in {
            'actor_address':pawn['actor']['address'],'player_state_address':ps['actor']['address'],
            'pawn_guid':pawn_guid,'player_state_guid':ps_guid,'notify_rva':'0x433c720',
            'changed_callback_rva':'0x131c2f0','notify_bytes':'488b9188030000e924890000',
            'changed_callback_bytes':'c20000','net_serialize_rva':'0x170af50'}.items()) or receiver.get('property',{}).get('address') != prop['address']:
        raise ValueError('Exact current pawn serializer and reviewed notification required')
    return {'wire_handle':21,'dispatch_authorized':True,'movement_proved':False}

def encode_pawn_player_state_content(ps_guid):
    stream = BitWriter().write(0,1).packed(21)
    _dynamic_guid(ps_guid).write(stream)
    stream.packed(0)
    block = BitWriter().write(1,1).write(1,1).packed(stream.bits).raw(bytes(stream.data),stream.bits)
    return bytes(block.data),block.bits
