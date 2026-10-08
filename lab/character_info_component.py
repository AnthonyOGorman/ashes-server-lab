"""Fixed existing CharacterInfo export and property-empty replication block.

This binds a fresh network identity to an existing default subobject. It sends
no character data and marks no load checkpoint complete. External fresh actor,
component and receive-path proofs are required before protocol dispatch.
"""
from .controller_player_state import _dynamic_guid
from .unreal import BitWriter
from .world_bootstrap import ObjectRef, encode_exports
import re

CHARACTER_INFO_NAME = 'BaseCharacterInfo'
CAPTURED_PLAYER_INFO_CHECKSUM = 2952361071

def encode_character_info_export(pawn_guid, component_guid):
    pawn, component = _dynamic_guid(pawn_guid), _dynamic_guid(component_guid)
    if pawn == component:
        raise ValueError('Component must have its own fresh dynamic GUID')
    return encode_exports([ObjectRef(component, CHARACTER_INFO_NAME,
        ObjectRef(pawn, no_load=True), CAPTURED_PLAYER_INFO_CHECKSUM, True)])

def encode_character_info_empty_content(component_guid):
    component = _dynamic_guid(component_guid)
    content = BitWriter().write(0,1).packed(0)
    header = BitWriter().write(1,1).write(0,1)
    component.write(header)
    header.write(1,1).packed(content.bits).raw(bytes(content.data),content.bits)
    return bytes(header.data),header.bits

def encode_character_info_name_content(component_guid, name):
    if not isinstance(name,str) or not 1<=len(name)<=64 or not name.isascii() or not name.isalnum():
        raise ValueError('Bounded local ASCII character name required')
    component=_dynamic_guid(component_guid)
    content=BitWriter().write(0,1).packed(8).string(name).packed(0)
    header=BitWriter().write(1,1).write(0,1)
    component.write(header)
    header.write(1,1).packed(content.bits).raw(bytes(content.data),content.bits)
    return bytes(header.data),header.bits

def validate_character_info_name(actors,appearance,mapping,layouts,pawn_guid,component_guid):
    result=_validate_character_info_mapping(actors,appearance,mapping,pawn_guid,component_guid)
    name=appearance['character_information']['fields']['CharacterName']
    if name.get('status')!='read' or name.get('value')!='Player':
        raise ValueError('Explicitly observed current placeholder name Player required')
    layout=_player_info_layout(layouts)
    command=layout['commands'][7]
    prop=layout['parents'][4]['property']
    if (command.get('parent_index'),command.get('command_type_byte'),command.get('uninterpreted_word_14'),command.get('property_address'))!=(4,19,8,prop['address']) or (
        prop.get('name'),prop.get('type'),prop.get('owner_class'),prop.get('offset_in_object'))!=('CharacterName','StrProperty','CharacterInfo',304) or any(c['command_type_byte']==0 for c in layout['commands'][:8]):
        raise ValueError('Exact scalar CharacterName handle8 required')
    proof=mapping.get('properties',{}).get('CharacterName',{})
    notifications=[n for n in mapping.get('notification_functions',[]) if n.get('name')=='OnRep_CharacterName']
    if proof.get('property',{}).get('address')!=prop['address'] or (
        proof.get('serializer_rva'),proof.get('serialize_item_rva'))!=('0x16de940','0x1610120') or mapping.get('notification_virtuals',{}).get('0x570')!='0x6c2b150' or (
        len(notifications)!=1 or notifications[0].get('owner')!='CharacterInfo' or notifications[0].get('native_rva')!='0x5d81500'):
        raise ValueError('Exact reviewed string serializer and notification required')
    result.update(dispatch_authorized=True,wire_handle=8)
    return result

def _validate_character_info_mapping(actors,appearance,mapping,pawn_guid,component_guid):
    result=validate_character_info_identity(actors,appearance,pawn_guid)
    matches=mapping.get('network_guid_component_matches',[])
    if len(matches)!=1 or matches[0].get('guid')!=component_guid or matches[0].get('pawn_guid')!=pawn_guid or (
        matches[0].get('component')!=appearance['character_information']['identity'] or
        mapping.get('cached_actor_owner',{}).get('address')!=appearance['pawn']['identity']['address'] or
        mapping.get('functions_invoked') is not False):
        raise ValueError('Exact accepted existing component network identity required')
    pawn=next(m for m in actors['network_guid_actor_matches'] if m['guid']==pawn_guid)
    match=matches[0]
    if match.get('guid_cache')!=pawn.get('guid_cache') or match.get('weak_object_index')!=result['component_index'] or (
        not isinstance(match.get('weak_object_serial'),int) or match['weak_object_serial']<=0):
        raise ValueError('Component must share current pawn cache and validated weak identity')
    return result

def _player_info_layout(layouts):
    candidates=[l for l in layouts.get('layouts',[]) if l.get('class')=='PlayerInfo']
    if layouts.get('errors') or len(candidates)!=1:
        raise ValueError('One clean actual PlayerInfo replication layout required')
    return candidates[0]

def character_guid_words(value):
    if not isinstance(value,str) or re.fullmatch(r'[0-9a-fA-F]{32}',value) is None or int(value,16)==0:
        raise ValueError('Nonnull own-server character ID in canonical32-digit form required')
    return tuple(int(value[i:i+8],16) for i in range(0,32,8))

