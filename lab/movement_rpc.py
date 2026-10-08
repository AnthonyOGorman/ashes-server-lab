"""Exact pawn RPC envelopes; packed movement data remains opaque.

Names/max198 are from the installed client's inherited PlayerPawn_C cache.
Captured real gameplay validates field44 and field35 envelopes; field76 is
cache-known but has no complete RPC-only fixture in the supplied capture.
This module neither executes moves nor constructs server responses.
"""
from .unreal import DecodeError
from .world_bootstrap import decode_actor_rpc_content

PAWN_RPC_MAX = 198
MOVEMENT_FIELDS = {
    "client": {44: "ServerMovePacked"},
    "server": {35: "ClientMoveResponsePacked", 76: "ReliableClientMoveResponsePacked"},
}


def decode_pawn_movement_rpc(payload: bytes, payload_bits: int, direction: str):
    """Recognize a complete RPC-only pawn block under its external cache.

Caller must establish that the bunch belongs to the accepted pawn channel,
and reject partial/export/must-map/open/close blocks before calling. Mixed
blocks preserve unrecognized field indices without assigning them semantics.
At least one movement field must occur; malformed framing is never accepted.
"""
    if direction not in MOVEMENT_FIELDS:
        raise ValueError("direction must be client or server")
    if isinstance(payload_bits, bool) or not isinstance(payload_bits, int) or not 0 <= payload_bits <= 8224:
        raise DecodeError("invalid bounded pawn payload bits")
    decoded = decode_actor_rpc_content(payload, payload_bits, PAWN_RPC_MAX)
    fields = []
    recognized = 0
    for field in decoded["fields"]:
        name = MOVEMENT_FIELDS[direction].get(field["field_index"])
        entry = dict(field)
        if name:
            recognized += 1
            entry["rpc"] = name
            entry["packed_data_decoded"] = False
        fields.append(entry)
    if not recognized:
        raise DecodeError("no movement RPC for supplied direction")
    return {"class_field_max": PAWN_RPC_MAX, "direction": direction,
            "fields": fields, "movement_rpc_count": recognized,
            "movement_proved": False,
            "evidence": "exact_cache_and_capture_verified_rpc_envelope_inner_data_opaque"}
