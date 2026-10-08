"""Offline GameState BeginPlay prefix proof from original capture fragments.

Only the early scalar prefix is decoded. Large later arrays remain opaque.
This tool never transmits packets or uses a live game's memory.
"""
import argparse
import json
from pathlib import Path
import struct

from lab.unreal import BitReader, BitWriter, DecodeError
from lab.world_bootstrap import NetGUID


ROOT = Path(__file__).resolve().parents[1]


def decode(fixture):
    source = json.loads(Path(fixture).read_text(encoding="utf-8"))
    fragments = []
    body = BitWriter()
    for row in source["evidence"]:
        for bunch in row["decoded"].get("bunches", []):
            if row["direction"] == "server" and bunch["channel"] == 5 and not bunch["exports"]:
                fragments.append({"frame": row["frame"], "reliable_sequence": bunch["reliable_sequence"],
                                  "partial_flags": bunch["partial_flags"], "payload_bits": bunch["payload_bits"]})
                body.raw(bytes.fromhex(bunch["payload_hex"]), bunch["payload_bits"])
    if len(fragments) != 16 or [row["frame"] for row in fragments] != list(range(3717, 3733)) or \
       [row["reliable_sequence"] for row in fragments] != list(range(534, 550)) or \
       any(row["partial_flags"] != [0, 0, 0] for row in fragments[:-1]) or \
       fragments[-1]["partial_flags"] != [0, 0, 1]:
        raise DecodeError("Expected complete contiguous captured GameState body fragments")
    reader = BitReader(bytes(body.data), body.bits)
    actor = NetGUID.read(reader).as_dict()
    if actor != {"object_id": "0x000000000000516e", "server_id": 33, "randomizer": 2650652073}:
        raise DecodeError("Actor GUID does not identify the captured GameState")
    reader.pos = 388
    flags = [reader.read(1), reader.read(1)]
    length = reader.packed()
    start = reader.pos
    if flags != [1, 1] or length != 119515 or start != 414 or start+length != body.bits:
        raise DecodeError("Actor property content must exhaust the complete reassembled body")
    if reader.read(1):
        raise DecodeError("Property checksums must be disabled")
    fields = []
    expected = [(1, "AuthServerIDReplicated", 32), (8, "RemoteRole", 3), (16, "Role", 3),
                (19, "GameModeClass", 128), (21, "bReplicatedHasBegunPlay", 1),
                (23, "ReplicatedWorldTimeSecondsDouble", 64), (28, "GameTimeScalar", 32)]
    for handle, name, bits in expected:
        handle_start = reader.pos
        if reader.packed() != handle:
            raise DecodeError(f"Expected current-layout scalar handle {handle}")
        value_start = reader.pos
        if name == "GameModeClass":
            value = NetGUID.read(reader).as_dict()
        elif name == "ReplicatedWorldTimeSecondsDouble":
            value = struct.unpack("<d", reader.raw(bits))[0]
        elif name == "GameTimeScalar":
            value = struct.unpack("<f", reader.raw(bits))[0]
        else:
            value = reader.read(bits)
        fields.append({"handle": handle, "property": name, "handle_start_bit": handle_start,
                       "value_start_bit": value_start, "value_bits": bits, "value": value})
    reader.pos = body.bits-8
    trailing_packed_zero = reader.packed() == 0 and reader.remaining == 0
    return {"source_capture": source["source_capture"], "source_fixture": str(Path(fixture).resolve()),
            "fragments": fragments, "actor": actor, "body_bits": body.bits,
            "content_header_start_bit": 388, "has_rep_layout": flags[0], "is_actor": flags[1],
            "content_start_bit": start, "content_length_bits": length,
            "declared_content_exhausts_body": True, "checksum_enabled": 0,
            "fields": fields, "prefix_end_bit": 734, "last_eight_bits_are_packed_zero": trailing_packed_zero,
            "remainder": "Opaque; trailing zero is consistent with a terminator, not a complete property traversal proof",
            "begin_play_prefix_proof": "Handle21 has raw one-bit true followed immediately by handle23 and plausible captured world time"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "evidence/gamestate_property_capture.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = decode(args.fixture)
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
