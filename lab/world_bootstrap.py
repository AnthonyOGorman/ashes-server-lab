"""AoC object-reference research and opt-in PlayerController bootstrap.

Export grammar is independently verified against the gameplay capture (frame
3710). Default-transform new-actor construction is an experiment, not evidence
of possession, a spawned pawn, or movement. No recorded packet is replayed.
"""
from dataclasses import dataclass
import math
import secrets
from .unreal import BitReader, BitWriter, DecodeError

ACTOR_NAME = 102
# Solid, gently sloped heightfield candidate. Capsule half-height 95.99 cm,
# plus 2 cm clearance; see evidence/spawn_candidate_epoch2_49892.json.
# Client placement and static-mesh clearance still require live verification.
DEFAULT_SPAWN = (-680500., 406500., 12503.39)


@dataclass(frozen=True)
class NetGUID:
    object_id: int
    server_id: int = 0
    randomizer: int = 0

    def write(self, writer):
        writer.write(self.object_id, 64).write(self.server_id, 32).write(self.randomizer, 32)

    @classmethod
    def read(cls, reader):
        return cls(reader.read(64), reader.read(32), reader.read(32))

    def as_dict(self):
        return {"object_id": f"0x{self.object_id:016x}", "server_id": self.server_id, "randomizer": self.randomizer}


NULL_GUID = NetGUID(0)


def fresh_actor_guid():
    # Real dynamic actors (0x925a0,0x9259e,0x925a6,0x516e) are even;
    # all named asset GUIDs exported here are odd. Preserve the UE low-bit
    # dynamic/static convention despite AoC's extended 128-bit representation.
    return NetGUID((secrets.randbits(62) << 1) or 2, 1, secrets.randbits(32))


@dataclass
class ObjectRef:
    guid: NetGUID
    path: str = ""
    outer: "ObjectRef | None" = None
    checksum: int | None = None
    no_load: bool = False

    def write(self, writer):
        self.guid.write(writer)
        if self.guid == NULL_GUID:
            return
        flags = int(bool(self.path)) | (2 if self.no_load else 0) | (4 if self.checksum is not None else 0)
        writer.write(flags, 8)
        if flags & 1:
            (self.outer or ObjectRef(NULL_GUID)).write(writer)
            writer.string(self.path)
            if flags & 4:
                writer.write(self.checksum, 32)

    @classmethod
    def read(cls, reader, depth=0):
        if depth > 16:
            raise DecodeError("export outer nesting exceeds limit")
        guid = NetGUID.read(reader)
        if guid == NULL_GUID:
            return cls(guid)
        flags = reader.read(8)
        if flags & ~7:
            raise DecodeError(f"unvalidated AoC export flags {flags:#x}")
        ref = cls(guid, no_load=bool(flags & 2))
        if flags & 1:
            ref.outer = cls.read(reader, depth+1)
            ref.path = reader.string()
            ref.checksum = reader.read(32) if flags & 4 else None
        return ref

    def as_dict(self):
        result = {"guid": self.guid.as_dict(), "path": self.path, "checksum": self.checksum, "no_load": self.no_load}
        if self.outer and self.outer.guid != NULL_GUID:
            result["outer"] = self.outer.as_dict()
        return result


def decode_exports(data, bits=None):
    r = BitReader(data, bits)
    if r.read(1):
        raise DecodeError("RepLayout export groups not yet decoded")
    count = r.read(32)
    if count > 2048:
        raise DecodeError("export count exceeds safety limit")
    objects = [ObjectRef.read(r) for _ in range(count)]
    return {"objects": [o.as_dict() for o in objects], "consumed_bits": r.pos, "remaining_bits": r.remaining, "evidence": "capture_verified_128_bit_guid_recursive_exports"}


def encode_exports(objects):
    w = BitWriter().write(0, 1).write(len(objects), 32)
    for obj in objects:
        obj.write(w)
    return bytes(w.data), w.bits


def decode_actor_prefix(data, bits=None):
    r = BitReader(data, bits)
    return {"actor": NetGUID.read(r).as_dict(), "archetype": NetGUID.read(r).as_dict(), "level": NetGUID.read(r).as_dict(), "consumed_bits": r.pos, "remaining_bits": r.remaining, "evidence": "capture_verified_actor_reference_prefix_transforms_unresolved"}


def write_spawn_location(writer, location):
    """Capture-verified UE LWC scaled signed-vector grammar (0.1cm precision).

    A seven-bit header was located using independent UE5-client research:
    https://github.com/Mokocoder/UE5_python_client/blob/master/client/net/net_serialization.py
    Validation: real frame3710 gives (-660391.3,389341.8,13622.9).
    """
    if location is None:
        writer.write(0, 1)
        return
    if len(location) != 3 or not all(math.isfinite(v) for v in location):
        raise ValueError("spawn location requires three finite components")
    values = [int(math.floor(abs(v)*10+0.5)) * (-1 if v < 0 else 1) for v in location]
    count = max(1, max(abs(v).bit_length()+1 for v in values))
    if count > 63:
        raise ValueError("spawn location exceeds quantized range")
    writer.write(1, 1).write(1, 1).write(count | 64, 7)
    for value in values:
        writer.write(value & ((1 << count)-1), count)


