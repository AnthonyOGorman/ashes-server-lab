"""Summarize session schemas from historical data without exporting credentials."""
import argparse
from collections import Counter
import json
import mmap
import re
from pathlib import Path
import struct
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lab.contracts import Contracts
from tools.import_capture import find_tshark
from tools.inspect_lobby_capture import fields


def shape(value):
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return {"type": "array", "items": [shape(item) for item in value[:2]]}
    return type(value).__name__


def summarize(wrapper, contracts):
    result = {"type": wrapper.message_type_name, "system_keys": sorted(wrapper.system_data.tags)}
    if wrapper.message_type_name != "ics_common.SessionReply":
        return result
    reply = contracts.parse(wrapper.message_type_name, wrapper.message_data)
    result.update(result_code=reply.result_code, request_type=reply.request_type,
                  tag_keys=sorted(reply.tags), data_keys=sorted(reply.data_map),
                  data_string_length=len(reply.data_string))
    result["config_schemas"] = {}
    for section, mapping in (("system_data.tags", wrapper.system_data.tags), ("tags", reply.tags), ("data_map", reply.data_map)):
        for key, value in mapping.items():
            if "config" in key.lower():
                try:
                    schema = shape(json.loads(value))
                except ValueError:
                    schema = {"type": "non_json_string", "length": len(value)}
                result["config_schemas"][section + "." + key] = schema
    try:
        result["data_string_schema"] = shape(json.loads(reply.data_string))
    except ValueError:
        result["data_string_schema"] = "not_json"
    return result


def wrappers_from_json(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    yield from fields(data, "grpc.message_data")


def wrappers_from_pcap(path, keylog=None):
    command = [find_tshark(), "-n", "-r", str(path), "-Y", "grpc.message_data", "-T", "fields",
               "-E", "occurrence=a", "-E", "aggregator=|", "-e", "grpc.message_data"]
    if keylog:
        command.extend(["-o", "tls.keylog_file:" + str(keylog)])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        for line in process.stdout:
            for value in line.strip().split("|"):
                if value:
                    yield value
        code = process.wait()
        if code:
            raise RuntimeError(f"tshark returned {code}; capture or decryption configuration may be unsupported")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()


def analyze(path, contracts, keylog=None):
    counts, replies, failures = Counter(), [], 0
    iterator = wrappers_from_json(path) if path.suffix == ".json" else wrappers_from_pcap(path, keylog)
    for value in iterator:
        try:
            wrapper = contracts.parse("ics_common.MessageWrapper", bytes.fromhex(value.replace(":", "")))
            counts[wrapper.message_type_name] += 1
            if wrapper.message_type_name == "ics_common.SessionReply":
                replies.append(summarize(wrapper, contracts))
        except Exception:
            failures += 1
    return {"source": str(path), "types": dict(counts), "session_replies": replies, "decode_failures": failures,
            "keylog_supplied": bool(keylog)}


def binary_keys(path):
    import pefile
    pe = pefile.PE(str(path), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    result = []
    with path.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        for key in ("ConfigJsonPing", "ConfigJsonXClient", "ConfigJsonTether", "config_env_fragment", "player_session_state"):
            for encoding in ("ascii", "utf-16le"):
                needle = key.encode(encoding)
                start = 0
                while True:
                    offset = data.find(needle, start)
                    if offset < 0:
                        break
                    start = offset + len(needle)
                    width = 2 if encoding == "utf-16le" else 1
                    string_start = offset
                    while string_start >= width and data[string_start-width:string_start] != b"\0"*width:
                        string_start -= width
                    rva = pe.get_rva_from_offset(string_start)
                    item = {"key": key, "encoding": encoding, "offset": offset,
                            "string_start": string_start, "rva": rva,
                            "virtual_address": hex(base + rva), "code_xrefs": []}
                    result.append(item)
        result.append({"key": "ConfigJsonPing static FString", "rva": 0xD93EA00,
                       "virtual_address": hex(base + 0xD93EA00), "code_xrefs": []})
        targets = {item["rva"]: item for item in result}
        for section in pe.sections:
            if not section.Characteristics & 0x20000000:
                continue
            blob = data[section.PointerToRawData:section.PointerToRawData + section.SizeOfRawData]
            for match in re.finditer(rb"[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", blob):
                index = match.start()
                if index + 7 > len(blob):
                    continue
                target = section.VirtualAddress + index + 7 + struct.unpack_from("<i", blob, index + 3)[0]
                if target in targets:
                    targets[target]["code_xrefs"].append({"rva": section.VirtualAddress + index, "offset": section.PointerToRawData + index})
    return result


def installed_client_findings(path):
    """Check the string and instruction evidence for this installed build."""
    import pefile
    pe = pefile.PE(str(path), fast_load=True)
    with path.open("rb") as source:
        def read(rva, size):
            source.seek(pe.get_offset_from_rva(rva))
            return source.read(size)
        literal = read(0xB86ADA8, 128).decode("utf-16le").split("\0")[0]
        # Constructor loads the filename literal into the global FString, then
        # the SessionReply sink loads that same FString before its map lookup.
        static_init = read(0x11F5F74, 19)
        map_lookup = read(0x64E8157, 111)
        filename_verified = literal == "ics_ping_client_config.json"
        init_verified = static_init == bytes.fromhex("488d152d4e670a488d0d7e8a740ce8498e1400")
        sink_verified = map_lookup[:16] == bytes.fromhex("498d8db8000000488b01ff90a0000000")
        return {"ping_config": {"verified": filename_verified and init_verified and sink_verified,
                    "field": "ics_common.SessionReply.data_map", "key": literal,
                    "literal_rva": "0xb86ada8", "static_init_rva": "0x11f5f74",
                    "fstring_rva": "0xd93ea00", "consumer_rva": "0x64e8157",
                    "missing_config_branch_rva": "0x64e85e0",
                    "schema_keys_from_binary": ["ping_period_msec", "ping_hosts"]},
                "player_session_state": {"field": "ics_common.SessionReply.data_map",
                    "key": "player_session_state", "lookup_tag_id": 25,
                    "consumer_rva": "0x64e890b", "parse_from_string_rva": "0x64e8970",
                    "encoding": "Serialized ics_xclient.PlayerSessionState protobuf in string value; not a separate unsolicited wrapper"},
                "player_config_filename": "ics_player_client_config.json"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="*", type=Path)
    parser.add_argument("--keylog", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contracts = Contracts(Path(__file__).resolve().parent.parent / "evidence/client_contracts.pb")
    result = {"captures": [analyze(path, contracts, args.keylog) for path in args.sources]}
    if args.binary:
        result["binary_keys"] = binary_keys(args.binary)
        result["installed_client_findings"] = installed_client_findings(args.binary)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
