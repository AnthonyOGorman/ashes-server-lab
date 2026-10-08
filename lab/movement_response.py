"""Exact acknowledgement encoding; callers must first validate the move.

This pure encoder does not accept movement, choose an actor, or dispatch a
response. A decoded client location alone does not authorize acknowledgement.
"""
import math
import struct

from .unreal import BitWriter
from .world_bootstrap import encode_actor_rpc_content


def encode_move_ack_argument(timestamp):
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
        raise ValueError('finite move timestamp required')
    try:
        serialized = struct.pack('<f', timestamp)
    except (OverflowError, struct.error) as exc:
        raise ValueError('move timestamp outside float32 range') from exc
    inner = BitWriter().write(1, 1).raw(serialized)
    argument = BitWriter().write(1, 1).packed(inner.bits).raw(bytes(inner.data), inner.bits)
    return bytes(argument.data), argument.bits


def encode_move_ack_content(timestamp):
    """Exact cache max198/field35, for an externally verified pawn channel."""
    argument, bits = encode_move_ack_argument(timestamp)
    return encode_actor_rpc_content(35, 198, argument, bits)


def encode_move_correction_content(timestamp, location, velocity, movement_mode):
    """Ordinary exact correction, with no base/bone/root-motion references."""
    if movement_mode not in (1,3):
        raise ValueError('only walking/falling corrections supported')
    values=[timestamp,*location,*velocity]
    if len(location)!=3 or len(velocity)!=3 or not all(math.isfinite(v) for v in values):
        raise ValueError('finite correction vectors required')
    inner=BitWriter().write(0,1).raw(struct.pack('<f',timestamp)).write(0,4)
    inner.raw(struct.pack('<6d',*location,*velocity))
    inner.write(0,1).write(0,1).write(0,1)  # default gravity, no base/bone
    inner.write(movement_mode!=1,1)
    if movement_mode!=1:
        inner.write(movement_mode,8)
    inner.write(0,2)
    arg=BitWriter().write(1,1).packed(inner.bits).raw(bytes(inner.data),inner.bits)
    return encode_actor_rpc_content(35,198,bytes(arg.data),arg.bits)