def decode_actor_location(data, bits=None):
    r = BitReader(data, bits)
    result = decode_actor_prefix(data, bits)
    r.read(384)
    if not r.read(1):
        result["location"] = [0., 0., 0.]
    else:
        if not r.read(1):
            raise DecodeError("unquantized spawn FVector width not validated")
        header = r.read(7)
        count, scaled = header & 63, bool(header & 64)
        if count == 0:
            raise DecodeError("spawn fallback float/double schema not validated")
        values = [r.read(count) for _ in range(3)]
        result["location"] = [(v-(1 << count) if v & (1 << (count-1)) else v)/(10. if scaled else 1.) for v in values]
        result["location_component_bits"] = count
    result.update(consumed_bits=r.pos, remaining_bits=r.remaining, evidence="capture_verified_actor_guid_prefix_and_quantized_location")
    return result


def controller_references():
    # These static IDs and CDO checksum are source evidence from frame3710.
    # Dynamic actor ID below is always freshly allocated per local connection.
    package = ObjectRef(NetGUID(0x388a0ee91474b469), "/Game/ThirdPersonCPP/Blueprints/AoCPlayerControllerBP", checksum=0)
    archetype = ObjectRef(NetGUID(0x309fd7f5912a3c33), "Default__AoCPlayerControllerBP_C", package, 0x6b62891c)
    map_package = ObjectRef(NetGUID(0xb359315214b240a7), "/Game/Levels/Verra_World_Master/Verra_World_Master", checksum=0, no_load=True)
    world = ObjectRef(NetGUID(0xe66eea9dcf2327d1), "Verra_World_Master", map_package, 0, True)
    level = ObjectRef(NetGUID(0xe42f6afe6ac5e219), "PersistentLevel", world, 0, True)
    actor = fresh_actor_guid()
    return actor, archetype, level


def experimental_controller_bunches(initial_reliable):
    actor, archetype, level = controller_references()
    exports, export_bits = encode_exports([archetype, level])
    # SerializeNewActor references precede default transform flags. Default
    # vectors avoid unproved FVector float/double/quantized representations.
    w = BitWriter()
    actor.write(w)
    archetype.guid.write(w)
    level.guid.write(w)
    w.write(0, 4)
    # APlayerController::OnSerializeNewActor adds NetPlayerIndex. Zero is the
    # first local player. Its exact current-build callback needs live proof.
    w.write(0, 8)
    shared = {"channel": 3, "channel_name": ACTOR_NAME, "reliable": True, "partial": True}
    return [
        {**shared, "open": True, "exports": True, "partial_flags": [1, 0, 0], "reliable_sequence": (initial_reliable+1)&1023, "payload": exports, "payload_bits": export_bits},
        {**shared, "open": False, "exports": False, "partial_flags": [0, 0, 1], "reliable_sequence": (initial_reliable+2)&1023, "payload": bytes(w.data), "payload_bits": w.bits},
    ]


def _archetype(kind):
    # Static GUIDs/class checksums decoded from real exports: frames3716,
    # 3753 and3898 respectively. These constants describe named asset identity.
    templates = {
        "game_state": (0xc6546cc4140f45c3, "/Game/GameBlueprints/AoCGameStateBP", 0x72516bac9471f0e3, "Default__AoCGameStateBP_C", 0x01442053),
        "pawn": (0x888d5ab23568d817, "/Game/ThirdPersonCPP/Blueprints/PlayerPawn", 0x817231b97e0ae84b, "Default__PlayerPawn_C", 0x02cdc5b6),
        "player_state": (0x1ae80686e8b97865, "/Game/ThirdPersonCPP/Blueprints/AoCPlayerStateBP", 0xde917003ba3b725f, "Default__AoCPlayerStateBP_C", 0xf4f44182),
    }
    package_id, package_path, cdo_id, cdo_name, checksum = templates[kind]
    package = ObjectRef(NetGUID(package_id), package_path, checksum=0)
    return ObjectRef(NetGUID(cdo_id), cdo_name, package, checksum)


