"""Bounded read-only reflected appearance snapshot for a validated Verra pawn."""
import argparse
import json
from pathlib import Path
import re

from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader, ReadError
from protocol_proof import client_proof, EXPECTED_EXE


class AppearanceProbe(MovementProbe):
    def decode(self, base, prop, depth=0):
        result = super().decode(base, prop)
        if result['status']=='unsupported_reflected_type' and prop['type']=='StrProperty':
            data,count,capacity=self.reader.unpack(base+prop['offset_in_object'],'<Qii')
            if not 0<=count<=capacity<=16384 or (count and not data):
                raise ReadError('Bounded reflected FString required')
            value=self.reader.read(data,count*2).decode('utf-16le') if count else ''
            if value and not value.endswith('\0'):
                raise ReadError('Reflected FString terminator missing')
            result.update(status='read',value=value[:-1] if value else '')
        if result["status"] == "unsupported_reflected_type" and prop["type"] == "StructProperty" and depth < 2:
            target = self.reader.unpack(int(prop["address"], 16)+0x70, "<Q")[0]
            obj = self.reflection.obj(target)
            size = self.reader.unpack(target+0x78, "<i")[0]
            if size != prop["element_size"] or size > 4096:
                raise ReadError("Reflected struct size differs or exceeds bound")
            head = self.reader.unpack(target+0x70, "<Q")[0]
            members = self.reflection.properties(head, size)
            if len(members) > 64:
                raise ReadError("Struct member bound exceeded")
            fields = {}
            for member in members:
                try:
                    fields[member["name"]] = self.decode(base+prop["offset_in_object"], member, depth+1)
                except (ReadError, UnicodeError) as error:
                    fields[member["name"]] = {"status": "read_error", "error": str(error), "metadata": member}
            result.update(status="read_struct", struct=obj["name"], fields=fields)
        return result

    def appearance_fields(self, address, extra=()):
        props = self.properties_for(address)
        names = list(dict.fromkeys([*extra, *(name for name in props if re.search(
            r"mesh|appearance|custom|cosmetic|race|gender|skin|body|head|hair|equipment|playerstate|owner|hidden|visible|anim|attach|active|beginplay|scale", name, re.I))]))[:128]
        return self.fields(address, names)


