"""Read-only local-controller, pawn and component proof for the current client.

Uses reflected field names and validates SDK offsets before reading them. No
game function is invoked, no memory is written and no UI action is performed.
Object identity is not a network GUID; this tool explicitly keeps them distinct.
"""
import argparse
import json
import math
from pathlib import Path
import struct

try:
    from .dump_runtime_reflection import Reader, Reflection, ReadError, pointer
    from .protocol_proof import client_proof
except ImportError:  # Direct command-line execution.
    from dump_runtime_reflection import Reader, Reflection, ReadError, pointer
    from protocol_proof import client_proof


class PlayerProbe:
    def __init__(self, reader):
        self.reader = reader
        self.reflection = Reflection(reader)
        self.chains = {}
        self.members = {}

    def chain(self, class_address):
        if class_address not in self.chains:
            result, seen = [], set()
            current = class_address
            while current:
                if current in seen or len(seen) >= 32:
                    raise ReadError("Invalid class ancestry")
                seen.add(current)
                result.append((current, self.reflection.obj(current)["name"]))
                current = self.reader.unpack(current + 0x60, "<Q")[0]
            self.chains[class_address] = result
        return self.chains[class_address]

    def identity(self, address, expected=None):
        if not address:
            return None
        obj = self.reflection.obj(address)
        ancestors = [name for _, name in self.chain(obj["class_address"])]
        if expected and expected not in ancestors:
            raise ReadError(f"Object is not a {expected}")
        return {"address": hex(address), "object_index": obj["index"],
                "name": obj["name"], "class": ancestors[0], "ancestors": ancestors,
                "outer_address": hex(obj["outer_address"])}

    def property(self, address, name, offset, size):
        obj = self.reflection.obj(address)
        for cls, _ in self.chain(obj["class_address"]):
            if cls not in self.members:
                head = self.reader.unpack(cls + 0x70, "<Q")[0]
                owner_size = self.reader.unpack(cls + 0x78, "<i")[0]
                self.members[cls] = self.reflection.properties(head, owner_size)
            for prop in self.members[cls]:
                if prop["name"] == name:
                    if prop["offset_in_object"] != offset or prop["element_size"] != size:
                        raise ReadError(f"Reflected {name} disagrees with expected SDK layout")
                    return prop
        raise ReadError(f"Reflected property {name} absent")

    def object_field(self, address, name, offset, expected):
        prop = self.property(address, name, offset, 8)
        if prop["type"] not in ("ObjectProperty", "ObjectPropertyBase"):
            raise ReadError(f"{name} is not an object property")
        target = self.reader.unpack(address + offset, "<Q")[0]
        return self.identity(target, expected)

    def actor_roles(self, address):
        result = {}
        for name, offset in (("Role", 0x1f8), ("RemoteRole", 0x180)):
            prop = self.property(address, name, offset, 1)
            if prop["type"] != "ByteProperty" or prop["array_dim"] != 1:
                raise ReadError(f"{name} must be a reflected scalar ByteProperty")
            result[name] = self.reader.unpack(address+offset, "<B")[0]
        result["evidence"] = "reflected Actor names/type/size/exactoffset; no role inferred from possession"
        return result

    def pawn(self, address):
        result = self.identity(address, "Pawn")
        result["network_roles"] = self.actor_roles(address)
        result["controller"] = self.object_field(address, "Controller", 0x398, "Controller")
        result["player_state"] = self.object_field(address, "PlayerState", 0x388, "PlayerState")
        root = self.object_field(address, "RootComponent", 0x248, "SceneComponent")
        result["root_component"] = root
        if root:
            component = int(root["address"], 16)
            root["attach_parent"] = self.object_field(component, "AttachParent", 0x118, "SceneComponent")
            self.property(component, "RelativeLocation", 0x190, 24)
            location = self.reader.unpack(component + 0x190, "<ddd")
            if not all(math.isfinite(value) for value in location):
                raise ReadError("Nonfinite reflected component location")
            root["relative_location"] = list(location)
            root["coordinate_evidence"] = "reflected RelativeLocation; ComponentToWorld not read"
            if root["attach_parent"] is None:
                root["unattached_location"] = list(location)
        return result

    def controller(self, address):
        result = self.identity(address, "PlayerController")
        result["network_roles"] = self.actor_roles(address)
        result["pawn"] = self.object_field(address, "Pawn", 0x3A8, "Pawn")
        result["acknowledged_pawn"] = self.object_field(address, "AcknowledgedPawn", 0x428, "Pawn")
        result["player_state"] = self.object_field(address, "PlayerState", 0x370, "PlayerState")
        result["hud"] = self.object_field(address, "MyHUD", 0x450, "HUD")
        result["hud_is_aoc_base"] = bool(result["hud"] and "AoCHUDBase" in result["hud"]["ancestors"])
        if result["pawn"]:
            result["pawn"] = self.pawn(int(result["pawn"]["address"], 16))
        ack = result["acknowledged_pawn"]
        result["acknowledges_same_pawn"] = bool(result["pawn"] and ack and result["pawn"]["address"] == ack["address"])
        result["pawn_points_back_to_controller"] = bool(result["pawn"] and result["pawn"]["controller"] and result["pawn"]["controller"]["address"] == hex(address))
        return result