def experimental_scene_bunches(initial_reliable, location=DEFAULT_SPAWN):
    """Fresh GameState/Pawn/PlayerState creations; possession unimplemented.

    Return (kind,bunches,GUID) triples so callers can record each experiment.
    No RPC index or replication-property handle is guessed here.
    """
    _, _, level = controller_references()
    result = []
    for kind, channel in (("game_state", 5), ("pawn", 9), ("player_state", 39)):
        actor = fresh_actor_guid()
        archetype = _archetype(kind)
        exports, export_bits = encode_exports([archetype, level])
        w = BitWriter()
        actor.write(w)
        archetype.guid.write(w)
        level.guid.write(w)
        write_spawn_location(w, location if kind == "pawn" else None)
        w.write(0, 3)  # default velocity, scale and rotation
        shared = {"channel": channel, "channel_name": ACTOR_NAME, "reliable": True, "partial": True}
        bunches = [
            {**shared, "open": True, "exports": True, "partial_flags": [1, 0, 0], "reliable_sequence": (initial_reliable+1)&1023, "payload": exports, "payload_bits": export_bits},
            {**shared, "open": False, "exports": False, "partial_flags": [0, 0, 1], "reliable_sequence": (initial_reliable+2)&1023, "payload": bytes(w.data), "payload_bits": w.bits},
        ]
        result.append((kind, bunches, actor.as_dict()))
    return result


def hud_class_reference():
    """The UClass exported and passed to ClientSetHUD in capture frame3710.

    This is the concrete Blueprint class, not its CDO or a guessed HUD base.
    The original capture exported it separately after opening the controller.
    """
    package = ObjectRef(NetGUID(0x6c5157f1ebbf3de7), "/Game/UI/Widgets/BP_AOCHUD", checksum=0)
    return ObjectRef(NetGUID(0x7574e081758a110f), "BP_AOCHUD_C", package, 0xac6f1251)


def experimental_hud_bunches(last_reliable, field_index, field_max):
    """Author HUD class export+RPC; caller must supply verified live cache.

    No live dispatch occurs here. Both reliable channel sequences advance
    from the connection's retained controller sequence. Class asset metadata
    comes from an independent captured export; the RPC is constructed afresh.
    """
    hud = hud_class_reference()
    exports, export_bits = encode_exports([hud])
    argument, argument_bits = encode_rpc_object_argument(hud.guid)
    payload, payload_bits = encode_actor_rpc_content(field_index, field_max, argument, argument_bits)
    shared = {"channel": 3, "channel_name": ACTOR_NAME, "reliable": True, "partial": True}
    return [
        {**shared, "exports": True, "partial_flags": [1, 0, 0],
         "reliable_sequence": (last_reliable+1)&1023, "payload": exports, "payload_bits": export_bits},
        {**shared, "exports": False, "partial_flags": [0, 0, 1],
         "reliable_sequence": (last_reliable+2)&1023, "payload": payload, "payload_bits": payload_bits},
    ]


def encode_actor_rpc_content(field_index, field_max, argument_payload=b"", argument_bits=0):
    """Actor-only legacy RPC grammar, requiring a caller-verified class cache.

    This function never chooses a function name/index/max. The supplied cache
    mapping must come from this exact build; reflection declaration order is
    insufficient. The object-argument presence bit belongs in argument_payload.
    """
    if not 0 <= argument_bits <= len(argument_payload)*8:
        raise ValueError("invalid RPC argument bit count")
    fields = BitWriter().uint(field_index, field_max).packed(argument_bits).raw(argument_payload, argument_bits)
    block = BitWriter().write(0, 1).write(1, 1).packed(fields.bits).raw(bytes(fields.data), fields.bits)
    return bytes(block.data), block.bits


def encode_rpc_object_argument(guid):
    """One non-Bool object RPC parameter referencing an already exported GUID.

    Current build FRepLayout decoder RVA0x44e4d20 reads the presence bit;
    ObjectProperty RVA0x170af50 delegates to PackageMapClient, whose normal
    non-export object loader reads four raw UINT32 values (RVA0x141e960).
    No class-cache index or function name is chosen by this helper.
    """
    if guid is not None and not isinstance(guid, NetGUID):
        raise TypeError("RPC object reference must be a NetGUID or None")
    writer = BitWriter().write(int(guid is not None), 1)
    if guid is not None:
        guid.write(writer)
    return bytes(writer.data), writer.bits


def decode_rpc_object_argument(data, bits):
    reader = BitReader(data, bits)
    present = reader.read(1)
    guid = NetGUID.read(reader) if present else None
    if reader.remaining:
        raise DecodeError("RPC object argument has trailing bits")
    return guid


def decode_actor_rpc_content(data, bits, field_max):
    """Decode RPCs using an explicit external class-cache maximum, no names."""
    reader = BitReader(data, bits)
    if reader.read(1) or not reader.read(1):
        raise DecodeError("RPC-only actor content flags required")
    content_bits = reader.packed()
    if content_bits != reader.remaining:
        raise DecodeError("RPC content length must consume the full supplied block")
    fields = []
    while reader.remaining:
        index = reader.uint(field_max)
        count = reader.packed()
        payload = reader.raw(count)
        fields.append({"field_index": index, "argument_bits": count, "argument_hex": payload.hex()})
    return {"fields": fields, "class_field_max": field_max,
            "evidence": "actor_rpc_grammar_external_class_cache_required"}