def inspect(pid, controller, pawn, require_possession=True):
    proof = client_proof(pid)
    reader = Reader(pid, EXPECTED_EXE, budget=64*1024*1024)
    try:
        probe = AppearanceProbe(reader)
        possession = probe.controller(controller)
        if require_possession and (not possession["acknowledges_same_pawn"] or not possession["pawn_points_back_to_controller"] or int(possession["pawn"]["address"], 16) != pawn):
            raise ReadError("Requested pawn is not acknowledged by requested controller")
        pawn_identity = probe.identity(pawn, "Pawn")
        def actor_world(identity):
            level = probe.identity(int(identity["outer_address"], 16), "Level")
            world = probe.fields(int(level["address"], 16), ("OwningWorld",))["OwningWorld"].get("value")
            if not world or world["name"] != "Verra_World_Master":
                raise ReadError("Actor is not in the expected live Verra World")
            return world
        world = actor_world(pawn_identity)
        if actor_world(possession)["address"] != world["address"]:
            raise ReadError("Pawn and controller do not share the same Verra World")
        result = {"pid": pid, "client_proof": proof, "access": "PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION",
                  "safety": "No memory writes, game calls, injection or input", "possession": possession,
                  "scope": "acknowledged_local_pawn" if require_possession else "spawned_actor_same_verra_world_no_possession_claim",
                  "world": world,
                  "pawn": {"identity": pawn_identity, "fields": probe.appearance_fields(pawn, ("Mesh", "CharacterMovement", "bHidden", "PlayerState", "Owner", "CharacterInformationComponent"))},
                  "components": {}, "assets": {}, "errors": []}
        pending = []
        for name, row in result["pawn"]["fields"].items():
            value = row.get("value")
            if isinstance(value, dict) and "address" in value and any("Component" in ancestor for ancestor in value["ancestors"]):
                pending.append((name, int(value["address"], 16)))
        seen = set()
        while pending and len(seen) < 24:
            name, address = pending.pop(0)
            if address in seen:
                continue
            seen.add(address)
            fields = probe.appearance_fields(address, ("SkeletalMesh", "bVisible", "bHiddenInGame", "bOwnerNoSee", "bOnlyOwnerSee", "bIsActive", "bAutoActivate", "Skeleton", "LeaderPoseComponent", "CharacterCreatorSubsystem"))
            result["components"][name] = {"identity": probe.identity(address), "fields": fields}
            for child_name, row in fields.items():
                value = row.get("value")
                if isinstance(value, dict) and "address" in value and "Component" in value["class"] and re.search(r"mesh|appearance", child_name, re.I):
                    pending.append((name+"."+child_name, int(value["address"], 16)))
            asset = fields.get("SkeletalMesh", {}).get("value")
            if asset and asset["address"] not in result["assets"]:
                result["assets"][asset["address"]] = {"identity": asset, "fields": probe.fields(int(asset["address"], 16),
                    ("Skeleton", "Materials", "LODInfo", "ImportedBounds"))}
        info = result['pawn']['fields'].get('CharacterInformationComponent', {}).get('value')
        if info:
            result['character_information'] = {'identity': info, 'fields': probe.fields(int(info['address'],16),
                ['CharacterGuid','CharacterName','CharacterType','Race','Gender','ServerId','Level',
                 'ComponentOwnerPrivate','bReplicates','bIsPhasedOut','bClientIsReadyToPhaseIn',
                 'bHasBeenPossessed','PhasedOutStartTime','TeleportState'])}
        cls = probe.reflection.obj(pawn)["class_address"]
        default = reader.unpack(cls+0x150, "<Q")[0]
        if default:
            result["pawn_class_default"] = {"identity": probe.identity(default), "fields": probe.appearance_fields(default, ("Mesh",))}
            mesh = result["pawn_class_default"]["fields"]["Mesh"].get("value")
            if mesh:
                result["class_default_mesh"] = {"identity": mesh, "fields": probe.appearance_fields(int(mesh["address"], 16))}
        after = client_proof(pid)
        if any(proof[key] != after[key] for key in ("pid", "sha256", "process_created_filetime", "exe")):
            raise ReadError("Client identity changed during snapshot")
        result.update(completed_client_proof=after, bytes_read=reader.bytes_read, reflection_validation=probe.reflection.validation)
        return result
    finally:
        reader.close()


