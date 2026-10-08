"""Read-only AoC movement codec for the exact installed UE5.6 client.

Contract: current AoC container b110928, per-move b110910/5ec10b0,
packed struct 3de86d0, response container a82ead0/3dfbcc0. This module
does not simulate movement or emit packets. It rejects unreviewed package-map
references and root-motion corrections; decoding client positions is not authority.
"""
import math
import struct

from .unreal import BitReader, DecodeError


def _finite(value):
    if not math.isfinite(value):
        raise DecodeError("nonfinite movement value")
    return value


def unpack_movement_argument(data, bits):
    """Single non-null StructProperty argument, then native packed bit count."""
    reader = BitReader(data, bits)
    if reader.read(1) != 1:
        raise DecodeError("missing packed movement argument")
    count = reader.packed()
    if not 1 <= count <= 8192 or count != reader.remaining:
        raise DecodeError("packed movement bit count mismatch or outside bounded codec")
    return BitReader(reader.raw(count), count)


def _vector(reader, scale):
    # Modern UE vector reader 1d44a60: 7-bit header, sign extension,
    # optional integer scaling. Header0/64 carry raw floats/doubles.
    header = reader.uint(128)
    width = header & 63
    if width == 0:
        fmt, size = ('d',64) if header >> 6 else ('f',32)
        return [_finite(struct.unpack('<'+fmt,reader.raw(size))[0]) for _ in range(3)]
    sign = 1 << (width-1)
    divisor = scale if header >> 6 else 1
    return [((reader.read(width) ^ sign)-sign)/divisor for _ in range(3)]


def _optional_byte(reader, default):
    return reader.read(8) if reader.read(1) else default


def _move(reader, kind):
    start = reader.pos
    timestamp = _finite(struct.unpack('<f',reader.raw(32))[0])
    acceleration = _vector(reader,10)
    location = _vector(reader,100)
    rotation = [reader.read(16)*360/65536 if reader.read(1) else 0 for _ in range(3)]
    flags = _optional_byte(reader,0)
    if reader.read(1):
        raise DecodeError("movement base object requires reviewed package-map decoder")
    if reader.read(1):
        raise DecodeError("movement bone name requires reviewed name decoder")
    movement_mode = _optional_byte(reader,1)
    sign_bits = [reader.read(1) for _ in range(4)]
    # Native63e7a80 gives positive precedence if both signs are set.
    axes = [1 if sign_bits[i] else -1 if sign_bits[i+1] else 0 for i in (0,2)]
    return {'kind':kind,'timestamp':timestamp,'acceleration':acceleration,
            'client_location':location,'control_rotation':rotation,'compressed_flags':flags,
            'movement_mode':movement_mode,'custom_axis_sign_bits':sign_bits,
            'custom_axes':axes,'serialized_bits':reader.pos-start}


def decode_server_move_argument(data, bits):
    """Decode modern-version moves with no base/bone references, consuming all bits."""
    reader = unpack_movement_argument(data,bits)
    moves = [_move(reader,'new')]
    pending = bool(reader.read(1))
    hybrid = bool(reader.read(1)) if pending else False
    if pending:
        moves.append(_move(reader,'pending'))
    old = bool(reader.read(1))
    if old:
        moves.append(_move(reader,'old'))
    disable_combining = bool(reader.read(1))
    if reader.remaining:
        raise DecodeError("movement container has trailing bits")
    return {'moves':moves,'pending_move_present':pending,'pending_hybrid_flag':hybrid,
            'old_move_present':old,'disable_combining':disable_combining,
            'inner_bits':reader.limit,'movement_proved':False,
            'evidence':'exact_binary_custom_serializer_and_capture; client_report_only'}


def decode_move_response_argument(data,bits):
    """Decode ack or ordinary correction with no package-map/root-motion references."""
    reader = unpack_movement_argument(data,bits)
    ack = bool(reader.read(1))
    timestamp = _finite(struct.unpack('<f',reader.raw(32))[0])
    result = {'acknowledgement':ack,'timestamp':timestamp,'inner_bits':reader.limit,
              'movement_proved':False}
    if not ack:
        flags = [reader.read(1) for _ in range(4)]
        location = [_finite(struct.unpack('<d',reader.raw(64))[0]) for _ in range(3)]
        velocity = [_finite(struct.unpack('<d',reader.raw(64))[0]) for _ in range(3)]
        gravity = ([_finite(struct.unpack('<d',reader.raw(64))[0]) for _ in range(3)]
                   if reader.read(1) else [0.0,0.0,-1.0])
        rotation = ([reader.read(16)*360/65536 if reader.read(1) else 0 for _ in range(3)]
                    if flags[1] else [0.0,0.0,0.0])
        if reader.read(1):
            raise DecodeError('correction base object requires reviewed package-map decoder')
        if reader.read(1):
            raise DecodeError('correction bone name requires reviewed name decoder')
        movement_mode = _optional_byte(reader,1)
        trailing_flags = [reader.read(1) for _ in range(2)]
        if flags[2] or flags[3]:
            raise DecodeError('root-motion correction requires reviewed root-motion codec')
        result['correction'] = {'server_location':location,'server_velocity':velocity,
            'gravity_direction':gravity,'rotation':rotation,'movement_mode':movement_mode,
            'flags_at_offsets_08_0b':flags,'flags_at_offsets_89_8a':trailing_flags}
    if reader.remaining:
        raise DecodeError("move response has trailing bits")
    return result
