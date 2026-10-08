"""Read reflected movement/input prerequisites without writes or game calls."""
import argparse
import json
import math
from pathlib import Path
import re

try:
    from .inspect_player_state import PlayerProbe
    from .dump_runtime_reflection import Reader, ReadError, pointer
    from .protocol_proof import client_proof, EXPECTED_EXE
except ImportError:
    from inspect_player_state import PlayerProbe
    from dump_runtime_reflection import Reader, ReadError, pointer
    from protocol_proof import client_proof, EXPECTED_EXE


class MovementProbe(PlayerProbe):
    def properties_for(self, address):
        obj = self.reflection.obj(address)
        result = {}
        for cls, owner in self.chain(obj["class_address"]):
            if cls not in self.members:
                head = self.reader.unpack(cls+0x70, "<Q")[0]
                size = self.reader.unpack(cls+0x78, "<i")[0]
                self.members[cls] = self.reflection.properties(head, size)
            for prop in self.members[cls]:
                result.setdefault(prop["name"], {**prop, "owner_class": owner})
        return result

    def decode(self, base, prop):
        result = {"status": "read", "metadata": prop}
        kind, size = prop["type"], prop["element_size"]
        if prop["array_dim"] != 1:
            return {**result, "status": "unsupported_array_dimension"}
        address = base+prop["offset_in_object"]
        if kind in ("ObjectProperty", "ObjectPropertyBase", "ClassProperty") and size == 8:
            result["value"] = self.identity(self.reader.unpack(address, "<Q")[0], prop.get("referenced_type"))
        elif kind == "BoolProperty" and size == 1:
            layout = prop.get("bool_layout", {})
            byte_offset = layout.get("byte_offset", -1)
            mask = layout.get("field_mask", 0)
            if layout.get("field_size") != 1 or byte_offset != 0 or not 1 <= mask <= 255:
                raise ReadError("BoolProperty mask/field layout is not a validated single byte")
            raw = self.reader.unpack(address+byte_offset, "<B")[0]
            result.update(value=bool(raw & mask), raw_byte=raw)
        elif kind in ("ByteProperty", "EnumProperty") and size == 1:
            value = self.reader.unpack(address, "<B")[0]
            result["value"] = value
            if kind == "ByteProperty":
                enum_address = self.reader.unpack(int(prop["address"], 16)+0x70, "<Q")[0]
                if enum_address:
                    enum = self.reflection.obj(enum_address)
                    if self.reflection.class_name(enum["class_address"]) != "Enum":
                        raise ReadError("ByteProperty enum target is not an Enum")
                    data, count, capacity = self.reader.unpack(enum_address+0x60, "<Qii")
                    if not pointer(data) or not 0 < count <= capacity <= 256:
                        raise ReadError("Invalid bounded reflected enum Names array")
                    values = []
                    for index in range(count):
                        name, number, enum_value = self.reader.unpack(data+index*16, "<IIq")
                        values.append({"name": self.reflection.names.get(name, number), "value": enum_value})
                    result["enum"] = {"name": enum["name"], "values": values}
                    result["value_name"] = next((entry["name"] for entry in values if entry["value"] == value), None)
        elif kind == "NameProperty" and size == 8:
            index, number = self.reader.unpack(address, "<II")
            result["value"] = self.reflection.names.get(index, number)
        elif kind in ("IntProperty", "UInt32Property", "FloatProperty") and size == 4:
            result["value"] = self.reader.unpack(address, {"IntProperty": "<i", "UInt32Property": "<I", "FloatProperty": "<f"}[kind])[0]
        elif kind == "DoubleProperty" and size == 8:
            result["value"] = self.reader.unpack(address, "<d")[0]
        elif kind == "StructProperty" and size == 24 and prop.get("referenced_type") == "Vector":
            result["value"] = list(self.reader.unpack(address, "<ddd"))
            if not all(math.isfinite(value) for value in result["value"]):
                raise ReadError("Nonfinite reflected vector")
        elif kind == "ArrayProperty" and size == 16:
            data, count, capacity = self.reader.unpack(address, "<Qii")
            if not 0 <= count <= capacity <= 65536 or (count and not pointer(data)):
                raise ReadError("Invalid bounded reflected array")
            result.update(value={"count": count, "capacity": capacity}, elements_read=False)
        else:
            result["status"] = "unsupported_reflected_type"
        return result

    def fields(self, address, names, include_flags=False):
        props = self.properties_for(address)
        if include_flags:
            names = list(dict.fromkeys([*names, *(name for name, prop in props.items()
                         if prop["type"] == "BoolProperty" and
                         re.search(r"init|ready|move|input|control|dead|active|enable|tick|predict", name, re.I))]))[:96]
        result = {}
        for name in names:
            prop = props.get(name)
            if prop is None:
                result[name] = {"status": "not_reflected"}
                continue
            try:
                result[name] = self.decode(address, prop)
            except (ReadError, UnicodeError) as error:
                result[name] = {"status": "read_error", "metadata": prop, "error": str(error)}
        return result

    def tick(self, address, name):
        prop = self.properties_for(address).get(name)
        if prop is None:
            return {"status": "not_reflected"}
        if prop["type"] != "StructProperty" or prop["array_dim"] != 1:
            raise ReadError("Tick property is not a scalar reflected struct")
        struct_address = self.reader.unpack(int(prop["address"], 16)+0x70, "<Q")[0]
        struct_obj = self.reflection.obj(struct_address)
        if struct_obj["name"] not in ("ActorTickFunction", "ActorComponentTickFunction"):
            raise ReadError("Unexpected tick struct identity")
        base = address+prop["offset_in_object"]
        fields, seen = {}, set()
        current = struct_address
        while current:
            if current in seen or len(seen) >= 8:
                raise ReadError("Invalid bounded tick struct inheritance")
            seen.add(current)
            head = self.reader.unpack(current+0x70, "<Q")[0]
            size = self.reader.unpack(current+0x78, "<i")[0]
            for field in self.reflection.properties(head, size):
                if field["type"] in ("BoolProperty", "FloatProperty", "ByteProperty"):
                    fields.setdefault(field["name"], self.decode(base, field))
            current = self.reader.unpack(current+0x60, "<Q")[0]
        return {"status": "read", "metadata": prop, "struct": struct_obj["name"], "fields": fields,
                "runtime_tick_registration": "Unresolved; reflected defaults are not runtime scheduler state"}