def catalog(pid):
    proof = client_proof(pid)
    reader = Reader(pid, EXPECTED_EXE, budget=96*1024*1024)
    try:
        probe = AppearanceProbe(reader)
        result = {"pid": pid, "client_proof": proof,
                  "access": "PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION",
                  "scope": "Class defaults and loaded appearance instances; no stale world actor dereferences",
                  "classes": {}, "instances": [], "assets": {}, "errors": []}
        class_names = {"IntrepidCharacter", "PlayerCharacter", "PlayerPawn_C", "CharacterAppearanceComponent", "BaseModularAppearanceComponent", "AoCPlayerState"}
        for address, obj in probe.reflection.objects():
            if obj["name"] in class_names and probe.reflection.class_name(obj["class_address"]) in ("Class", "BlueprintGeneratedClass"):
                entry = {"identity": probe.identity(address)}
                default = reader.unpack(address+0x150, "<Q")[0]
                if default:
                    entry["default"] = {"identity": probe.identity(default), "fields": probe.appearance_fields(default, ("Mesh", "bHidden"))}
                    mesh = entry["default"]["fields"].get("Mesh", {}).get("value")
                    if mesh:
                        entry["default_mesh"] = {"identity": mesh, "fields": probe.appearance_fields(int(mesh["address"], 16))}
                    appearance = entry["default"]["fields"].get("CharacterAppearance", {}).get("value")
                    if appearance:
                        entry["default_appearance"] = {"identity": appearance, "fields": probe.appearance_fields(int(appearance["address"], 16), ("CharacterCustomization", "AppearanceIDs", "SharedAppearanceInfoId", "Skeleton", "LeaderPoseComponent"))}
                functions = []
                for cls, owner in probe.chain(address):
                    current = reader.unpack(cls+0x68, "<Q")[0]
                    seen = set()
                    while current:
                        if current in seen or len(seen) >= 1024:
                            raise ReadError("Function list bound/cycle")
                        seen.add(current)
                        member = probe.reflection.obj(current)
                        if re.search(r"OnRep_PlayerState|CharacterCustomization|AppearanceIDs|SharedAppearance|SetRace|OnRep_Race|BeginPlay", member["name"]):
                            native = reader.unpack(current+0xf8, "<Q")[0]
                            functions.append({"name": member["name"], "owner": owner, "address": hex(current),
                                              "native_rva": hex(native-reader.base) if reader.base <= native < reader.base+reader.image_size else None})
                        current = reader.unpack(current+0x48, "<Q")[0]
                entry["research_functions"] = functions
                result["classes"][obj["name"]] = entry
            if len(result["instances"]) >= 24 or obj["name"].startswith("Default__") or int(obj["flags"], 16) & 0x10:
                continue
            kind = probe.reflection.class_name(obj["class_address"])
            if kind in ("CharacterAppearanceComponent", "CCAppearanceComponent", "NPCAppearanceComponent"):
                try:
                    fields = probe.appearance_fields(address, ("CharacterCustomization", "AppearanceIDs", "SharedAppearanceInfoId", "LeaderPoseComponent", "MergedMesh", "Skeleton"))
                    entry = {"identity": probe.identity(address), "fields": fields, "meshes": {}}
                    outer = obj["outer_address"]
                    if outer:
                        entry["outer"] = {"identity": probe.identity(outer), "fields": probe.fields(outer, ("PlayerState", "bHidden", "Owner"))}
                    for name in ("LeaderPoseComponent", "MergedMesh"):
                        value = fields.get(name, {}).get("value")
                        if value:
                            entry["meshes"][name] = {"identity": value, "fields": probe.appearance_fields(int(value["address"], 16))}
                    result["instances"].append(entry)
                except (ReadError, UnicodeError) as error:
                    result["errors"].append({"address": hex(address), "error": str(error)})
        mesh_groups = [c["default_mesh"] for c in result["classes"].values() if "default_mesh" in c]
        mesh_groups += [m for entry in result["instances"] for m in entry["meshes"].values()]
        for mesh in mesh_groups:
            asset = mesh["fields"].get("SkeletalMesh", {}).get("value")
            if not asset or asset["address"] in result["assets"] or len(result["assets"]) >= 12:
                continue
            result["assets"][asset["address"]] = {"identity": asset, "fields": probe.fields(int(asset["address"], 16),
                ("Skeleton", "Materials", "LODInfo", "ImportedBounds", "PositiveBoundsExtension", "NegativeBoundsExtension", "bHasVertexColors"))}
        after = client_proof(pid)
        if any(proof[key] != after[key] for key in ("pid", "sha256", "process_created_filetime", "exe")):
            raise ReadError("Client identity changed during catalog")
        result.update(completed_client_proof=after, bytes_read=reader.bytes_read)
        return result
    finally:
        reader.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--controller", type=lambda x: int(x, 0))
    parser.add_argument("--pawn", type=lambda x: int(x, 0))
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("--spawned-actor", action="store_true", help="Validate same live Verra World without claiming acknowledged possession")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.catalog and (args.controller is None or args.pawn is None):
        parser.error("--controller and --pawn required without --catalog")
    result = catalog(args.pid) if args.catalog else inspect(args.pid, args.controller, args.pawn, require_possession=not args.spawned_actor)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "classes": list(result.get("classes", {})), "instance_count": len(result.get("instances", [])), "bytes_read": result["bytes_read"]}))