def encode_character_info_guid_content(component_guid, character_id):
    component=_dynamic_guid(component_guid)
    content=BitWriter().write(0,1)
    for handle,word in zip(range(3,7),character_guid_words(character_id)):
        content.packed(handle).write(word,32)
    content.packed(0)
    header=BitWriter().write(1,1).write(0,1)
    component.write(header)
    header.write(1,1).packed(content.bits).raw(bytes(content.data),content.bits)
    return bytes(header.data),header.bits

def validate_character_info_guid(actors,appearance,mapping,layouts,pawn_guid,component_guid):
    result=_validate_character_info_mapping(actors,appearance,mapping,pawn_guid,component_guid)
    fields=appearance['character_information']['fields']['CharacterGuid']
    if fields.get('status')!='read_struct' or fields.get('struct')!='Guid' or any(
        fields['fields'][n].get('status')!='read' or fields['fields'][n].get('value')!=0 for n in ('A','B','C','D')):
        raise ValueError('Explicitly observed zero current character GUID required')
    layout=_player_info_layout(layouts)
    parent=layout['parents'][2]['property']
    if (parent.get('name'),parent.get('type'),parent.get('referenced_type'),parent.get('offset_in_object'),parent.get('element_size'))!=('CharacterGuid','StructProperty','Guid',280,16):
        raise ValueError('Exact expanded replicated Guid struct required')
    if any(c['command_type_byte']==0 for c in layout['commands'][:6]):
        raise ValueError('Scalar traversal to all four Guid words required')
    for index,name in enumerate(('A','B','C','D')):
        prop=fields['fields'][name]['metadata']
        command=layout['commands'][index+2]
        serializer=mapping.get('guid_fields',{}).get(name,{})
        if (prop.get('name'),prop.get('type'),prop.get('offset_in_object'),prop.get('element_size'),prop.get('array_dim'))!=(name,'IntProperty',index*4,4,1) or (
            command.get('parent_index'),command.get('command_type_byte'),command.get('uninterpreted_word_14'),command.get('offset_in_object'),command.get('property_address'))!=(2,5,index+3,280+index*4,prop['address']) or (
            serializer.get('property')!=prop or serializer.get('serializer_rva')!='0x16de940' or serializer.get('serialize_item_rva')!='0x16100a0'):
            raise ValueError('Exact independently inspected Guid child scalar required')
    notifications=[n for n in mapping.get('notification_functions',[]) if n.get('name')=='OnRep_CharacterGuid']
    if mapping.get('notification_virtuals',{}).get('0x560')!='0x6c2b0c0' or len(notifications)!=1 or (
        notifications[0].get('owner'),notifications[0].get('native_rva'))!=('CharacterInfo','0x5d81460'):
        raise ValueError('Exact reviewed Guid registration notification required')
    result.update(dispatch_authorized=True,wire_handles=[3,4,5,6])
    return result

def validate_character_info_identity(actors, appearance, pawn_guid):
    if actors.get('errors') or appearance.get('errors'):
        raise ValueError('Clean actor/component inspection required')
    matches = [m for m in actors['network_guid_actor_matches'] if m['guid'] == pawn_guid]
    if len(matches) != 1 or matches[0]['actor']['class'] != 'PlayerPawn_C':
        raise ValueError('One accepted current PlayerPawn GUID required')
    pawn = matches[0]['actor']
    if appearance.get('pawn',{}).get('identity',{}).get('address') != pawn['address']:
        raise ValueError('Appearance snapshot must bind the accepted pawn')
    info = appearance.get('character_information',{})
    identity = info.get('identity',{})
    if identity.get('name') != CHARACTER_INFO_NAME or identity.get('class') != 'PlayerInfo' or (
            'CharacterInfo' not in identity.get('ancestors',[]) or identity.get('outer_address') != pawn['address']):
        raise ValueError('Exact existing PlayerInfo default subobject required')
    if info.get('fields',{}).get('bReplicates',{}).get('value') is not True:
        raise ValueError('Current replicated component must belong to the accepted pawn')
    return {'component_address':identity['address'],'component_index':identity['object_index'],
            'default_subobject_name':CHARACTER_INFO_NAME,'character_data_supplied':False,
            'load_complete_claimed':False,'dispatch_authorized':False}

def validate_character_info_export(actors, appearance, receiver, pawn_guid, component_guid):
    result=validate_character_info_identity(actors,appearance,pawn_guid)
    component=_dynamic_guid(component_guid)
    if any(m.get('guid')==component.as_dict() for m in actors['network_guid_actor_matches']):
        raise ValueError('Fresh unused component network identity required')
    if receiver.get('functions_invoked') is not False or receiver.get('component') != appearance['character_information']['identity']:
        raise ValueError('Actual component receive proof required')
    pre=receiver.get('virtual_targets',{}).get('0x2a8',{})
    post=receiver.get('virtual_targets',{}).get('0x2b0',{})
    if pre.get('rva')!='0x131c2f0' or not pre.get('bytes','').startswith('c20000') or (
        post.get('rva')!='0x15f4670' or not post.get('bytes','').startswith('e97b7cd2ff') or
        post.get('jump_target_rva')!='0x131c2f0' or post.get('jump_target_bytes')!='c20000'):
        raise ValueError('Exact reviewed no-op PreNetReceive/PostNetReceive required')
    result['dispatch_authorized']=True
    return result