def inspect(pid, controller_address, pawn_address):
    proof = client_proof(pid)
    reader = Reader(pid, EXPECTED_EXE)
    result = {"pid": pid, "client_proof": proof,
              "access": "PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION", "errors": []}
    try:
        probe = MovementProbe(reader)
        controller = probe.controller(controller_address)
        if not controller["acknowledges_same_pawn"] or not controller["pawn_points_back_to_controller"] or int(controller["pawn"]["address"], 16) != pawn_address:
            raise ReadError("Requested pawn must be acknowledged and point back to requested controller")
        result["possession"] = controller
        result["controller"] = probe.fields(controller_address,
            ["IgnoreMoveInput", "IgnoreLookInput", "StateName", "InputComponent", "PlayerInput",
             "InactiveStateInputComponent", "PlayerState", "bBlockInput", "AutoReceiveInput", "InputPriority"], True)
        result["pawn"] = probe.fields(pawn_address,
            ["CharacterMovement", "InputComponent", "Owner", "PlayerState", "Mesh", "CapsuleComponent",
             "AutoPossessPlayer", "AutoReceiveInput", "bBlockInput", "InputPriority", "Controller",
             "ReplicatedMovementMode", "ControlInputVector", "LastControlInputVector",
             "bPressedJump", "JumpMaxHoldTime", "JumpForceTimeRemaining", "JumpCurrentCount"], True)
        result["pawn_tick"] = probe.tick(pawn_address, "PrimaryActorTick")
        movement = result["pawn"]["CharacterMovement"].get("value")
        if movement:
            address = int(movement["address"], 16)
            result["movement_component"] = {"identity": movement,
                "fields": probe.fields(address, ["MovementMode", "CustomMovementMode", "DefaultLandMovementMode",
                    "GroundMovementMode", "Velocity", "Acceleration", "UpdatedComponent", "UpdatedPrimitive",
                    "PawnOwner", "CharacterOwner", "bIsActive", "bAutoActivate", "bHasBegunPlay", "bRegistered",
                    "bTickEnabled", "bUpdateOnlyIfRendered",
                    "bRunPhysicsWithNoController", "MaxWalkSpeed", "MaxAcceleration", "bUseMovementSpeedStat",
                    "bPredictMovement", "bDeferServerMoves", "GravityScale", "GravityDirection",
                    "JumpZVelocity", "bApplyGravityWhileJumping", "bSimGravityDisabled"], True),
                "tick": probe.tick(address, "PrimaryComponentTick")}
        for group in ("controller", "pawn"):
            entry = result[group].get("InputComponent", {}).get("value")
            if entry:
                address = int(entry["address"], 16)
                result[f"{group}_input_component"] = {"identity": entry,
                    "fields": probe.fields(address, ["bBlockInput", "Priority", "bIsActive", "bAutoActivate"], True)}
        player_input = result["controller"]["PlayerInput"].get("value")
        if player_input:
            result["player_input"] = {"identity": player_input,
                "fields": probe.fields(int(player_input["address"], 16),
                    ["ActionMappings", "AxisMappings", "bEnableMouseSmoothing", "bEnableFOVScaling"], True)}
        level = probe.identity(int(controller["pawn"]["outer_address"], 16), "Level")
        level_fields = probe.fields(int(level["address"], 16), ["OwningWorld"])
        result["level"] = {"identity": level, "fields": level_fields}
        world = level_fields["OwningWorld"].get("value")
        if world:
            world_fields = probe.fields(int(world["address"], 16),
                ["GameState", "AuthorityGameMode", "bBegunPlay", "bActorsInitialized", "bMatchStarted",
                 "bPlayersOnly", "bIsWorldInitialized"], True)
            result["world"] = {"identity": world, "fields": world_fields}
            game_state = world_fields["GameState"].get("value")
            if game_state:
                result["game_state"] = {"identity": game_state,
                    "fields": probe.fields(int(game_state["address"], 16),
                        ["bReplicatedHasBegunPlay", "GameModeClass", "AuthorityGameMode", "PlayerArray",
                         "ReplicatedWorldTimeSeconds", "ReplicatedWorldTimeSecondsDouble"], True)}
        after = client_proof(pid)
        if any(proof[key] != after[key] for key in ("pid", "sha256", "process_created_filetime", "exe")):
            raise ReadError("Client identity changed while probing prerequisites")
        result["completed_client_proof"] = after
        result["bytes_read"] = reader.bytes_read
        result["reflection_validation"] = probe.reflection.validation
        return result
    finally:
        reader.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--controller", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--pawn", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.pid, args.controller, args.pawn)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"pid": result["pid"], "output": str(args.output), "bytes_read": result["bytes_read"],
                      "controller": {name: row.get("value", row["status"]) for name, row in result["controller"].items()},
                      "pawn": {name: row.get("value", row["status"]) for name, row in result["pawn"].items()},
                      "movement": {name: row.get("value", row["status"]) for name, row in result.get("movement_component", {}).get("fields", {}).items()},
                      "game_state": {name: row.get("value", row["status"]) for name, row in result.get("game_state", {}).get("fields", {}).items()}}))
