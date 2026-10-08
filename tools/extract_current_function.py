"""Extract one exact client function using PE .pdata boundaries, read-only."""
import argparse
import json
import mmap
from pathlib import Path
import struct


def extract(exe, rva, output, length=None):
    with Path(exe).open("rb") as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[:2] != b"MZ" or data[pe:pe+4] != b"PE\0\0":
            raise ValueError("Invalid PE headers")
        count, optional_size = struct.unpack_from("<H12xH", data, pe+6)
        optional = pe+24
        if struct.unpack_from("<H", data, optional)[0] != 0x20B:
            raise ValueError("Requires PE32+ executable")
        sections = []
        for i in range(count):
            at = optional+optional_size+i*40
            virtual_size, virtual, raw_size, raw = struct.unpack_from("<IIII", data, at+8)
            sections.append((virtual, max(virtual_size, raw_size), raw, raw_size))
        def offset(address, size=1):
            for virtual, extent, raw, raw_size in sections:
                if virtual <= address and address+size <= virtual+extent:
                    relative = address-virtual
                    if relative+size > raw_size:
                        raise ValueError("Requested bytes exceed section raw data")
                    return raw+relative
            raise ValueError("RVA outside sections")
        if length is not None:
            if not 1 <= length <= 65536:
                raise ValueError("Fragment length must be bounded to 65536 bytes")
            fragment_offset = offset(rva, length)
            Path(output).write_bytes(data[fragment_offset:fragment_offset+length])
            return {"requested_rva": hex(rva), "bytes": length, "output": str(output),
                    "boundary_evidence": "explicit bounded fragment; no function boundary claimed"}
        exception_rva, exception_size = struct.unpack_from("<II", data, optional+112+3*8)
        start = offset(exception_rva, exception_size)
        for begin, end, unwind in struct.iter_unpack("<III", data[start:start+exception_size]):
            if begin <= rva < end:
                function_offset = offset(begin, end-begin)
                Path(output).write_bytes(data[function_offset:function_offset+end-begin])
                return {"requested_rva": hex(rva), "begin": hex(begin), "end": hex(end),
                        "unwind": hex(unwind), "output": str(output)}
        raise ValueError("No function boundary covers RVA")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rva", type=lambda value: int(value, 0))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bytes", type=int, help="Explicit bounded fragment for leaf functions without .pdata")
    args = parser.parse_args()
    inventory = json.loads((Path(__file__).resolve().parents[1]/"evidence/client_inventory.json").read_text(encoding="utf-8"))
    print(json.dumps(extract(inventory["exe"], args.rva, args.output, args.bytes)))
