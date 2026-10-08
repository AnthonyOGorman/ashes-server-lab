"""Read-only current native RPC/property virtual serializer addresses."""
import argparse
import json
from pathlib import Path

from dump_runtime_reflection import Reader, Reflection, ReadError


def inspect(snapshot):
    metadata = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    reader = Reader(metadata["pid"], Path(metadata["exe"]))
    result = {"pid": metadata["pid"], "source_snapshot": str(snapshot),
              "access": "PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION", "functions": [], "package_map_serializers": []}
    try:
        reflection = Reflection(reader)
        for cls in metadata["classes"]:
            for function in cls.get("net_functions", []):
                if function["name"] not in ("ClientRestart", "ClientRetryClientRestart", "ServerAcknowledgePossession"):
                    continue
                address = int(function["address"], 16)
                if reflection.obj(address)["name"] != function["name"]:
                    raise ReadError("Function snapshot no longer agrees with process")
                entry = {"owner_class": cls["name"], "name": function["name"],
                         "address": hex(address), "exec_rva": hex(reader.unpack(address + 0xF8, "<Q")[0] - reader.base),
                         "parameters": []}
                props = reflection.properties(reader.unpack(address + 0x70, "<Q")[0])
                for prop in props:
                    property_address = int(prop["address"], 16)
                    vtable = reader.unpack(property_address, "<Q")[0]
                    serializer = reader.unpack(vtable + 0xC8, "<Q")[0]
                    if not reader.base <= serializer < reader.base + reader.image_size:
                        raise ReadError("Property virtual serializer lies outside current executable")
                    entry["parameters"].append({**prop, "net_serialize_virtual_offset": "0xc8",
                                                 "net_serialize_rva": hex(serializer - reader.base)})
                result["functions"].append(entry)
        for address, obj in reflection.objects():
            if obj["name"] not in ("Default__PackageMapClient", "Default__IntrepidNetServerPackageMap"):
                continue
            vtable = reader.unpack(address, "<Q")[0]
            serializer = reader.unpack(vtable + 0x340, "<Q")[0]
            if not reader.base <= serializer < reader.base + reader.image_size:
                raise ReadError("Package map serializer lies outside current executable")
            result["package_map_serializers"].append({"name": obj["name"],
                "class": reflection.class_name(obj["class_address"]), "address": hex(address),
                "serialize_object_virtual_offset": "0x340", "serialize_object_rva": hex(serializer - reader.base),
                "get_object_from_guid_virtual_offset": "0x3b8",
                "get_object_from_guid_rva": hex(reader.unpack(vtable + 0x3B8, "<Q")[0] - reader.base),
                "evidence": "validated live CDO vtable; no function invoked"})
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
    print(json.dumps(result))
