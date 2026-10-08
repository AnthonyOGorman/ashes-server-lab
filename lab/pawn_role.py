"""Fixed experimental pawn autonomy property; no dispatch or arbitrary fields."""
import struct
from .unreal import BitWriter

ROLE_NAMES = (("ROLE_None", 0), ("ROLE_SimulatedProxy", 1), ("ROLE_AutonomousProxy", 2),
              ("ROLE_LightweightProxy", 3), ("ROLE_Authority", 4), ("ROLE_MAX", 5))


def validate_pawn_role_layout(layouts, role_proof, pawn_cache):
    if layouts.get("errors"):
        raise ValueError("Exact current RepLayout must validate without errors")
    layout = next((item for item in layouts.get("layouts", []) if item.get("class") == "PlayerPawn_C"), None)
    if layout is None or (layout.get("class_index"), layout.get("class_serial")) != (pawn_cache.get("class_index"), pawn_cache.get("class_serial")):
        raise ValueError("Pawn RepLayout class index/serial must match the verified live cache")
    parents, commands = layout["parents"], layout["commands"]
    for name, parent_index, command_index, offset in (("RemoteRole", 7, 7, 0x180), ("Role", 10, 15, 0x1f8)):
        parent = next((item for item in parents if item.get("parent_index") == parent_index), None)
        if parent is None:
            raise ValueError("Required Role/RemoteRole parent entry is absent")
        prop = parent["property"]
        if (prop.get("name"), prop.get("type"), prop.get("offset_in_object"), prop.get("element_size"), prop.get("array_dim")) != (name, "ByteProperty", offset, 1, 1):
            raise ValueError("Exact reflected scalar Role/RemoteRole metadata required")
        if struct.unpack_from("<H", bytes.fromhex(parent["record_hex"]), 0x1c)[0] != command_index:
            raise ValueError("Role counterpart parent start command must agree with native swap path")
        cmd = next((item for item in commands if item.get("command_index") == command_index), None)
        if cmd is None:
            raise ValueError("Required Role/RemoteRole command entry is absent")
        if cmd["parent_index"] != parent_index or cmd["command_type_byte"] != 6 or cmd["uninterpreted_word_14"] != command_index+1 or cmd.get("property_address") != prop["address"]:
            raise ValueError("Exact scalar role command and relative handle must agree")
        if any(item["command_type_byte"] == 0 for item in commands[:command_index+1]):
            raise ValueError("Array child spans would require a different handle traversal")
        proof = next((item for item in role_proof.get("properties", []) if item["name"] == name), None)
        if proof is None or proof["address"] != prop["address"] or proof["net_serialize_rva"] != "0x170ad20" or proof["net_serialize_virtual_offset"] != "0xc8":
            raise ValueError("Live role property serializer must be the verified exact function")
        if tuple((item["name"], item["value"]) for item in proof["enum_names"]) != ROLE_NAMES:
            raise ValueError("Actual ENetRole values must match the verified custom enum")
    return {"server_property": "RemoteRole", "wire_handle": 8, "serialized_bits": 3,
            "desired_client_role": 2, "role_swap": "native_receiver_RemoteRole_to_Role"}


def encode_pawn_autonomous_content():
    """Only RemoteRole handle8 = AutonomousProxy2, with checksum disabled.

    Requires external current proof before dispatch. No GUID is serialized:
    the target is the connection's already-open pawn actor channel9.
    """
    stream = BitWriter().write(0, 1).packed(8).write(2, 3).packed(0)
    block = BitWriter().write(1, 1).write(1, 1).packed(stream.bits).raw(bytes(stream.data), stream.bits)
    return bytes(block.data), block.bits
