"""Read-only exact reflected Role enum and property NetSerializeItem pointers."""
import argparse
import json
from pathlib import Path

from dump_runtime_reflection import Reader, Reflection, ReadError, pointer
from protocol_proof import client_proof


def inspect(snapshot):
    metadata = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    reader = Reader(metadata["pid"], Path(metadata["exe"]))
    result = {"pid": metadata["pid"], "source": str(snapshot), "access": "PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION", "properties": []}
    try:
        reflection = Reflection(reader)
        actor = next(cls for cls in metadata["classes"] if cls["name"] == "Actor")
        address = int(actor["address"], 16)
        if reflection.obj(address)["name"] != "Actor":
            raise ReadError("Actor snapshot identity disagrees with current process")
        props = reflection.properties(reader.unpack(address+0x70, "<Q")[0], actor["size"])
        for name, offset in (("Role", 0x1f8), ("RemoteRole", 0x180)):
            prop = next(item for item in props if item["name"] == name)
            if prop["type"] != "ByteProperty" or prop["element_size"] != 1 or prop["array_dim"] != 1 or prop["offset_in_object"] != offset:
                raise ReadError("Role metadata must match exact reflected ByteProperty layout")
            field = int(prop["address"], 16)
            table = reader.unpack(field, "<Q")[0]
            serializer = reader.unpack(table+0xc8, "<Q")[0]
            if not reader.base <= serializer < reader.base+reader.image_size:
                raise ReadError("Role serializer must belong to exact current executable")
            enum_address = reader.unpack(field+0x70, "<Q")[0]
            enum = reflection.obj(enum_address)
            if enum["name"] != "ENetRole" or reflection.class_name(enum["class_address"]) != "Enum":
                raise ReadError("Role enum must be the actual ENetRole UObject")
            data, count, capacity = reader.unpack(enum_address+0x60, "<Qii")
            if not pointer(data) or not 0 < count <= capacity <= 64:
                raise ReadError("Invalid bounded enum Names array")
            values = []
            for i in range(count):
                index, number, value = reader.unpack(data+i*16, "<IIq")
                values.append({"name": reflection.names.get(index, number), "value": value})
            result["properties"].append({**prop, "enum_address": hex(enum_address), "enum_names": values,
                "net_serialize_rva": hex(serializer-reader.base), "net_serialize_virtual_offset": "0xc8"})
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
    print(json.dumps({"pid": result["pid"], "properties": result["properties"]}))
