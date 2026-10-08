"""Import scoped offline game payloads; never change Wireshark preferences.

Only game signatures and explicitly selected loopback lab ports are exported.
This is an observation importer, not a claim that packet meanings are known.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
from pathlib import Path


DEFAULT_PORTS = (15051, 17089)
FIELDS = ("frame.number", "frame.time_epoch", "ip.src", "ipv6.src", "ip.dst", "ipv6.dst",
          "udp.srcport", "udp.dstport", "tcp.srcport", "tcp.dstport", "udp.payload", "tcp.payload")


def find_tshark(explicit=None):
    candidates = [str(explicit)] if explicit else [shutil.which("tshark"),
        str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Wireshark/tshark.exe")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise FileNotFoundError("tshark was not found. Install Wireshark or provide --tshark PATH.")


def is_loopback(address):
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def normalize_fields(line, local_ports=DEFAULT_PORTS):
    fields = line.rstrip("\r\n").split("\t")
    if len(fields) != len(FIELDS):
        return None
    frame, ts, ip_src, ipv6_src, ip_dst, ipv6_dst, us, ud, cs, cd, up, cp = fields
    src, dst = ip_src or ipv6_src, ip_dst or ipv6_dst
    channel, source_port, destination_port, payload = ("udp", us, ud, up) if up else ("tcp", cs, cd, cp)
    if not payload:
        return None
    try:
        raw = bytes.fromhex(payload.replace(":", ""))
        source_port, destination_port = int(source_port), int(destination_port)
        frame, ts = int(frame), float(ts)
    except (ValueError, TypeError):
        return None
    game_marker = None
    if channel == "udp":
        if raw.startswith(b"\x96\x76\x0c\x50"):
            game_marker = "game_96760c50"
        elif len(raw) >= 4 and raw.startswith(b"\xa5\x5a\x02"):
            game_marker = "tether_a55a"
    ports = set(local_ports)
    local = is_loopback(src) and is_loopback(dst) and (source_port in ports or destination_port in ports)
    if not game_marker and not local:
        return None
    # No encrypted TLS records are useful for this semantic packet catalog.
    if not game_marker and len(raw) > 2 and raw[0] in range(20, 24) and raw[1] == 3:
        return None
    direction = "unknown"
    if local and (source_port in ports) != (destination_port in ports):
        direction = "server_to_client" if source_port in ports else "client_to_server"
    return {"ts": ts, "channel": channel, "direction": direction,
            "kind": game_marker or "local_lab_payload", "size": len(raw), "hex": raw.hex(),
            "decoded": {"interpretation": "unknown", "signature": game_marker},
            "frame": frame, "source": {"address": src, "port": source_port},
            "destination": {"address": dst, "port": destination_port}}


def iter_capture(path, tshark=None, local_ports=DEFAULT_PORTS):
    """Yield normalized payload rows from a PCAP/PCAPNG via an isolated tshark process."""
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    ports = tuple(int(p) for p in local_ports)
    if any(not 1 <= p <= 65535 for p in ports):
        raise ValueError("Local ports must be between 1 and 65535.")
    signatures = "(udp.payload[0:4] == 96:76:0c:50) || (udp.payload[0:3] == a5:5a:02)"
    lab_filter = " || ".join(f"udp.port == {p} || tcp.port == {p}" for p in ports)
    display_filter = signatures
    if lab_filter:
        display_filter += f" || (((ip.src == 127.0.0.1 && ip.dst == 127.0.0.1) || (ipv6.src == ::1 && ipv6.dst == ::1)) && ({lab_filter}))"
    command = [find_tshark(tshark), "-n", "-r", str(path), "-Y", display_filter,
               "-T", "fields", "-E", "separator=/t", "-E", "occurrence=f"]
    for field in FIELDS:
        command.extend(["-e", field])
    # A temporary stderr file avoids deadlocks on malformed or very large captures.
    # -r is offline; no key log fields or live capture interfaces are requested.
    import tempfile
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, encoding="utf-8", errors="replace",
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            for line in process.stdout:
                row = normalize_fields(line, ports)
                if row:
                    yield row
            returncode = process.wait()
            if returncode:
                errors.seek(0)
                message = errors.read(8192).decode("utf-8", errors="replace")
                raise RuntimeError(f"tshark exited with {returncode}: {message}")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tshark", type=Path)
    parser.add_argument("--local-port", action="append", type=int, dest="ports",
                        help="Include loopback payloads on this lab port (repeatable).")
    args = parser.parse_args()
    if args.capture.resolve() == args.output.resolve():
        parser.error("Output must differ from the source capture.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with args.output.open("w", encoding="utf-8") as destination:
        for row in iter_capture(args.capture, args.tshark, args.ports if args.ports is not None else DEFAULT_PORTS):
            destination.write(json.dumps(row) + "\n")
            count += 1
    print(json.dumps({"capture": str(args.capture), "output": str(args.output), "packets": count}))


if __name__ == "__main__":
    main()
