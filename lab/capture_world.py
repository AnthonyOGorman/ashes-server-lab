"""Read-only, reproducible gameplay-capture bootstrap evidence extraction.

Run: python -m lab.capture_world --capture PATH --output JSON
"""
import argparse
import collections
import json
from pathlib import Path
import re
import subprocess

from .unreal import decode_packet, DecodeError
from .world_bootstrap import decode_exports, decode_actor_prefix


def strings_at_bit_offsets(data):
    n = int.from_bytes(data, "little")
    result = []
    for shift in range(8):
        shifted = (n >> shift).to_bytes(len(data), "little")
        for match in re.finditer(rb"[\x20-\x7e]{8,}", shifted):
            text = match.group().decode("ascii")
            if "/Game/" in text or "/Script/" in text or "Default__" in text:
                result.append({"bit_offset": match.start()*8+shift, "text": text, "evidence": "printable_string_scan_not_object_schema"})
    return result


def analyze(capture, tshark=r"C:\Program Files\Wireshark\tshark.exe", first=3634, last=4000):
    command = [tshark, "-r", str(capture), "-Y", f"frame.number>={first} && frame.number<={last} && udp.port==7436", "-T", "fields", "-e", "frame.number", "-e", "ip.src", "-e", "udp.payload"]
    process = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if process.returncode:
        raise RuntimeError(process.stderr.strip())
    stats = collections.Counter()
    evidence = []
    first_actor_data = set()
    for line in process.stdout.splitlines():
        frame, source, raw = line.split("\t")
        direction = "server" if source == "18.117.53.108" else "client"
        parsed = decode_packet(bytes.fromhex(raw), direction)
        stats[parsed["kind"]] += 1
        actor_open = any(b.get("open") and b["channel"] != 0 for b in parsed.get("bunches", []))
        selected = parsed["kind"].startswith(("control.", "stateless.")) or actor_open
        for bunch in parsed.get("bunches", []):
            payload = bytes.fromhex(bunch["payload_hex"])
            if bunch["exports"]:
                try:
                    bunch["export_decode"] = decode_exports(payload, bunch["payload_bits"])
                except DecodeError as exc:
                    bunch["export_decode_error"] = str(exc)
                    bunch["string_evidence"] = strings_at_bit_offsets(payload)
            elif bunch["channel"] not in first_actor_data and bunch["channel"] != 0:
                first_actor_data.add(bunch["channel"])
                if bunch["payload_bits"] >= 384:
                    bunch["actor_prefix"] = decode_actor_prefix(payload, bunch["payload_bits"])
                selected = selected or int(frame) <= 3735
        if selected:
            evidence.append({"frame": int(frame), "direction": direction, "udp_hex": raw, "decoded": parsed})
    return {"source_capture": str(Path(capture).resolve()), "filter": command[4], "stats": dict(stats), "evidence": evidence, "limits": ["Transport and exports are capture-verified; printable scans are explicitly separate.", "Actor transforms, RPC handles, replication property handles, and current client acceptance remain unresolved.", "These captured bytes are research fixtures, not packets served to clients."]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = analyze(args.capture)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output": args.output, "stats": report["stats"], "evidence_records": len(report["evidence"])}))


if __name__ == "__main__":
    main()
