"""Offline exact-capture controller property block proof, not a replay tool.

This bounded fixture decoder deliberately anchors to frame 3710/body bit 508.
The preceding actor spawn suffix is not inferred. Property labels come from
the independently saved current RepLayout; decoding must exhaust the complete
519-bit content block and match the following GlobalGMCommands object header.
"""
import argparse
import json
from pathlib import Path
import struct

from lab.unreal import BitReader, DecodeError
from lab.world_bootstrap import NetGUID


ROOT = Path(__file__).resolve().parents[1]


def decode(fixture):
    source = json.loads(Path(fixture).read_text(encoding="utf-8"))
    frame = next(row for row in source["evidence"] if row["frame"] == 3710)
    bunch = next(row for row in frame["decoded"]["bunches"]
                 if row["channel"] == 3 and row["payload_bits"] == 1314)
    reader = BitReader(bytes.fromhex(bunch["payload_hex"]), bunch["payload_bits"])
    reader.pos = 508
    flags = [reader.read(1), reader.read(1)]
    length = reader.packed()
    start, end = reader.pos, reader.pos + length
    if flags != [1, 1] or start != 526 or length != 519:
        raise DecodeError("Captured actor content framing differs from proven fixture")
    checksum = reader.read(1)
    if checksum:
        raise DecodeError("Captured property checksums must be disabled")
    fields = []
    expected = [(1, "AuthServerIDReplicated", 32), (8, "RemoteRole", 3),
                (16, "Role", 3), (19, "PlayerState", 128),
                (22, "SpawnLocation", 192), (24, "CaravanLaunchNode", 64),
                (52, "SummonCooldownTimer", 32)]
    for handle, name, bits in expected:
        handle_start = reader.pos
        actual = reader.packed()
        if actual != handle:
            raise DecodeError(f"Expected packed handle {handle}, got {actual}")
        value_start = reader.pos
        if name == "PlayerState":
            value = NetGUID.read(reader).as_dict()
        elif name == "SpawnLocation":
            value = list(struct.unpack("<ddd", reader.raw(bits)))
        elif name == "SummonCooldownTimer":
            value = struct.unpack("<f", reader.raw(bits))[0]
        else:
            value = reader.read(bits)
        fields.append({"handle": handle, "property": name, "handle_start_bit": handle_start,
                       "value_start_bit": value_start, "value_bits": bits, "value": value})
    terminator_start = reader.pos
    if reader.packed() != 0 or reader.pos != end:
        raise DecodeError("Packed zero terminator must exhaust actor content exactly")
    next_flags = [reader.read(1), reader.read(1)]
    subobject = NetGUID.read(reader).as_dict()
    if next_flags != [0, 0] or subobject != {"object_id": "0x00000000000925a2", "server_id": 33,
                                           "randomizer": 2650652073}:
        raise DecodeError("Following subobject boundary does not agree")
    return {"source_capture": source["source_capture"], "source_fixture": str(Path(fixture).resolve()),
            "frame": 3710, "channel": 3, "body_bits": 1314, "content_header_start_bit": 508,
            "has_rep_layout": flags[0], "is_actor": flags[1], "content_length_bits": length,
            "content_start_bit": start, "content_end_bit": end,
            "checksum_enabled": checksum, "checksum_bit_position": start,
            "fields": fields, "terminator_start_bit": terminator_start,
            "property_content_exhausted": True, "following_header_start_bit": end,
            "following_flags": next_flags, "following_subobject": subobject,
            "evidence": "offline exact capture and independently saved RepLayout scalar handles",
            "limitations": "No live dispatch. Preceding actor spawn suffix remains unparsed. Role swapping requires receiver analysis."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "evidence/world_bootstrap_capture.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = decode(args.fixture)
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
