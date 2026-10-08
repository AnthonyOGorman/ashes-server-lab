"""Read-only local PlayerController lifecycle vtable target from current proof."""
import argparse
import json
from pathlib import Path
from dump_runtime_reflection import Reader, ReadError
from inspect_player_state import PlayerProbe
from protocol_proof import client_proof


def inspect(snapshot):
    actors = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    reader = Reader(actors["pid"], Path(actors["exe"]))
    try:
        probe = PlayerProbe(reader)
        if len(actors["local_players"]) != 1:
            raise ReadError("One exact local player required")
        local = int(actors["local_players"][0]["address"], 16)
        controller = probe.object_field(local, "PlayerController", 0x50, "PlayerController")
        if controller is None or controller["class"] != "AoCPlayerControllerBP_C":
            raise ReadError("Expected gameplay local controller required")
        address = int(controller["address"], 16)
        table = reader.unpack(address, "<Q")[0]
        function = reader.unpack(table+0xb30, "<Q")[0]
        if not reader.base <= function < reader.base+reader.image_size:
            raise ReadError("ClientRestart implementation target must be in current executable")
        state = probe.controller(address)
        pawn_targets = {}
        if state["pawn"]:
            pawn_table = reader.unpack(int(state["pawn"]["address"], 16), "<Q")[0]
            for offset in (0x868, 0x8b8):
                target = reader.unpack(pawn_table+offset, "<Q")[0]
                if not reader.base <= target < reader.base+reader.image_size:
                    raise ReadError("Pawn lifecycle target must belong to exact current executable")
                pawn_targets[hex(offset)] = hex(target-reader.base)
        return {"pid": actors["pid"], "source": str(snapshot), "controller": state,
            "access": "PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION",
            "client_restart_virtual_offset": "0xb30", "implementation_rva": hex(function-reader.base),
            "pawn_virtual_targets_from_client_restart": pawn_targets,
            "evidence": "current_exec_thunk_RVA4442fd0_calls_this_virtual_and_live_local_controller_target_verified",
            "bytes_read": reader.bytes_read}
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
    print(json.dumps(result))
