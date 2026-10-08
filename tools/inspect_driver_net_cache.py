"""Discover current-build network cache by validated read-only pointer chains.

Requires a same-PID inspect_class_net_arrays snapshot. No addresses are invoked,
no process memory is written, and class declaration order is never a wire index.
Every reported FieldNetIndex comes from a candidate cache record matching an
independently validated reflected function pointer and monotonic index series.
"""
import argparse
import json
from pathlib import Path
import struct

from dump_runtime_reflection import Reader, Reflection, ReadError, pointer
from protocol_proof import client_proof


def inspect(snapshot):
    metadata = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    inventory = json.loads((Path(__file__).resolve().parents[1]/"evidence/client_inventory.json").read_text(encoding="utf-8"))
    reader = Reader(metadata["pid"], Path(inventory["exe"]))
    known_fields, known_classes = {}, {}
    for cls in metadata["classes"]:
        if "object_index" in cls:
            known_classes[cls["object_index"]] = cls
        for function in cls.get("net_functions", []):
            known_fields[int(function["address"], 16)] = {**function, "kind": "UFunction", "owner_class": cls["name"]}
        for prop in cls.get("properties", []):
            known_fields[int(prop["address"], 16)] = {**prop, "kind": "FProperty", "owner_class": cls["name"]}
    result = {"pid": metadata["pid"], "source": str(snapshot),
              "access": "PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION",
              "status": "no_verified_cache", "drivers": [], "candidate_caches": []}
    found, scanned_managers = set(), set()
    try:
        reflection = Reflection(reader)
        for cls in known_classes.values():
            live = reflection.obj(int(cls["address"], 16))
            if live["index"] != cls["object_index"] or live["name"] != cls["name"]:
                raise ReadError("Class snapshot identity mismatch")
        for address, obj in reflection.objects():
            if obj["name"].startswith("Default__"):
                continue
            class_name = reflection.class_name(obj["class_address"])
            if "NetDriver" not in class_name:
                continue
            # Explicit ancestry check excludes similarly named unrelated objects.
            current, ancestors = obj["class_address"], []
            for _ in range(16):
                if not current:
                    break
                ancestors.append(reflection.obj(current)["name"])
                current = reader.unpack(current+0x60, "<Q")[0]
            if "NetDriver" not in ancestors:
                continue
            driver = reader.read(address, 0x8D8)
            connection = struct.unpack_from("<Q", driver, 0x138)[0]
            result["drivers"].append({"name": obj["name"], "class": class_name, "address": hex(address), "server_connection": hex(connection)})
            if not pointer(connection):
                continue
            # Current ReceivedBunch RVA0x3f2f820 +0xdd..e8 passes
            # NetDriver[+0x210] to GetClassNetCache. The padding sweep is a
            # bounded diagnostic fallback; it must include this early member.
            for driver_offset in (0x210, *range(0x200, 0x858, 8)):
                manager, shared_controller = struct.unpack_from("<QQ", driver, driver_offset)
                if not pointer(manager) or not pointer(shared_controller) or manager in scanned_managers:
                    continue
                scanned_managers.add(manager)
                try:
                    manager_raw = reader.read(manager, 0x90)
                except ReadError:
                    continue
                for map_offset in range(0, 0x50, 8):
                    entries, count, capacity = struct.unpack_from("<Qii", manager_raw, map_offset)
                    if not pointer(entries) or not 0 < count <= capacity <= 256:
                        continue
                    try:
                        sparse = reader.read(entries, count*24)
                    except ReadError:
                        continue
                    for i in range(count):
                        class_index, serial, cache = struct.unpack_from("<iiQ", sparse, i*24)
                        cls = known_classes.get(class_index)
                        if cls is None or serial <= 0 or not pointer(cache) or cache in found:
                            continue
                        try:
                            cache_raw = reader.read(cache, 0xD0)
                        except ReadError:
                            continue
                        # Cache fields are FFieldVariant(8), index(4), CRC(4),
                        # incompatibility(1), padding; 24-byte aligned records.
                        # Current executable ReadFieldHeaderAndPayload RVA
                        # 0x3f2dc60 verifies Fields at +0x20, Num at +0x28,
                        # FieldsBase at +0 and Super at +8, records 24 bytes.
                        for fields_offset in (0x20,):
                            fields_pointer, field_count, field_capacity = struct.unpack_from("<Qii", cache_raw, fields_offset)
                            if not pointer(fields_pointer) or not 0 < field_count <= field_capacity <= 4096:
                                continue
                            try:
                                fields_raw = reader.read(fields_pointer, field_count*24)
                            except ReadError:
                                continue
                            fields, previous = [], None
                            for j in range(field_count):
                                raw_field, net_index, checksum = struct.unpack_from("<QiI", fields_raw, j*24)
                                field = known_fields.get(raw_field & ~1)
                                incompatible = fields_raw[j*24+16]
                                if field is None or bool(raw_field & 1) != (field["kind"] == "UFunction") or incompatible not in (0, 1) or not 0 <= net_index <= 8192 or (previous is not None and net_index != previous+1):
                                    break
                                fields.append({"name": field["name"], "kind": field["kind"], "field_address": field["address"], "owner_class": field["owner_class"], "field_net_index": net_index,
                                               "checksum": checksum, "incompatible": bool(incompatible), "record_hex": fields_raw[j*24:(j+1)*24].hex()})
                                previous = net_index
                            if len(fields) != field_count:
                                continue
                            header_base = struct.unpack_from("<i", cache_raw, 0)[0]
                            header_class_index, header_class_serial = struct.unpack_from("<ii", cache_raw, 0x10)
                            if header_base != fields[0]["field_net_index"]:
                                continue
                            found.add(cache)
                            result["candidate_caches"].append({"class": cls["name"], "class_index": class_index, "class_serial": serial,
                                "driver": hex(address), "driver_manager_offset": hex(driver_offset), "manager": hex(manager),
                                "manager_map_offset": hex(map_offset), "cache": hex(cache), "cache_header_hex": cache_raw.hex(),
                                "fields_array_offset": hex(fields_offset), "field_count": field_count, "fields": fields,
                                "fields_base_candidate": header_base, "fields_base_matches": header_base == fields[0]["field_net_index"],
                                "header_weak_class_candidate": [header_class_index, header_class_serial],
                                "header_weak_class_matches": (header_class_index, header_class_serial) == (class_index, serial),
                                "max_observed_field_index": fields[-1]["field_net_index"],
                                "normal_rpc_field_maximum": header_base + field_count + 1,
                                "field_maximum_evidence": "current_client_ReadFieldHeaderAndPayload_RVA_0x3f2dc60_plus_0x396_SerializeInt_Base_plus_Num_plus_1",
                                "super_cache": hex(struct.unpack_from("<Q", cache_raw, 8)[0]),
                                "evidence": "candidate_runtime_cache_pointer_identity_and_contiguous_indices_verified"})
        if result["candidate_caches"]:
            result["status"] = "runtime_cache_candidates_verified"
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
    result["client_proof"] = client_proof(result["pid"])
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "drivers": result["drivers"], "classes": [c["class"] for c in result["candidate_caches"]], "bytes_read": result["bytes_read"]}))