def inspect(pid, exe):
    reader = Reader(pid, exe)
    report = {"pid": pid, "exe": str(exe),
              "access": "PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION",
              "local_players": [], "game_instances": [], "controllers": [],
              "pawns": [], "player_states": [], "game_states": [], "errors": [],
              "network_guid_actor_matches": [], "net_drivers": [],
              "network_guid_mapping": "Unresolved; UObject indices and names are not network GUIDs",
              "walking_claim": "None; this snapshot only proves pointers and reflected positions"}
    try:
        probe = PlayerProbe(reader)
        drivers = []
        for address, obj in probe.reflection.objects():
            if obj["name"].startswith("Default__") or int(obj["flags"], 16) & 0x10:
                continue
            names = [name for _, name in probe.chain(obj["class_address"])]
            try:
                if "NetDriver" in names:
                    drivers.append(address)
                elif "LocalPlayer" in names:
                    entry = probe.identity(address, "LocalPlayer")
                    entry["player_controller"] = probe.object_field(address, "PlayerController", 0x50, "PlayerController")
                    report["local_players"].append(entry)
                elif "GameInstance" in names:
                    entry = probe.identity(address, "GameInstance")
                    probe.property(address, "LocalPlayers", 0x58, 16)
                    data, count, capacity = reader.unpack(address + 0x58, "<Qii")
                    if not 0 <= count <= capacity <= 16 or (count and not pointer(data)):
                        raise ReadError("Invalid bounded LocalPlayers array")
                    entry["local_players"] = [probe.identity(reader.unpack(data + i*8, "<Q")[0], "LocalPlayer") for i in range(count)]
                    report["game_instances"].append(entry)
                elif "PlayerController" in names:
                    report["controllers"].append(probe.controller(address))
                elif "Pawn" in names:
                    report["pawns"].append(probe.pawn(address))
                elif "PlayerState" in names:
                    report["player_states"].append(probe.identity(address, "PlayerState"))
                elif "GameStateBase" in names:
                    report["game_states"].append(probe.identity(address, "GameStateBase"))
            except (ReadError, UnicodeError) as exc:
                report["errors"].append({"address": hex(address), "name": obj["name"], "error": str(exc)})
        actor_identities = {obj["object_index"]: obj for key in ("controllers", "pawns", "player_states", "game_states") for obj in report[key]}
        chunk_table = reader.read(probe.reflection.chunks, probe.reflection.num_chunks*8)
        for address in drivers:
            try:
                driver = probe.identity(address, "NetDriver")
                connection = probe.object_field(address, "ServerConnection", 0x138, "NetConnection")
                driver["server_connection"] = connection
                report["net_drivers"].append(driver)
                if connection is None:
                    continue
                package = probe.object_field(int(connection["address"], 16), "PackageMap", 0x88, "PackageMap")
                driver["package_map"] = package
                if package is None or package["class"] != "PackageMapClient":
                    continue
                # Current binary PackageMapClient.GetObjectFromNetGUID leaf
                # RVA0x426f920 reads GuidCache at +0x338. Internal lookup at
                # RVA0x426f930 +0x62..95 uses map+0x10, 80-byte entries, GUID
                # key16 followed by FNetGUIDCacheObject's weak UObject pair.
                guid_cache = reader.unpack(int(package["address"], 16)+0x338, "<Q")[0]
                if not pointer(guid_cache):
                    raise ReadError("Invalid network GUID cache pointer")
                data, count, capacity = reader.unpack(guid_cache+0x10, "<Qii")
                if not 0 <= count <= capacity <= 100000 or (count and not pointer(data)):
                    raise ReadError("Invalid bounded network GUID object map")
                entries = reader.read(data, count*80) if count else b""
                driver["guid_cache"] = hex(guid_cache)
                driver["guid_cache_slot_count"] = count
                for i in range(count):
                    object_id, server_id, randomizer, index, serial = struct.unpack_from("<QIIii", entries, i*80)
                    actor = actor_identities.get(index)
                    if actor is None or serial <= 0 or object_id <= 1:
                        continue
                    chunk = struct.unpack_from("<Q", chunk_table, (index//65536)*8)[0]
                    item = reader.read(chunk+(index%65536)*24, 24)
                    actual_address = struct.unpack_from("<Q", item)[0]
                    internal_flags = struct.unpack_from("<I", item, 8)[0]
                    actual_serial = struct.unpack_from("<i", item, 16)[0]
                    if actual_address != int(actor["address"], 16) or actual_serial != serial or internal_flags & 0x10200000:
                        continue
                    report["network_guid_actor_matches"].append({"actor": actor,
                        "guid": {"object_id": f"0x{object_id:016x}", "server_id": server_id, "randomizer": randomizer},
                        "guid_hex": entries[i*80:i*80+16].hex(), "weak_object_index": index,
                        "weak_object_serial": serial, "guid_cache": hex(guid_cache),
                        "evidence": "current_binary_map_layout_and_live_GObjects_pointer_index_serial_agreement"})
            except (ReadError, UnicodeError) as exc:
                report["errors"].append({"address": hex(address), "error": str(exc)})
        if report["network_guid_actor_matches"]:
            report["network_guid_mapping"] = "Exact GUID map keys matched to live actor pointers through independently validated weak UObject index and serial"
        report["reflection_validation"] = probe.reflection.validation
        report["bytes_read"] = reader.bytes_read
        return report
    finally:
        reader.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads((Path(__file__).resolve().parents[1] / "evidence/client_inventory.json").read_text(encoding="utf-8"))
    result = inspect(args.pid, Path(inventory["exe"]))
    result["client_proof"] = client_proof(args.pid)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"pid": args.pid, "output": str(args.output),
                      "counts": {key: len(result[key]) for key in ("local_players", "controllers", "pawns", "player_states", "game_states", "errors")},
                      "network_guid_actor_matches": len(result["network_guid_actor_matches"]),
                      "controllers": result["controllers"]}))
