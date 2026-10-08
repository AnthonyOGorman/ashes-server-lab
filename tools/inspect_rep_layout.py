"""Read-only initialized class RepLayout arrays; no guessed wire handles."""
import argparse
import json
from pathlib import Path
import struct

from dump_runtime_reflection import Reader, Reflection, ReadError, pointer
from protocol_proof import client_proof


def inspect(snapshot, driver_snapshot):
    classes = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    drivers = json.loads(Path(driver_snapshot).read_text(encoding="utf-8"))
    if classes["pid"] != drivers["pid"]:
        raise ReadError("Snapshots must belong to one live PID")
    inventory = json.loads((Path(__file__).resolve().parents[1]/"evidence/client_inventory.json").read_text(encoding="utf-8"))
    reader = Reader(classes["pid"], Path(inventory["exe"]))
    known_classes = {c["object_index"]: c for c in classes["classes"]}
    properties = {int(p["address"], 16): {**p, "owner_class": c["name"]} for c in classes["classes"] for p in c["properties"]}
    report = {"pid": classes["pid"], "source_classes": str(snapshot), "source_drivers": str(driver_snapshot),
              "access": "PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION", "layouts": [], "errors": [],
              "wire_handles": "None: raw command words retained until serializer interpretation is verified"}
    try:
        reflection = Reflection(reader)
        for driver in drivers["drivers"]:
            address = int(driver["address"], 16)
            if reflection.class_name(reflection.obj(address)["class_address"]) != driver["class"]:
                raise ReadError("Driver snapshot identity mismatch")
            # Current GetFunctionRepLayout RVA0x4236550 validates this map:
            # Driver+0x5c0; weak UStruct key8, shared Layout pointer16;
            # 32-byte sparse map records. No cache function is invoked.
            data, count, capacity = reader.unpack(address+0x5C0, "<Qii")
            if not 0 <= count <= capacity <= 8192 or (count and not pointer(data)):
                raise ReadError("Invalid bounded driver RepLayout map")
            raw = reader.read(data, count*32) if count else b""
            for i in range(count):
                index, serial, layout, controller = struct.unpack_from("<iiQQ", raw, i*32)
                cls = known_classes.get(index)
                if cls is None or serial <= 0 or not pointer(layout) or not pointer(controller):
                    continue
                try:
                    live = reflection.obj(int(cls["address"], 16))
                    if live["index"] != index or live["name"] != cls["name"]:
                        raise ReadError("Layout weak-class identity disagrees")
                    header = reader.read(layout, 0x50)
                    parents, parent_count, parent_capacity = struct.unpack_from("<Qii", header, 0x28)
                    commands, command_count, command_capacity = struct.unpack_from("<Qii", header, 0x38)
                    if not pointer(parents) or not pointer(commands) or not 0 < parent_count <= parent_capacity <= 4096 or not 0 < command_count <= command_capacity <= 32768:
                        raise ReadError("Invalid bounded layout arrays")
                    parent_raw = reader.read(parents, parent_count*48)
                    command_raw = reader.read(commands, command_count*32)
                    entry = {"class": cls["name"], "class_index": index, "class_serial": serial,
                             "driver": hex(address), "layout": hex(layout), "header_hex": header.hex(),
                             "parent_count": parent_count, "command_count": command_count, "parents": [], "commands": []}
                    for j in range(parent_count):
                        property_address = struct.unpack_from("<Q", parent_raw, j*48)[0]
                        prop = properties.get(property_address)
                        if prop is None:
                            raise ReadError("Layout parent does not match validated reflected property")
                        entry["parents"].append({"parent_index": j, "property": prop,
                                                 "record_hex": parent_raw[j*48:(j+1)*48].hex()})
                    for j in range(command_count):
                        record = command_raw[j*32:(j+1)*32]
                        property_address = struct.unpack_from("<Q", record)[0]
                        prop = properties.get(property_address)
                        entry["commands"].append({"command_index": j, "property_address": hex(property_address),
                            "property": prop, "record_hex": record.hex(),
                            "offset_in_object": struct.unpack_from("<i", record, 0xC)[0],
                            "parent_index": struct.unpack_from("<H", record, 0x16)[0],
                            "command_type_byte": record[0x1C],
                            "uninterpreted_word_08": struct.unpack_from("<H", record, 8)[0],
                            "uninterpreted_word_0a": struct.unpack_from("<H", record, 10)[0],
                            "uninterpreted_word_14": struct.unpack_from("<H", record, 0x14)[0],
                            "wire_handle": None})
                    report["layouts"].append(entry)
                except ReadError as exc:
                    report["errors"].append({"class": cls["name"], "layout": hex(layout), "error": str(exc)})
        report["bytes_read"] = reader.bytes_read
        return report
    finally:
        reader.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("classes", type=Path)
    parser.add_argument("drivers", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.classes, args.drivers)
    result["client_proof"] = client_proof(result["pid"])
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"pid": result["pid"], "classes": [c["class"] for c in result["layouts"]], "errors": result["errors"]}))
