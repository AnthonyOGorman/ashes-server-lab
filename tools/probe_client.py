"""Extract protobuf contracts directly from the installed PE; never execute it."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from google.protobuf import descriptor_pb2


def varint(data, pos):
    value = 0
    for shift in range(0, 35, 7):
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
    raise ValueError("invalid varint")


def probe(exe, destination):
    data = exe.read_bytes()
    found = {}
    for match in re.finditer(rb"ics-protos/[^\x00\r\n]{1,180}?\.proto", data):
        start_name = match.start()
        for prefix in range(2, 5):
            start = start_name - prefix
            if data[start] != 10:
                continue
            try:
                length, pos = varint(data, start + 1)
                if pos != start_name or length != len(match.group()):
                    continue
                end = data.find(b"\x62\x06proto3", pos + length, start + 150000)
                if end < 0:
                    continue
                blob = data[start:end + 8]
                file = descriptor_pb2.FileDescriptorProto.FromString(blob)
                if file.name.encode() == match.group() and file.syntax == "proto3":
                    found[file.name] = (file, start, blob)
            except Exception:
                continue
    destination.mkdir(parents=True, exist_ok=True)
    descriptors = descriptor_pb2.FileDescriptorSet()
    summary = []
    for name, (file, offset, blob) in sorted(found.items()):
        descriptors.file.add().CopyFrom(file)
        summary.append({"name": name, "package": file.package, "offset": offset,
                        "sha256": hashlib.sha256(blob).hexdigest(),
                        "messages": [m.name for m in file.message_type],
                        "services": [s.name for s in file.service]})
    (destination / "client_contracts.pb").write_bytes(descriptors.SerializeToString())
    report = {"exe": str(exe), "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
              "contracts": summary,
              "engine_strings": list(dict.fromkeys(x.decode(errors="replace") for x in
                  re.findall(rb"\+\+UE5[^\x00]{0,80}|\+\+AOC[^\x00]{0,80}", data)))[:20]}
    (destination / "client_inventory.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    probe(args.exe, args.destination)
