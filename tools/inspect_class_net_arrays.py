"""Bounded read-only UClass array discovery, with exact reflection pointers.

Candidate arrays are diagnostics, not wire-index claims. This tool never calls
the game, writes process memory, or controls the client.
"""
import argparse
import json
from pathlib import Path
import struct

from dump_runtime_reflection import Reader, Reflection, ReadError, pointer


def inspect(snapshot):
    report = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    reader = Reader(report["pid"], Path(report["exe"]))
    result = {"pid": report["pid"], "source_snapshot": str(snapshot),
              "access": "PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION",
              "wire_handle_claims": "None: validated reflection arrays only", "classes": []}
    known = {}
    for cls in report["classes"]:
        for item in cls.get("net_functions", []) + cls.get("properties", []):
            known[int(item["address"], 16)] = item
    try:
        reflection = Reflection(reader)
        for cls in report["classes"]:
            address = int(cls["address"], 16)
            live = reflection.obj(address)
            if live["name"] != cls["name"] or ("object_index" in cls and live["index"] != cls["object_index"]):
                raise ReadError("Snapshot class identity no longer agrees with live process")
            raw = reader.read(address, 0x240)
            properties = reflection.properties(struct.unpack_from("<Q", raw, 0x70)[0], struct.unpack_from("<i", raw, 0x78)[0])
            for prop in properties:
                known[int(prop["address"], 16)] = prop
            # Large AoC classes exceed the general dumper's 1024-method bound.
            # Validate every UField identity and cycle before recording flags.
            head = struct.unpack_from("<Q", raw, 0x68)[0]
            seen, functions = set(), []
            while head:
                if not pointer(head) or head in seen or len(seen) >= 8192:
                    raise ReadError("Invalid/cyclic/excessive class function chain")
                seen.add(head)
                obj = reflection.obj(head)
                if reflection.class_name(obj["class_address"]) == "Function":
                    flags = reader.unpack(head+0xD0, "<I")[0]
                    known[head] = {"name": obj["name"], "type": "UFunction", "flags": hex(flags)}
                    if flags & 0x40:
                        functions.append({"name": obj["name"], "address": hex(head), "flags": hex(flags),
                                          "super_function": hex(reader.unpack(head+0x60, "<Q")[0])})
                head = reader.unpack(head+0x48, "<Q")[0]
            arrays = []
            for offset in range(0xD0, 0x230, 8):
                data, count, capacity = struct.unpack_from("<Qii", raw, offset)
                if not pointer(data) or not 0 < count <= 2048 or not count <= capacity <= 4096:
                    continue
                for stride in (8, 16):
                    try:
                        entries = reader.read(data, count*stride)
                    except ReadError:
                        continue
                    fields = []
                    for i in range(count):
                        field = struct.unpack_from("<Q", entries, i*stride)[0]
                        normalized = field & ~1
                        if normalized not in known:
                            break
                        metadata = known[normalized]
                        fields.append({"array_index": i, "raw_pointer": hex(field),
                                       "name": metadata["name"],
                                       "kind": metadata.get("type", "UFunction"),
                                       "entry_hex": entries[i*stride:(i+1)*stride].hex()})
                    if len(fields) == count:
                        arrays.append({"offset": hex(offset), "data": hex(data),
                                       "count": count, "capacity": capacity,
                                       "stride": stride, "fields": fields})
            result["classes"].append({"name": cls["name"], "address": cls["address"],
                                      "object_index": live["index"],
                                      "properties": properties,
                                      "net_functions": functions,
                                      "validated_reflection_arrays": arrays,
                                      "uclass_raw_hex": raw.hex()})
        result["bytes_read"] = reader.bytes_read
        return result
    finally:
        reader.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.snapshot)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "pid": result["pid"],
                      "arrays": {c["name"]: [(a["offset"], a["count"], a["stride"]) for a in c["validated_reflection_arrays"]] for c in result["classes"]}}))
