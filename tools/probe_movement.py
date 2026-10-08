"""Read-only possession and position evidence; never a walking success gate.

capture_snapshot(pid) validates the installed executable, process lifetime and
the existing reflected player/GUID inspector. compare_snapshots(before, after)
accepts only the same possessed pawn and unattached root. A position delta can
also be a fall, teleport or correction: server-authoritative walking is always
reported as unverified. No game input, memory writes or remote calls occur.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import time

try:
    from .inspect_player_state import inspect, ReadError
except ImportError:  # Direct command-line execution.
    from inspect_player_state import inspect, ReadError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ashes-read-only-position-v1"
GUID_EVIDENCE = "current_binary_map_layout_and_live_GObjects_pointer_index_serial_agreement"


class EvidenceError(ValueError):
    """A sample cannot substantiate the requested position comparison."""


def _require(condition, message):
    if not condition:
        raise EvidenceError(message)


def _integer(value, minimum=1):
    return type(value) is int and value >= minimum


def _identity(obj):
    _require(isinstance(obj, dict), "Missing object identity")
    address = obj.get("address")
    _require(isinstance(address, str), "Missing object address")
    try:
        numeric = int(address, 16)
    except ValueError as error:
        raise EvidenceError("Invalid object address") from error
    _require(0x10000 <= numeric < 0x800000000000 and numeric % 8 == 0,
             "Invalid object address")
    _require(_integer(obj.get("object_index"), 0), "Invalid object index")
    _require(all(isinstance(obj.get(key), str) and obj[key]
                 for key in ("class", "name", "outer_address")), "Incomplete object identity")
    return {key: obj[key] for key in ("address", "object_index", "class", "name", "outer_address")}


def _mapped(obj, matches):
    identity = _identity(obj)
    rows = [row for row in matches if _identity(row.get("actor")) == identity]
    _require(len(rows) == 1, "Object must have exactly one validated network GUID match")
    row = rows[0]
    _require(row.get("evidence") == GUID_EVIDENCE, "Network GUID match lacks pointer/index/serial proof")
    _require(row.get("weak_object_index") == identity["object_index"] and
             _integer(row.get("weak_object_serial")), "Invalid weak object identity")
    guid = row.get("guid")
    _require(isinstance(guid, dict), "Missing network GUID")
    try:
        object_id = int(guid["object_id"], 16)
        wire = object_id.to_bytes(8, "little") + guid["server_id"].to_bytes(4, "little") + guid["randomizer"].to_bytes(4, "little")
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        raise EvidenceError("Invalid network GUID") from error
    _require(object_id > 1 and _integer(guid.get("server_id"), 0) and
             _integer(guid.get("randomizer"), 0) and wire.hex() == row.get("guid_hex"),
             "Network GUID components disagree with raw map key")
    return {**identity, "weak_object_serial": row["weak_object_serial"],
            "guid": dict(guid), "guid_hex": wire.hex()}


def sample_from_inspection(report, process_created_filetime, started_ns, completed_ns):
    """Normalize a trusted inspect_player_state report, refusing partial proof.

    This pure function enables tests using independently constructed reports.
    Production callers should use capture_snapshot to collect process lifetime.
    """
    _require(isinstance(report, dict) and not report.get("errors"), "Inspector reported errors")
    _require(_integer(report.get("pid")) and _integer(process_created_filetime), "Invalid process lifetime identity")
    _require(_integer(started_ns) and _integer(completed_ns) and completed_ns >= started_ns,
             "Invalid capture interval")
    validation = report.get("reflection_validation", {})
    _require(validation.get("name_pool_sentinel") == "None" and
             _integer(validation.get("validated_object_indices")), "Missing reflection validation")
    locals_ = [entry for entry in report.get("local_players", []) if entry.get("player_controller")]
    _require(len(locals_) == 1, "Expected one local player with a controller")
    local = locals_[0]
    controller_ref = _identity(local["player_controller"])
    controllers = [entry for entry in report.get("controllers", []) if _identity(entry) == controller_ref]
    _require(len(controllers) == 1, "Local player controller is absent or ambiguous")
    controller = controllers[0]
    _require(controller.get("acknowledges_same_pawn") is True and
             controller.get("pawn_points_back_to_controller") is True,
             "Controller has not acknowledged a pawn with a matching back pointer")
    pawn, acknowledged = controller.get("pawn"), controller.get("acknowledged_pawn")
    _require(_identity(pawn) == _identity(acknowledged), "Pawn and acknowledged pawn identities disagree")
    _require(_identity(pawn.get("controller")) == controller_ref, "Pawn back pointer differs from local controller")
    matches = report.get("network_guid_actor_matches", [])
    controller_bound = _mapped(controller, matches)
    pawn_bound = _mapped(pawn, matches)
    _require(_mapped(acknowledged, matches) == pawn_bound and
             _mapped(pawn["controller"], matches) == controller_bound,
             "Possession references disagree with validated network GUID identities")
    root = pawn.get("root_component")
    root_identity = _identity(root)
    _require("attach_parent" in root and root["attach_parent"] is None,
             "Attached or uninspected roots cannot prove world position")
    location = root.get("unattached_location")
    _require(isinstance(location, (list, tuple)) and len(location) == 3 and
             all(type(value) in (int, float) and math.isfinite(value) for value in location),
             "Missing finite unattached position")
    _require(root.get("relative_location") == location, "Position evidence disagrees with reflected relative location")
    return {"schema": SCHEMA, "status": "sampled", "pid": report["pid"],
            "exe": report["exe"], "process_created_filetime": process_created_filetime,
            "started_ns": started_ns, "completed_ns": completed_ns,
            "local_player": _identity(local), "controller": controller_bound,
            "pawn": pawn_bound, "root_component": root_identity,
            "position": list(location), "possession_proven": True,
            "coordinate_evidence": "Reflected RelativeLocation on a root with no AttachParent",
            "server_authoritative_walking_verified": False,
            "inspection": report}


def _process_created_filetime(pid):
    if os.name != "nt":
        raise EvidenceError("Process lifetime collection requires Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise EvidenceError(f"Cannot read process lifetime: WinError {ctypes.get_last_error()}")
    try:
        created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in (created, exited, system, user))):
            raise EvidenceError("Cannot read process creation time")
        _require(exited.dwHighDateTime == 0 and exited.dwLowDateTime == 0, "Process has exited")
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


def capture_snapshot(pid):
    """Capture and return sampled or blocked evidence for the exact local client."""
    started = time.time_ns()
    try:
        inventory = json.loads((ROOT / "evidence/client_inventory.json").read_text(encoding="utf-8"))
        exe = Path(inventory["exe"])
        digest = hashlib.sha256()
        with exe.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        _require(digest.hexdigest() == inventory["sha256"], "Executable hash differs from extracted inventory")
        lifetime = _process_created_filetime(pid)
        report = inspect(pid, exe)
        _require(lifetime == _process_created_filetime(pid), "Process lifetime changed during inspection")
        return sample_from_inspection(report, lifetime, started, time.time_ns())
    except (EvidenceError, ReadError, OSError, KeyError, ValueError) as error:
        return {"schema": SCHEMA, "status": "blocked", "pid": pid,
                "started_ns": started, "completed_ns": time.time_ns(), "error": str(error),
                "possession_proven": False, "server_authoritative_walking_verified": False}


def compare_snapshots(before, after, *, tolerance_cm=0.01, max_gap_seconds=120):
    """Compare bound samples; changed position does not substantiate walking."""
    result = {"schema": SCHEMA, "status": "blocked", "position_changed": None,
              "server_authoritative_walking_verified": False, "before": before, "after": after}
    try:
        _require(type(tolerance_cm) in (int, float) and math.isfinite(tolerance_cm) and tolerance_cm >= 0,
                 "Invalid position tolerance")
        _require(type(max_gap_seconds) in (int, float) and math.isfinite(max_gap_seconds) and 0 < max_gap_seconds <= 3600,
                 "Invalid comparison interval bound")
        for sample in (before, after):
            _require(isinstance(sample, dict) and sample.get("schema") == SCHEMA and
                     sample.get("status") == "sampled", "Both snapshots must contain complete evidence")
            canonical = sample_from_inspection(sample["inspection"], sample["process_created_filetime"],
                                               sample["started_ns"], sample["completed_ns"])
            _require(sample == canonical, "Snapshot differs from its source inspector proof")
        for key in ("pid", "exe", "process_created_filetime", "local_player", "controller", "pawn", "root_component"):
            _require(before[key] == after[key], f"Identity changed between samples: {key}")
        gap = (after["started_ns"] - before["completed_ns"]) / 1e9
        _require(0 <= gap <= max_gap_seconds, "Samples overlap, are reversed or exceed the comparison interval")
        delta = [later - earlier for earlier, later in zip(before["position"], after["position"])]
        distance = math.hypot(*delta)
        _require(all(math.isfinite(value) for value in delta) and math.isfinite(distance), "Nonfinite position delta")
        result.update(status="compared", possession_proven=True,
                      position_changed=distance > tolerance_cm, delta_cm=delta,
                      distance_cm=distance, horizontal_distance_cm=math.hypot(*delta[:2]),
                      vertical_delta_cm=delta[2], between_capture_seconds=gap,
                      tolerance_cm=tolerance_cm,
                      interpretation="Position changed; cause unverified" if distance > tolerance_cm else "No position change above tolerance",
                      walking_claim="None; falling, teleporting and corrections can also change position")
    except (EvidenceError, KeyError, TypeError, ValueError) as error:
        result["error"] = str(error)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--pid", type=int, required=True)
    snapshot.add_argument("--output", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        result = capture_snapshot(args.pid)
    else:
        result = compare_snapshots(json.loads(args.before.read_text(encoding="utf-8")),
                                   json.loads(args.after.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in ("inspection", "before", "after")}))
    return 0 if result["status"] in ("sampled", "compared") else 2


if __name__ == "__main__":
    raise SystemExit(main())
