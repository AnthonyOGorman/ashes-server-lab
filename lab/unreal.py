"""Evidence-led UE UDP negotiation for the installed AoC client.

Wire constants are proved against the supplied gameplay PCAP, not the legacy
emulator. AoC adds a 48-bit header and extended handshake to the supplied stock
engine source. Their unknown fields remain explicitly opaque.
Actor replication/spawn/movement is deliberately not invented here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import secrets
import struct
import time
from dataclasses import dataclass, field

MAGIC = bytes.fromhex("96760c50")
MASK = 16383
CONTROL_NAME = 255
# Live client captures consume exactly to the packet terminator with this
# SerializeInt bound, including mixed 7436-bit and 28-bit bunches.  It matches
# 1024+4 bytes, but that derivation remains an inference until client init is
# traced. The source-level ReadInt grammar itself is verified in NetConnection.
BUNCH_BITS_MAX = 8224
DEFAULT_MAP = "/Game/Levels/Verra_World_Master/Verra_World_Master"
DEFAULT_GAME_MODE = "/Game/GameBlueprints/AoCGameModeBaseBP.AoCGameModeBaseBP_C"
MESSAGE_NAMES = {0: "Hello", 1: "Welcome", 2: "Upgrade", 3: "Challenge", 4: "NetSpeed", 5: "Login", 6: "Failure", 9: "Join", 10: "JoinSplit", 15: "Skip", 16: "Abort", 17: "PCSwap", 18: "ActorChannelFailure", 19: "DebugText", 20: "NetGUIDAssign", 21: "SecurityViolation", 23: "DestructionInfo"}


class DecodeError(ValueError):
    pass


class BitReader:
    def __init__(self, data: bytes, bits: int | None = None):
        self.data = data
        self.limit = len(data) * 8 if bits is None else bits
        if not 0 <= self.limit <= len(data) * 8:
            raise DecodeError("invalid bit limit")
        self.pos = 0

    @property
    def remaining(self):
        return self.limit - self.pos

    def read(self, count: int) -> int:
        if count < 0 or count > self.remaining:
            raise DecodeError(f"truncated field at bit {self.pos}: need {count}, have {self.remaining}")
        value = 0
        for i in range(count):
            value |= ((self.data[(self.pos+i)//8] >> ((self.pos+i)%8)) & 1) << i
        self.pos += count
        return value

    def raw(self, count: int) -> bytes:
        return self.read(count).to_bytes((count+7)//8, "little")

    def packed(self) -> int:
        value = 0
        for shift in range(0, 35, 7):
            byte = self.read(8)
            value |= (byte >> 1) << shift
            if value > 0xffffffff:
                raise DecodeError("packed integer overflow")
            if not byte & 1:
                return value
        raise DecodeError("overlong packed integer")

    def uint(self, maximum: int) -> int:
        """UE SerializeInt, whose width depends on the value for nonpowers of 2."""
        if not 1 <= maximum <= 0x100000000:
            raise DecodeError("invalid bounded integer maximum")
        value, mask = 0, 1
        while value + mask < maximum:
            value |= self.read(1) * mask
            mask <<= 1
        return value

    def string(self) -> str:
        length = struct.unpack("<i", self.raw(32))[0]
        if length == 0:
            return ""
        if abs(length) > 16384:
            raise DecodeError("FString exceeds safety limit")
        data = self.raw(abs(length) * (16 if length < 0 else 8))
        ending = b"\0\0" if length < 0 else b"\0"
        if not data.endswith(ending):
            raise DecodeError("FString missing terminator")
        return data[:-len(ending)].decode("utf-16-le" if length < 0 else "utf-8", errors="strict")


class BitWriter:
    def __init__(self):
        self.data = bytearray()
        self.bits = 0

    def write(self, value: int, count: int):
        if count < 0 or value < 0 or value >= 1 << count:
            raise ValueError("value does not fit bit field")
        for i in range(count):
            if self.bits // 8 == len(self.data):
                self.data.append(0)
            self.data[self.bits//8] |= ((value >> i) & 1) << (self.bits%8)
            self.bits += 1
        return self

    def raw(self, data: bytes, bits: int | None = None):
        return self.write(int.from_bytes(data, "little"), len(data)*8 if bits is None else bits)

    def packed(self, value: int):
        if not 0 <= value <= 0xffffffff:
            raise ValueError("packed integer out of range")
        while value >= 128:
            self.write(((value & 127) << 1) | 1, 8)
            value >>= 7
        return self.write(value << 1, 8)

    def uint(self, value: int, maximum: int):
        if not 1 <= maximum <= 0x100000000 or not 0 <= value < maximum:
            raise ValueError("bounded integer out of range")
        partial, mask = 0, 1
        while partial + mask < maximum:
            bit = bool(value & mask)
            self.write(int(bit), 1)
            partial |= int(bit) * mask
            mask <<= 1
        return self

    def string(self, value: str):
        if not value:
            return self.write(0, 32)
        try:
            raw = value.encode("ascii") + b"\0"
            self.write(len(raw), 32)
        except UnicodeEncodeError:
            raw = value.encode("utf-16-le") + b"\0\0"
            self.raw(struct.pack("<i", -(len(raw)//2)))
        return self.raw(raw)

    def finish(self, terminators=0) -> bytes:
        for _ in range(terminators):
            self.write(1, 1)
        return bytes(self.data)


def _reader(data):
    if len(data) < 5 or data[:4] != MAGIC:
        raise DecodeError("not an AoC UDP packet (magic mismatch or truncated)")
    if data[-1] == 0:
        raise DecodeError("missing packet termination bit")
    bits = (len(data)-1)*8 + data[-1].bit_length() - 1
    reader = BitReader(data, bits)
    reader.raw(32)
    return reader


def decode_control(data: bytes, bits: int | None = None) -> list[dict]:
    r = BitReader(data, bits)
    result = []
    while r.remaining:
        ident = r.read(8)
        message = {"id": ident, "name": MESSAGE_NAMES.get(ident, f"Unknown_{ident}")}
        if ident == 0:
            message.update(endian=r.read(8), network_version=r.read(32), encryption_token=r.string(), network_features=r.read(16))
        elif ident in (3, 6, 19, 21):
            message["text"] = r.string()
        elif ident == 1:
            message.update(map=r.string(), game_mode=r.string(), redirect=r.string())
        elif ident == 4:
            message["rate"] = r.read(32)
        elif ident == 5:
            message.update(response=r.string(), url=r.string())
            # FUniqueNetIdRepl uses a compact encoding byte followed by subtype data.
            # Capture of this build uses flag 8, FString ID, FString type.
            flags = r.read(8)
            message["unique_id_flags"] = flags
            if flags == 8:
                message["unique_id"] = r.string()
                message["unique_id_type"] = r.string()
            else:
                message["unresolved_tail_hex"] = r.raw(r.remaining).hex()
                message["evidence"] = "unresolved_unique_net_id_encoding"
                result.append(message)
                break
        elif ident not in (9, 15, 16):
            message["unresolved_tail_hex"] = r.raw(r.remaining).hex()
            message["evidence"] = "unknown_control_schema"
            result.append(message)
            break
        result.append(message)
    return result


def decode_packet(data: bytes, direction: str = "client", _payload_max: int = BUNCH_BITS_MAX) -> dict:
    """Decode captured AoC build. Malformed packets return a structured error."""
    try:
        r = _reader(data)
        result = {"protocol": "aoc_unreal_udp", "session_id": r.read(2), "client_id": r.read(3), "handshake": bool(r.read(1)), "wire_bytes": len(data)}
        if result["handshake"]:
            result.update(restart=bool(r.read(1)), min_version=r.read(8), version=r.read(8), packet_type=r.read(8), sent_count=r.read(8), network_version=r.read(32), network_features=r.read(16), secret_id=r.read(1))
            result["timestamp"] = struct.unpack("<d", r.raw(64))[0]
            result["cookie"] = r.raw(160).hex()
            # Installed game adds an opaque byte-aligned extension after cookie.
            # Keeping every byte matters: challenge response echoes it unchanged.
            result["extension_hex"] = r.raw(r.remaining).hex()
            result["extension_bits"] = r.pos - 344
            result["evidence"] = "capture_verified_header_opaque_extension"
            result["kind"] = "stateless." + {0: "Initial", 1: "Challenge", 2: "Response", 3: "Ack"}.get(result["packet_type"], "Unknown")
            return result
        # Inner NetConnection terminator is immediately before PacketHandler's.
        if r.limit <= r.pos or (data[(r.limit-1)//8] >> ((r.limit-1)%8)) & 1 != 1:
            raise DecodeError("missing NetConnection termination bit")
        r.limit -= 1
        packed = r.read(32)
        words = (packed & 15) + 1
        if words > 8:
            raise DecodeError("ack history exceeds engine 256-bit window")
        result.update(sequence=(packed >> 18) & MASK, ack=(packed >> 4) & MASK, ack_history=[r.read(32) for _ in range(words)])
        result["custom_header_opaque"] = r.read(48)
        result["custom_header_evidence"] = "capture_verified_48_bits_schema_unresolved"
        has_info = r.read(1)
        result["has_packet_info"] = bool(has_info)
        if has_info:
            result["jitter_clock"] = r.read(10)
            result["has_server_frame_time"] = bool(r.read(1))
            if result["has_server_frame_time"] and direction == "server":
                result["server_frame_time_ms"] = r.read(8)
        result["packet_info_opaque"] = result["custom_header_opaque"]
        bunches = []
        while r.remaining:
            start = r.pos
            control = r.read(1)
            opened, closed = (r.read(1), r.read(1)) if control else (0, 0)
            close_reason = None
            if closed:
                # Exact current live close fixture proves four zero-valued
                # reason bits and complete bunch exhaustion. Nonzero reasons
                # remain unsupported: the custom enum maximum is unresolved.
                close_reason = r.read(4)
                if close_reason != 0:
                    raise DecodeError("nonzero channel-close reason not validated for this build")
            paused, reliable = r.read(1), r.read(1)
            channel = r.packed()
            exports, must_map, partial = r.read(1), r.read(1), r.read(1)
            sequence = r.read(10) if reliable else None
            partial_flags = [r.read(1) for _ in range(3)] if partial else []
            name = None
            if reliable or opened:
                if r.read(1):
                    name = r.packed()
                else:
                    name = {"string": r.string(), "number": r.read(32)}
            length_start = r.pos
            count = r.uint(_payload_max)
            length_bits = r.pos - length_start
            if closed and (channel != 0 or opened or not reliable or name != CONTROL_NAME or exports or must_map or partial or count != 0):
                raise DecodeError("only exact zero-payload control-channel close is validated")
            payload = r.raw(count)
            bunch = {"start_bit": start, "channel": channel, "open": bool(opened), "close": bool(closed), "reliable": bool(reliable), "paused": bool(paused), "reliable_sequence": sequence, "channel_name": name, "exports": bool(exports), "must_map": bool(must_map), "partial": bool(partial), "partial_flags": partial_flags, "payload_bits": count, "payload_hex": payload.hex()}
            bunch["payload_length_field_bits"] = length_bits
            if closed:
                bunch.update(close_reason=close_reason, close_reason_evidence="capture_validated_zero_reason_4bits_max_unresolved")
            if channel == 0 and not exports and not partial:
                bunch["messages"] = decode_control(payload, count)
            else:
                bunch["evidence"] = "opaque_replication_payload"
            bunches.append(bunch)
        if any(bunch["close"] for bunch in bunches) and len(bunches) != 1:
            raise DecodeError("only standalone complete control-channel close is validated")
        result["bunches"] = bunches
        result["payload_length_max"] = _payload_max
        result["payload_length_evidence"] = "source_verified_SerializeInt_capture_inferred_maximum"
        names = [m["name"] for b in bunches for m in b.get("messages", [])]
        result["kind"] = "control.Close" if any(b["close"] for b in bunches) else "control." + "+".join(names) if names else "game.bunch" if bunches else "game.ack"
        result["evidence"] = "capture_verified_transport"
        return result
    except (DecodeError, UnicodeError, struct.error) as exc:
        # Earlier capture/server encodings use the power-of-two bound. Both
        # candidates must consume all bunches exactly; no leftover padding is
        # accepted and no fixed-width retry can shift unknown replication data.
        if _payload_max == BUNCH_BITS_MAX:
            alternate = decode_packet(data, direction, 8192)
            if "error" not in alternate:
                alternate["dialect_evidence"] = "capture_compatible_8192_bit_bunch_bound"
                return alternate
        return {"protocol": "aoc_unreal_udp", "kind": "game.decode_error", "error": str(exc), "wire_bytes": len(data)}


def encode_control(ident, **values):
    w = BitWriter().write(ident, 8)
    if ident == 0:
        w.write(1, 8).write(values["network_version"], 32).string("").write(0, 16)
    elif ident in (3, 6):
        w.string(values.get("text", ""))
    elif ident == 1:
        w.string(values["map"]).string(values["game_mode"]).string(values.get("redirect", ""))
    elif ident == 4:
        w.write(values.get("rate", 200000), 32)
    elif ident == 5:
        w.string(values.get("response", "")).string(values.get("url", "?Name=LocalExplorer")).write(8, 8).string(values.get("unique_id", "LocalExplorer")).string("NULL")
    elif ident != 9:
        raise ValueError("unsupported outgoing control message")
    return w.finish()


def _write_bunch(w, bunch):
    opened = bool(bunch.get("open"))
    reliable = bool(bunch.get("reliable", True))
    closed = bool(bunch.get("close"))
    w.write(int(opened or closed), 1)
    if opened or closed:
        w.write(int(opened), 1).write(int(closed), 1)
    if closed:
        if bunch.get("close_reason", 0) != 0:
            raise ValueError("Only captured zero-valued close reason is supported")
        w.write(0, 4)
    w.write(0, 1).write(int(reliable), 1).packed(bunch.get("channel", 0))
    partial = bool(bunch.get("partial"))
    w.write(int(bool(bunch.get("exports"))), 1).write(0, 1).write(int(partial), 1)
    if reliable:
        w.write(bunch["reliable_sequence"] & 1023, 10)
    if partial:
        for flag in bunch["partial_flags"]:
            w.write(flag, 1)
    if reliable or opened:
        w.write(1, 1).packed(bunch.get("channel_name", CONTROL_NAME))
    payload = bunch["payload"]
    count = bunch.get("payload_bits", len(payload)*8)
    w.uint(count, BUNCH_BITS_MAX).raw(payload, count)


def encode_packet(session, client, sequence, ack, history, payload=None, reliable_sequence=0, opened=False, info=None, bunches=None):
    w = BitWriter().raw(MAGIC).write(session, 2).write(client, 3).write(0, 1)
    w.write(((sequence & MASK) << 18) | ((ack & MASK) << 4) | (len(history)-1), 32)
    for word in history:
        w.write(word, 32)
    w.write(info or 0, 48)
    w.write(int(info is not None), 1)
    if info is not None:
        w.write(int(time.monotonic()*1000) & 1023, 10).write(0, 1)
    if payload is not None:
        _write_bunch(w, {"payload": payload, "reliable_sequence": reliable_sequence, "open": opened})
    for bunch in bunches or []:
        _write_bunch(w, bunch)
    return w.finish(2)


def encode_handshake(parsed, packet_type, timestamp, cookie, extension=None):
    w = BitWriter().raw(MAGIC).write(parsed["session_id"], 2).write(parsed["client_id"], 3).write(1, 1).write(0, 1)
    w.write(parsed["min_version"], 8).write(parsed["version"], 8).write(packet_type, 8).write(parsed["sent_count"], 8)
    w.write(parsed["network_version"], 32).write(parsed["network_features"], 16).write(int(packet_type == 3), 1)
    w.raw(struct.pack("<d", timestamp)).raw(cookie)
    tail = bytes.fromhex(parsed.get("extension_hex", "")) if extension is None else extension
    w.raw(tail)
    return w.finish(1)


@dataclass
class Connection:
    cookie: bytes
    session: int
    client: int
    out_seq: int
    in_seq: int
    out_reliable: int
    in_reliable: int
    history: int = 0
    phase: str = "connected"
    pending: dict = field(default_factory=dict)
    pending_bunches: dict = field(default_factory=dict)
    info: int | None = None
    last_seen: float = field(default_factory=time.monotonic)
    actor_guids: dict = field(default_factory=dict)
    channel_reliable: dict = field(default_factory=dict)
    consumed_experiment_ids: set = field(default_factory=set)
    possession_ack_contract: dict = field(default_factory=dict)
    possession_acknowledged: bool = False
    connection_id: str = field(default_factory=lambda: secrets.token_hex(12))
    handshake_timestamp: float = 0.


class WorldProtocol:
    """Negotiates handshake/control; emits truthful milestones, no fake actors."""
    def __init__(self, event=None, map_name=DEFAULT_MAP, game_mode=DEFAULT_GAME_MODE, bootstrap_enabled=False):
        # Include the explicit local movement experiment in parser hot reloads.
        # This does not enable it: a fresh proof-bound profile is still required.
        import importlib
        from . import terrain, capsule_sweep, triangle_collision, static_collision, terrain_movement, movement_response, terrain_movement_experiment, terrain_relocation, terrain_cache_extension, static_cache_extension, stats_component, world_initialization, collision_refresh
        for module in (terrain, capsule_sweep, triangle_collision, static_collision, terrain_movement, movement_response, terrain_movement_experiment, terrain_relocation, terrain_cache_extension, static_cache_extension, stats_component, world_initialization, collision_refresh):
            importlib.reload(module)
        self.event = event or (lambda kind, detail: None)
        self.map_name, self.game_mode = map_name, game_mode
        self.secret = secrets.token_bytes(32)
        self.connections = {}
        self.bootstrap_enabled = bootstrap_enabled
        # The desktop lab reloads this parser without restarting the game.
        # Revive only a verified dead receiver on its still-open local socket;
        # an active receiver and all connection state remain untouched.
        from .udp_service import repair_dead_listener
        owner=getattr(event,'__self__',None)
        repair_dead_listener(getattr(owner,'world',None))
        from .world_initialization import ensure_worker
        ensure_worker(owner)
        from .collision_refresh import ensure_worker as ensure_collision_refresh
        ensure_collision_refresh(owner)
        from . import world_view
        importlib.reload(world_view)
        world_view.install(owner)

    def _cookie(self, addr, timestamp):
        return hmac.new(self.secret, repr(addr).encode() + struct.pack("<d", timestamp), hashlib.sha1).digest()

    def _send(self, c, payload=None, reliable_sequence=None, retries=0):
        if payload is not None and reliable_sequence is None:
            c.out_reliable = (c.out_reliable + 1) & 1023
        reliable_sequence = c.out_reliable if reliable_sequence is None else reliable_sequence
        history = [(c.history >> shift) & 0xffffffff for shift in range(0, 256, 32)]
        while len(history) > 1 and history[-1] == 0:
            history.pop()
        packet = encode_packet(c.session, c.client, c.out_seq, c.in_seq, history, payload, reliable_sequence, info=c.info)
        if payload is not None:
            c.pending[c.out_seq] = (payload, reliable_sequence, time.monotonic(), retries)
        c.out_seq = (c.out_seq + 1) & MASK
        return packet

    def handle(self, data: bytes, addr: tuple) -> list[bytes]:
        parsed = decode_packet(data)
        if "error" in parsed:
            self.event("udp_decode_error", {"peer": str(addr), **parsed})
            return []
        now = time.monotonic()
        # Bound connection residency even during repeated test attempts.
        for peer, old in list(self.connections.items()):
            if now - old.last_seen > 120:
                del self.connections[peer]
        if parsed["handshake"]:
            if parsed["restart"] or parsed["version"] not in (3, 4) or parsed["network_features"] != 0:
                self.event("udp_unsupported_handshake", parsed)
                return []
            if parsed["packet_type"] == 0:
                timestamp = time.time()
                cookie = self._cookie(addr, timestamp)
                self.event("udp_challenge", {"peer": str(addr), "network_version": parsed["network_version"], "opaque_extension_bytes": parsed["extension_bits"]//8})
                return [encode_handshake(parsed, 1, timestamp, cookie)]
            if parsed["packet_type"] == 2:
                timestamp = parsed["timestamp"]
                if not 0 <= time.time()-timestamp <= 30 or not hmac.compare_digest(self._cookie(addr, timestamp).hex(), parsed["cookie"]):
                    self.event("udp_rejected_cookie", {"peer": str(addr)})
                    return []
                cookie = bytes.fromhex(parsed["cookie"])
                server, client = struct.unpack("<HH", cookie[:4])
                previous = self.connections.get(addr)
                if previous is not None and hmac.compare_digest(previous.cookie, cookie):
                    if (previous.session, previous.client) != (parsed["session_id"], parsed["client_id"]):
                        self.event("udp_rejected_handshake_identity", {"peer":str(addr)})
                        return []
                    # Retransmitted valid Response must preserve negotiated
                    # sequence/phase/actors, including an already closed epoch.
                    previous.last_seen = now
                else:
                    if previous is not None and timestamp <= getattr(previous, "handshake_timestamp", 0.):
                        self.event("udp_rejected_old_handshake", {"peer":str(addr)})
                        return []
                    if previous is None and len(self.connections) >= 64:
                        self.event("udp_capacity", {"peer": str(addr)})
                        return []
                    fresh = Connection(cookie, parsed["session_id"], parsed["client_id"], server & MASK,
                        (client-1) & MASK, server & 1023, client & 1023, handshake_timestamp=timestamp)
                    self.connections[addr] = fresh
                    self.event("udp_handshake", {"peer":str(addr), "connection_id":fresh.connection_id,
                        "replaces_existing":previous is not None,
                        "previous_connection_id":getattr(previous, "connection_id", None),
                        "evidence":"validated_live_cookie_response_new_connection"})
                return [encode_handshake(parsed, 3, -1., cookie)]
            return []
        c = self.connections.get(addr)
        if c is None:
            self.event("udp_unconnected", {"peer": str(addr)})
            return []
        c.last_seen = now
        if parsed["client_id"] != c.client or parsed["session_id"] != c.session:
            return []
        if c.phase == "closed":
            return [self._send(c)]
        delta = (parsed["sequence"] - c.in_seq) & MASK
        if delta == 0:
            return [self._send(c)]
        if not 0 < delta < 8192:
            return []
        # Remove reliable deliveries reported by client's ack history.
        for seq in list(c.pending):
            distance = (parsed["ack"] - seq) & MASK
            if distance < len(parsed["ack_history"])*32 and (parsed["ack_history"][distance//32] >> (distance%32)) & 1:
                del c.pending[seq]
        for seq in list(c.pending_bunches):
            distance = (parsed["ack"] - seq) & MASK
            if distance < len(parsed["ack_history"])*32 and (parsed["ack_history"][distance//32] >> (distance%32)) & 1:
                del c.pending_bunches[seq]
        c.in_seq = parsed["sequence"]
        c.history = ((c.history << min(delta, 256)) | 1) & ((1 << 256)-1)
        c.info = parsed.get("packet_info_opaque", c.info)
        outgoing = []
        for bunch in parsed["bunches"]:
            if bunch["channel"] != 0 or "messages" not in bunch:
                if self._observe_possession_ack(c, bunch, addr):
                    continue
                if self._observe_pawn_movement_rpc(c, bunch, addr):
                    for payload, bits in getattr(c,'terrain_response_queue',[]):
                        outgoing.append(self._send_bunches(c,[{'channel':9,'channel_name':102,
                            'reliable':False,'payload':payload,'payload_bits':bits}]))
                    c.terrain_response_queue=[]
                    continue
                self.event("udp_unknown_payload", {"peer": str(addr), "channel": bunch["channel"], "bits": bunch["payload_bits"], "evidence": "opaque_no_actor_semantics"})
                continue
            if bunch["reliable"]:
                expected = (c.in_reliable + 1) & 1023
                backwards = (c.in_reliable-bunch["reliable_sequence"]) & 1023
                if backwards < 512:
                    # A delivered reliable bunch may be re-sent in a new
                    # packet when its prior transport ACK was lost.
                    continue
                if bunch["reliable_sequence"] != expected:
                    c.history &= ~1
                    self.event("udp_reliable_gap", {"peer": str(addr), "expected": expected, "observed": bunch["reliable_sequence"]})
                    continue
                c.in_reliable = expected
            if bunch.get("close") and bunch.get("close_reason") == 0 and bunch.get("channel_name") == CONTROL_NAME and not bunch.get("partial"):
                previous_phase = c.phase
                c.phase = "closed"
                c.pending.clear()
                c.pending_bunches.clear()
                c.possession_acknowledged = False
                self.event("udp_connection_closed", {"peer":str(addr),
                    "connection_id":getattr(c, "connection_id", None), "previous_phase":previous_phase,
                    "reason_value":0, "evidence":"observed_complete_client_control_channel_close",
                    "cause":"not_inferred_from_close_packet"})
                return [self._send(c)]
            for message in bunch["messages"]:
                ident = message["id"]
                if ident == 0 and c.phase == "connected":
                    c.phase = "challenge"
                    self.event("hello", {"peer": str(addr), "network_version": message["network_version"]})
                    outgoing.append(self._send(c, encode_control(3, text=secrets.token_hex(4).upper())))
                elif ident == 5 and c.phase == "challenge":
                    c.phase = "welcomed"
                    self.event("login", {"peer": str(addr), "url": message.get("url", "")})
                    outgoing.append(self._send(c, encode_control(1, map=self.map_name, game_mode=self.game_mode)))
                    self.event("welcome", {"peer": str(addr), "map": self.map_name, "evidence": "emitted_welcome_not_map_loaded"})
                elif ident == 4:
                    self.event("netspeed", {"peer": str(addr), "rate": message["rate"]})
                elif ident == 9 and c.phase == "welcomed":
                    c.phase = "joined"
                    self.event("join", {"peer": str(addr), "evidence": "observed_NMT_Join_actor_spawn_unimplemented"})
                    if self.bootstrap_enabled:
                        outgoing.extend(self._bootstrap(c))
                        self.event("controller_bootstrap_experiment", {"peer": str(addr), "evidence": "authored_128_bit_guid_exports_and_new_actor_requires_live_validation", "channel": 3})
                else:
                    self.event("udp_control", {"peer": str(addr), "message": message, "phase": c.phase})
        # Reliable bunches keep the same channel sequence when re-sent in a new
        # datagram. Packet sequence numbers must continue advancing normally.
        for seq, (payload, reliable, sent_at, retries) in list(c.pending.items()):
            if now - sent_at > 0.5:
                del c.pending[seq]
                if retries < 8:
                    outgoing.append(self._send(c, payload, reliable, retries+1))
                    self.event("udp_retransmit", {"peer": str(addr), "channel_sequence": reliable, "attempt": retries+1})
                else:
                    self.event("udp_reliable_timeout", {"peer": str(addr), "channel_sequence": reliable})
        for seq, (bunches, sent_at, retries) in list(c.pending_bunches.items()):
            # Movement responses are unreliable and superseded by later moves.
            # Retained connections may still contain entries from the old
            # sender, which incorrectly retried every movement acknowledgement.
            reliable_bunches=[b for b in bunches if b.get('reliable')]
            if not reliable_bunches:
                del c.pending_bunches[seq]
                continue
            if now - sent_at > 0.5:
                del c.pending_bunches[seq]
                if retries < 8:
                    outgoing.append(self._send_bunches(c, reliable_bunches, retries+1))
                else:
                    self.event("controller_bootstrap_timeout", {"peer": str(addr)})
        outgoing.extend(self._poll_client_restart_experiment(c, addr))
        if not outgoing:
            outgoing.append(self._send(c))
        return outgoing

    def _send_bunches(self, c, bunches, retries=0):
        if retries == 0:
            if not hasattr(c, "channel_reliable"):
                c.channel_reliable = {}
            for bunch in bunches:
                if bunch.get("reliable"):
                    c.channel_reliable[bunch["channel"]] = bunch["reliable_sequence"] & 1023
        history = [(c.history >> shift) & 0xffffffff for shift in range(0, 256, 32)]
        while len(history) > 1 and history[-1] == 0:
            history.pop()
        packet = encode_packet(c.session, c.client, c.out_seq, c.in_seq, history, info=c.info, bunches=bunches)
        reliable_bunches=[b for b in bunches if b.get('reliable')]
        if reliable_bunches:
            c.pending_bunches[c.out_seq] = (reliable_bunches, time.monotonic(), retries)
        c.out_seq = (c.out_seq+1) & MASK
        return packet

    def _bootstrap(self, connection):
        from .world_bootstrap import experimental_controller_bunches, decode_actor_prefix
        if connection.phase != "joined":
            raise ValueError("Controller experiment requires an observed Join")
        if not hasattr(connection, "actor_guids"):
            connection.actor_guids = {}
        if "controller" in connection.actor_guids:
            raise ValueError("Controller actor has already been authored on this connection")
        # Actor channel reliable numbering starts from the original cookie,
        # independently of messages already sent on control channel zero.
        initial = struct.unpack("<H", connection.cookie[:2])[0] & 1023
        bunches = experimental_controller_bunches(initial)
        connection.actor_guids["controller"] = decode_actor_prefix(bunches[-1]["payload"], bunches[-1]["payload_bits"])["actor"]
        return [self._send_bunches(connection, bunches)]

    def _bootstrap_scene(self, connection, location=None):
        """Explicit experiment call; never triggered by normal Join.

        Packet emission cannot establish possession or movement. The calling
        local test endpoint must record the client's acceptance separately.
        """
        from .world_bootstrap import experimental_scene_bunches, DEFAULT_SPAWN
        if connection.phase != "joined":
            raise ValueError("Scene experiment requires an observed Join")
        if not hasattr(connection, "actor_guids"):
            connection.actor_guids = {}
        if any(kind in connection.actor_guids for kind in ("game_state", "pawn", "player_state")):
            raise ValueError("Scene actors have already been authored on this connection")
        initial = struct.unpack("<H", connection.cookie[:2])[0] & 1023
        packets = []
        for kind, bunches, actor in experimental_scene_bunches(initial, DEFAULT_SPAWN if location is None else location):
            connection.actor_guids[kind] = actor
            packets.append(self._send_bunches(connection, bunches))
            self.event("scene_bootstrap_experiment", {"kind": kind, "actor_guid": actor, "evidence": "authored_actor_requires_client_acceptance_possession_unimplemented"})
        return packets

    def _client_restart(self, connection, field_index, field_max, *, cache_verified=False, actors_verified=False):
        """Guarded explicit experiment; emission is not possession evidence.

        The caller must verify the exact live class cache's ClientRestart index
        and maximum, and verify that this connection's controller and pawn
        GUIDs resolve to accepted client actors. No default field values exist.
        Old connection objects preserved across protocol reloads are supported;
        missing authored references cause refusal, never fabricated IDs.
        """
        from .world_bootstrap import ACTOR_NAME, NetGUID, encode_rpc_object_argument, encode_actor_rpc_content
        if connection.phase != "joined" or not cache_verified or not actors_verified:
            raise ValueError("ClientRestart requires Join, verified live cache and accepted actors")
        if not isinstance(field_index, int) or isinstance(field_index, bool) or not isinstance(field_max, int) or isinstance(field_max, bool) or not 0 <= field_index < field_max <= 8193:
            raise ValueError("Explicit valid live class-cache index and maximum required")
        refs = getattr(connection, "actor_guids", {})
        sequences = getattr(connection, "channel_reliable", {})
        if "controller" not in refs or "pawn" not in refs or 3 not in sequences:
            raise ValueError("Connection has no retained authored controller/pawn references or channel sequence")
        pawn = refs["pawn"]
        guid = NetGUID(int(pawn["object_id"], 16), pawn["server_id"], pawn["randomizer"])
        argument, argument_bits = encode_rpc_object_argument(guid)
        payload, payload_bits = encode_actor_rpc_content(field_index, field_max, argument, argument_bits)
        sequence = (sequences[3]+1) & 1023
        bunch = {"channel": 3, "channel_name": ACTOR_NAME, "reliable": True,
                 "reliable_sequence": sequence, "payload": payload, "payload_bits": payload_bits}
        packet = self._send_bunches(connection, [bunch])
        self.event("client_restart_experiment", {"actor_guid": pawn, "field_index": field_index,
            "field_max": field_max, "channel": 3, "reliable_sequence": sequence,
            "evidence": "authored_RPC_requires_observed_client_acknowledgement_and_possession"})
        return [packet]

    def _client_set_hud(self, connection, field_index, field_max, *, cache_verified=False, actors_verified=False):
        from .world_bootstrap import experimental_hud_bunches, hud_class_reference
        refs = getattr(connection, "actor_guids", {})
        sequences = getattr(connection, "channel_reliable", {})
        if connection.phase != "joined" or not cache_verified or not actors_verified or "controller" not in refs or 3 not in sequences:
            raise ValueError("HUD experiment requires Join, verified cache and accepted local controller")
        if field_index != 53 or field_max != 1032:
            raise ValueError("Exact verified ClientSetHUD field53/max1032 required")
        if getattr(connection, "hud_class_emitted", None):
            raise ValueError("HUD class initialization has already been authored on this connection")
        bunches = experimental_hud_bunches(sequences[3], field_index, field_max)
        packet = self._send_bunches(connection, bunches)
        connection.hud_class_emitted = hud_class_reference().guid.as_dict()
        self.event("client_set_hud_experiment", {"class_guid": connection.hud_class_emitted,
            "class_path": "/Game/UI/Widgets/BP_AOCHUD.BP_AOCHUD_C", "field_index": field_index,
            "field_max": field_max, "channel": 3, "reliable_sequence": bunches[-1]["reliable_sequence"],
            "evidence": "authored_HUD_class_export_and_RPC_requires_live_MyHUD_acceptance_proof"})
        return [packet]

    def _pawn_autonomous(self, connection, *, proof_verified=False):
        from .pawn_role import encode_pawn_autonomous_content
        if not proof_verified or not getattr(connection, "possession_acknowledged", False) or connection.phase != "joined":
            raise ValueError("Pawn autonomy experiment requires exact proofs and observed possession")
        if getattr(connection, "pawn_autonomous_emitted", False):
            raise ValueError("Pawn autonomy experiment already emitted on this connection")
        sequences = getattr(connection, "channel_reliable", {})
        pawn = getattr(connection, "actor_guids", {}).get("pawn")
        if pawn is None or 9 not in sequences:
            raise ValueError("Accepted retained pawn channel9 and reliable sequence required")
        payload, bits = encode_pawn_autonomous_content()
        bunch = {"channel": 9, "channel_name": 102, "reliable": True,
            "reliable_sequence": (sequences[9]+1)&1023, "payload": payload, "payload_bits": bits}
        packet = self._send_bunches(connection, [bunch])
        connection.pawn_autonomous_emitted = True
        self.event("pawn_autonomous_experiment", {"actor_guid": pawn, "channel": 9,
            "server_property": "RemoteRole", "wire_handle": 8, "raw_enum_bits": 3,
            "desired_client_role": 2, "reliable_sequence": bunch["reliable_sequence"],
            "evidence": "authored_role_only_property_requires_read_only_acceptance_and_movement_probe",
            "movement_proved": False})
        return [packet]

    def _game_state_begin_play(self, connection, *, proof_verified=False):
        from .game_state_begin_play import encode_game_state_begin_play_content
        if not proof_verified or not getattr(connection, "possession_acknowledged", False) or connection.phase != "joined":
            raise ValueError("GameState BeginPlay experiment requires exact live proofs and possession")
        if getattr(connection, "game_state_begin_play_emitted", False):
            raise ValueError("GameState BeginPlay already emitted on this connection")
        sequences = getattr(connection, "channel_reliable", {})
        actor = getattr(connection, "actor_guids", {}).get("game_state")
        if actor is None or 5 not in sequences:
            raise ValueError("Retained GameState channel5 and reliable sequence required")
        payload, bits = encode_game_state_begin_play_content()
        bunch = {"channel":5, "channel_name":102, "reliable":True,
            "reliable_sequence":(sequences[5]+1)&1023, "payload":payload, "payload_bits":bits}
        packet = self._send_bunches(connection, [bunch])
        connection.game_state_begin_play_emitted = True
        self.event("game_state_begin_play_experiment", {"actor_guid":actor, "channel":5,
            "wire_handle":21, "raw_bool_bits":1, "desired_value":True,
            "reliable_sequence":bunch["reliable_sequence"], "movement_proved":False,
            "evidence":"authored_single_property_requires_read_only_actor_lifecycle_acceptance"})
        return [packet]

    def _observe_possession_ack(self, connection, bunch, peer):
        """Recognize only the RPC pinned by verified cache and actual dispatch.

        Actor traffic remains opaque without that connection-specific contract.
        A matching acknowledgement proves client possession acceptance, never
        terrain readiness, a visible character, or movement.
        """
        from .world_bootstrap import decode_actor_rpc_content, decode_rpc_object_argument
        contract = getattr(connection, "possession_ack_contract", {})
        refs = getattr(connection, "actor_guids", {})
        if (connection.phase != "joined" or not contract or
                contract.get("controller_guid") != refs.get("controller") or
                contract.get("pawn_guid") != refs.get("pawn") or
                bunch.get("channel") != 3 or not bunch.get("reliable") or
                any(bunch.get(flag) for flag in ("exports", "must_map", "partial", "open", "close"))):
            return False
        try:
            fields = decode_actor_rpc_content(bytes.fromhex(bunch["payload_hex"]),
                                               bunch["payload_bits"], contract["field_max"])["fields"]
            if len(fields) != 1 or fields[0]["field_index"] != contract["field_index"]:
                return False
            argument = fields[0]
            guid = decode_rpc_object_argument(bytes.fromhex(argument["argument_hex"]), argument["argument_bits"])
            if guid is None or guid.as_dict() != contract["pawn_guid"]:
                return False
        except (DecodeError, ValueError, KeyError, TypeError):
            return False
        if not getattr(connection, "possession_acknowledged", False):
            connection.possession_acknowledged = True
            self.event("player_spawned", {"peer": str(peer), "actor_guid": guid.as_dict(),
                "controller_guid": contract["controller_guid"], "channel": 3,
                "rpc": "ServerAcknowledgePossession", "field_index": contract["field_index"],
                "field_max": contract["field_max"], "cache_snapshot": contract["cache_snapshot"],
                "evidence": "observed_client_possession_ack_for_exact_dispatched_pawn_GUID",
                "movement_proved": False})
        return True

    def _observe_pawn_movement_rpc(self, connection, bunch, peer):
        """Decode client reports without treating their positions as authority."""
        from .movement_rpc import decode_pawn_movement_rpc
        from .movement_serialization import decode_server_move_argument
        contract = getattr(connection, 'pawn_movement_contract', {})
        refs = getattr(connection, 'actor_guids', {})
        if (connection.phase != 'joined' or not connection.possession_acknowledged or
                contract.get('pawn_guid') != refs.get('pawn') or not refs.get('pawn') or
                contract.get('field_max') != 198 or contract.get('server_move_field') != 44 or
                bunch.get('channel') != 9 or any(bunch.get(flag) for flag in
                ('exports', 'must_map', 'partial', 'open', 'close'))):
            return False
        try:
            decoded = decode_pawn_movement_rpc(bytes.fromhex(bunch['payload_hex']), bunch['payload_bits'], 'client')
        except (DecodeError, ValueError, KeyError, TypeError):
            return False
        for field in decoded['fields']:
            if field.get('rpc') != 'ServerMovePacked':
                continue
            try:
                field['movement'] = decode_server_move_argument(
                    bytes.fromhex(field['argument_hex']), field['argument_bits'])
                field['packed_data_decoded'] = True
            except (DecodeError, ValueError) as exc:
                field['movement_decode_error'] = str(exc)
        decoded['evidence'] = 'exact_cache_RPC_envelope_and_bounded_custom_movement_decoder'
        self.event('pawn_movement_rpc_observed', {'peer': str(peer),
            'connection_id': connection.connection_id, 'actor_guid': refs['pawn'],
            'channel': 9, 'reliable': bunch.get('reliable'),
            'cache_snapshot': contract['cache_snapshot'], **decoded})
        try:
            from .terrain_movement_experiment import responses
            connection.terrain_response_queue=responses(connection,peer,decoded,self.event)
        except (ValueError,OSError,KeyError,TypeError,StopIteration) as exc:
            # Disable a rejected profile for this connection; it must be corrected
            # explicitly before another initialization attempt.
            connection.terrain_response_queue=[]
            fingerprint=str(exc)
            if getattr(connection,'terrain_profile_error',None)!=fingerprint:
                self.event('terrain_movement_profile_rejected',{'connection_id':connection.connection_id,'reason':fingerprint})
                connection.terrain_profile_error=fingerprint
        return True

    def _poll_client_restart_experiment(self, connection, peer):
        """Consume one proof-bound HUD initialization or possession command.

        There is no default command and no arbitrary RPC facility. The exact
        current evidence files must prove this connection's accepted actors,
        local controller and inherited ClientRestart cache entry. Polling reads
        only a small fixed file; consumed IDs survive module reloads on the
        existing Connection object.
        """
        if connection.phase != "joined":
            return []
        from tools.protocol_proof import proof_paths, validate_current_client_proofs
        root = Path(__file__).resolve().parents[1]
        command_path = root/"data/client-restart-experiment.json"
        try:
            stat = command_path.stat()
        except FileNotFoundError:
            return []
        fingerprint = (stat.st_mtime_ns, stat.st_size)
        if getattr(connection, "experiment_file_fingerprint", None) == fingerprint:
            return []
        connection.experiment_file_fingerprint = fingerprint
        command_id = None
        try:
            if not 0 < stat.st_size <= 16384:
                raise ValueError("Command file size is outside the bounded schema")
            command = json.loads(command_path.read_text(encoding="utf-8"))
            required = {"command", "peer", "controller_guid", "pawn_guid", "cache_snapshot", "actor_snapshot", "id", "expires_at"}
            if isinstance(command, dict) and command.get("command") == "PawnAutonomous":
                required |= {"layout_snapshot", "role_snapshot"}
            if isinstance(command, dict) and command.get("command") == "GameStateBeginPlay":
                required |= {"game_state_guid", "layout_snapshot", "begin_play_snapshot", "lifecycle_snapshot"}
            if isinstance(command, dict) and command.get("command") in ("ControllerPlayerState", "PawnPlayerState"):
                required |= {"player_state_guid", "layout_snapshot", "receiver_snapshot"}
            if isinstance(command, dict) and command.get('command')=='CharacterInfoExport':
                required |= {'component_guid','appearance_snapshot','receiver_snapshot'}
            if isinstance(command, dict) and command.get('command')=='StatsComponentExport':
                required |= {'component_guid','receiver_snapshot'}
            if isinstance(command, dict) and command.get('command') in ('StatsGravity','StatsSpeed'):
                required |= {'component_guid','mapping_snapshot','stats_cache_snapshot'}
            if isinstance(command,dict) and command.get('command')=='CharacterInfoName':
                required |= {'component_guid','character_name','appearance_snapshot','mapping_snapshot','layout_snapshot'}
            if isinstance(command,dict) and command.get('command')=='CharacterInfoGuid':
                required |= {'component_guid','character_id','appearance_snapshot','mapping_snapshot','layout_snapshot'}
            if not isinstance(command, dict) or set(command) != required:
                raise ValueError("Command must contain exactly the documented schema fields")
            # A fixed command targets one peer. Other connections must retain
            # their normal Join behavior without consuming someone else's id.
            if command["peer"] != list(peer):
                return []
            command_id = command["id"]
            if not isinstance(command_id, str) or not 1 <= len(command_id) <= 128:
                raise ValueError("Bounded nonempty command id required")
            if not hasattr(connection, "consumed_experiment_ids"):
                connection.consumed_experiment_ids = set()
            if command_id in connection.consumed_experiment_ids:
                return []
            if len(connection.consumed_experiment_ids) >= 64:
                raise ValueError("Connection experiment id capacity reached")
            # Consume before validation/dispatch; a rejected nonce is not
            # silently retried on later packets or after a protocol reload.
            connection.consumed_experiment_ids.add(command_id)
            if command["command"] not in ("ClientRestart", "ClientSetHUD", "PawnAutonomous", "GameStateBeginPlay", "ControllerPlayerState", "PawnPlayerState", "CharacterInfoExport", "CharacterInfoName", "CharacterInfoGuid", "StatsComponentExport", "StatsGravity", "StatsSpeed"):
                raise ValueError("Only fixed HUD, possession, autonomy or GameState BeginPlay experiments are supported")
            expires = command["expires_at"]
            if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not 0 < expires-time.time() <= 30:
                raise ValueError("Command must expire within the next 30 seconds")
            pid, cache_path, actor_path = proof_paths(root, command["cache_snapshot"], command["actor_snapshot"])
            refs = getattr(connection, "actor_guids", {})
            if command["controller_guid"] != refs.get("controller") or command["pawn_guid"] != refs.get("pawn"):
                raise ValueError("Command GUIDs must equal this connection's emitted actor references")
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            actors = json.loads(actor_path.read_text(encoding="utf-8"))
            validate_current_client_proofs(pid, cache, actors)
            if actors.get("errors") or cache.get("status") != "runtime_cache_candidates_verified":
                raise ValueError("Actor/cache evidence did not validate cleanly")
            matches = actors.get("network_guid_actor_matches", [])
            controller = next((m["actor"] for m in matches if m.get("guid") == refs["controller"] and m["actor"].get("class") == "AoCPlayerControllerBP_C"), None)
            pawn = next((m["actor"] for m in matches if m.get("guid") == refs["pawn"] and m["actor"].get("class") == "PlayerPawn_C"), None)
            local_addresses = {p["player_controller"]["address"] for p in actors.get("local_players", []) if p.get("player_controller")}
            if controller is None or pawn is None or controller["address"] not in local_addresses:
                raise ValueError("Exact accepted local controller and pawn GUID proof required")
            if command["command"] in ("ClientRestart", "PawnAutonomous", "GameStateBeginPlay"):
                state = next((item for item in actors.get("controllers", []) if item.get("address") == controller["address"]), {})
                hud = state.get("hud") or {}
                if hud.get("class") != "BP_AOCHUD_C" or "AoCHUDBase" not in hud.get("ancestors", []):
                    raise ValueError("Possession requires fresh MyHUD proof for BP_AOCHUD_C inheriting AoCHUDBase; stage ClientSetHUD first")
            by_address = {entry["cache"]: entry for entry in cache["candidate_caches"]}
            current = next((entry for entry in by_address.values() if entry["class"] == "AoCPlayerControllerBP_C"), None)
            if current is None or current.get("normal_rpc_field_maximum") != 1032:
                raise ValueError("Verified controller cache maximum must be1032")
            field_max = current["normal_rpc_field_maximum"]
            controller_cache = current
            visited, restart, acknowledgement, set_hud = set(), None, None, None
            while current is not None:
                if current["cache"] in visited or not current.get("header_weak_class_matches") or not current.get("fields_base_matches"):
                    raise ValueError("Invalid verified cache inheritance chain")
                visited.add(current["cache"])
                restart = next((item for item in current["fields"] if item["name"] == "ClientRestart" and item["kind"] == "UFunction" and item["owner_class"] == "PlayerController"), None)
                if restart is not None:
                    acknowledgement = next((item for item in current["fields"] if item["name"] == "ServerAcknowledgePossession" and item["kind"] == "UFunction" and item["owner_class"] == "PlayerController"), None)
                    set_hud = next((item for item in current["fields"] if item["name"] == "ClientSetHUD" and item["kind"] == "UFunction" and item["owner_class"] == "PlayerController"), None)
                    break
                current = by_address.get(current.get("super_cache"))
            if restart is None or restart["field_net_index"] != 45:
                raise ValueError("Verified inherited ClientRestart field must be45")
            if acknowledgement is None or acknowledgement["field_net_index"] != 73:
                raise ValueError("Verified inherited ServerAcknowledgePossession field must be73")
            if command['command']=='CharacterInfoGuid':
                import sqlite3,importlib
                from . import character_info_component
                importlib.reload(character_info_component)
                from .character_info_component import validate_character_info_guid,encode_character_info_guid_content
                if 9 not in connection.channel_reliable or command['component_guid']!=refs.get('character_info') or getattr(connection,'character_guid_supplied',False):
                    raise ValueError('First identity update to retained accepted component required')
                expected={'appearance_snapshot':f'evidence/character_info_before_identity_{pid}.json',
                    'mapping_snapshot':f'evidence/character_info_mapping_{pid}.json',
                    'layout_snapshot':f'evidence/rep_layout_world_{pid}.json'}
                if any(command[k]!=v for k,v in expected.items()):
                    raise ValueError('Fixed same-PID component identity proofs required')
                appearance,mapping,layouts=[json.loads((root/name).read_text()) for name in expected.values()]
                validate_current_client_proofs(pid,appearance,mapping)
                validate_current_client_proofs(pid,layouts,actors)
                with sqlite3.connect(root/'data/lab.sqlite') as db:
                    identities=db.execute('SELECT id FROM characters').fetchall()
                if identities!=[(command['character_id'],)]:
                    raise ValueError('Identity must equal the single unambiguous own-server character')
                validate_character_info_guid(actors,appearance,mapping,layouts,refs['pawn'],refs['character_info'])
                payload,bits=encode_character_info_guid_content(refs['character_info'],command['character_id'])
                sequence=(connection.channel_reliable[9]+1)&1023
                packets=[self._send_bunches(connection,[{'channel':9,'channel_name':102,'reliable':True,
                    'reliable_sequence':sequence,'payload':payload,'payload_bits':bits}])]
                connection.character_guid_supplied=True
                self.event('character_info_guid_experiment',{'component_guid':refs['character_info'],
                    'character_id':command['character_id'],'wire_handles':[3,4,5,6],'movement_proved':False})
            elif command['command']=='CharacterInfoName':
                import sqlite3
                import importlib
                from . import character_info_component
                importlib.reload(character_info_component)
                from .character_info_component import validate_character_info_name,encode_character_info_name_content
                if 9 not in connection.channel_reliable or command['component_guid']!=refs.get('character_info') or getattr(connection,'character_name_supplied',False):
                    raise ValueError('First name update to retained accepted component required')
                expected={'appearance_snapshot':f'evidence/character_info_after_export_{pid}.json',
                    'mapping_snapshot':f'evidence/character_info_mapping_{pid}.json',
                    'layout_snapshot':f'evidence/rep_layout_world_{pid}.json'}
                if any(command[k]!=v for k,v in expected.items()):
                    raise ValueError('Fixed same-PID component name proofs required')
                appearance,mapping,layouts=[json.loads((root/name).read_text()) for name in expected.values()]
                validate_current_client_proofs(pid,appearance,mapping)
                validate_current_client_proofs(pid,layouts,actors)
                with sqlite3.connect(root/'data/lab.sqlite') as db:
                    names=db.execute('SELECT name FROM characters').fetchall()
                if names!=[(command['character_name'],)]:
                    raise ValueError('Name must equal the single unambiguous own-server character')
                validate_character_info_name(actors,appearance,mapping,layouts,refs['pawn'],refs['character_info'])
                payload,bits=encode_character_info_name_content(refs['character_info'],command['character_name'])
                sequence=(connection.channel_reliable[9]+1)&1023
                packets=[self._send_bunches(connection,[{'channel':9,'channel_name':102,'reliable':True,
                    'reliable_sequence':sequence,'payload':payload,'payload_bits':bits}])]
                connection.character_name_supplied=True
                self.event('character_info_name_experiment',{'component_guid':refs['character_info'],
                    'character_name':command['character_name'],'wire_handle':8,'movement_proved':False})
            elif command['command'] in ('StatsGravity','StatsSpeed'):
                from .stats_component import validate_gravity_update, encode_gravity_content, validate_speed_update, encode_speed_content
                is_speed = command['command'] == 'StatsSpeed'
                if refs.get('stats') != command['component_guid'] or not connection.possession_acknowledged or getattr(connection,'speed_stat_supplied' if is_speed else 'gravity_stat_supplied',False):
                    raise ValueError('First gravity update on the retained possessed stats component required')
                expected = {'mapping_snapshot':f'evidence/stats_mapping_{pid}.json',
                            'stats_cache_snapshot':f'evidence/stats_driver_net_cache_{pid}.json'}
                if any(command[k] != value for k,value in expected.items()):
                    raise ValueError('Fixed same-PID stat mapping/cache proofs required')
                mapping, stats_cache = [json.loads((root/path).read_text()) for path in expected.values()]
                validate_current_client_proofs(pid, mapping, stats_cache)
                (validate_speed_update if is_speed else validate_gravity_update)(mapping, stats_cache, refs['stats'])
                payload, bits = (encode_speed_content if is_speed else encode_gravity_content)(refs['stats'])
                sequence = (connection.channel_reliable[9]+1)&1023
                packets = [self._send_bunches(connection,[{'channel':9, 'channel_name':102,
                    'reliable':True, 'reliable_sequence':sequence, 'payload':payload, 'payload_bits':bits}])]
                setattr(connection, 'speed_stat_supplied' if is_speed else 'gravity_stat_supplied', True)
                self.event('speed_stat_experiment' if is_speed else 'gravity_stat_experiment', {'component_guid':refs['stats'],
                    'stat_guid':'0x6357c09a5679' if is_speed else '0x5429e5e8643f0018', 'value':1.659999966621399 if is_speed else 0.5, 'movement_proved':False})
            elif command['command']=='StatsComponentExport':
                from .stats_component import validate_stats_export, encode_stats_export, encode_stats_empty_content
                if 9 not in connection.channel_reliable or 'stats' in refs or not connection.possession_acknowledged:
                    raise ValueError('First stats export on a retained possessed pawn channel required')
                expected = f'evidence/stats_receiver_{pid}.json'
                if command['receiver_snapshot'] != expected:
                    raise ValueError('Fixed same-PID stats receiver proof required')
                receiver = json.loads((root/expected).read_text())
                validate_current_client_proofs(pid, actors, receiver)
                validate_stats_export(actors, receiver, refs['pawn'], command['component_guid'])
                export, export_bits = encode_stats_export(refs['pawn'], command['component_guid'])
                payload, bits = encode_stats_empty_content(command['component_guid'])
                sequence = (connection.channel_reliable[9]+1)&1023
                packets = [self._send_bunches(connection, [
                    {'channel':9, 'channel_name':102, 'reliable':True, 'reliable_sequence':sequence,
                     'exports':True, 'payload':export, 'payload_bits':export_bits},
                    {'channel':9, 'channel_name':102, 'reliable':True, 'reliable_sequence':(sequence+1)&1023,
                     'payload':payload, 'payload_bits':bits}])]
                refs['stats'] = dict(command['component_guid'])
                self.event('stats_component_export_experiment', {'pawn_guid':refs['pawn'],
                    'component_guid':refs['stats'], 'channel':9, 'stat_values_supplied':False})
            elif command['command']=='CharacterInfoExport':
                from .character_info_component import validate_character_info_export, encode_character_info_export, encode_character_info_empty_content
                if 9 not in connection.channel_reliable or 'character_info' in refs:
                    raise ValueError('Retained pawn channel and first component export required')
                expected={'appearance_snapshot':f'evidence/character_info_before_export_{pid}.json',
                    'receiver_snapshot':f'evidence/character_info_receiver_{pid}.json'}
                if any(command[k]!=v for k,v in expected.items()):
                    raise ValueError('Fixed same-PID component proofs required')
                appearance,receiver=[json.loads((root/name).read_text()) for name in expected.values()]
                validate_current_client_proofs(pid,appearance,receiver)
                validate_character_info_export(actors,appearance,receiver,refs['pawn'],command['component_guid'])
                export,export_bits=encode_character_info_export(refs['pawn'],command['component_guid'])
                payload,bits=encode_character_info_empty_content(command['component_guid'])
                sequence=(connection.channel_reliable[9]+1)&1023
                packets=[self._send_bunches(connection,[
                    {'channel':9,'channel_name':102,'reliable':True,'reliable_sequence':sequence,
                     'exports':True,'payload':export,'payload_bits':export_bits},
                    {'channel':9,'channel_name':102,'reliable':True,'reliable_sequence':(sequence+1)&1023,
                     'payload':payload,'payload_bits':bits}])]
                refs['character_info']=dict(command['component_guid'])
                self.event('character_info_export_experiment',{'pawn_guid':refs['pawn'],
                    'component_guid':refs['character_info'],'channel':9,'content_bits':bits,
                    'character_data_supplied':False,'load_complete_claimed':False})
            elif command["command"] == "PawnPlayerState":
                from .pawn_player_state import validate_pawn_player_state, encode_pawn_player_state_content
                if command['player_state_guid'] != refs.get('player_state') or not connection.possession_acknowledged or 9 not in connection.channel_reliable:
                    raise ValueError('Accepted possession and retained pawn/PlayerState references required')
                expected = {'layout_snapshot': f'evidence/rep_layout_world_{pid}.json',
                    'receiver_snapshot': f'evidence/pawn_player_state_receiver_{pid}.json'}
                if any(command[key] != value for key,value in expected.items()):
                    raise ValueError('Exact fixed same-PID pawn PlayerState proofs required')
                layouts, receiver = [json.loads((root/name).read_text()) for name in expected.values()]
                validate_current_client_proofs(pid, layouts, receiver)
                pawn_cache = next((x for x in by_address.values() if x['class'] == 'PlayerPawn_C'), None)
                if pawn_cache is None or not pawn_cache.get('header_weak_class_matches') or not pawn_cache.get('fields_base_matches'):
                    raise ValueError('Verified current pawn class cache required')
                validate_pawn_player_state(layouts, receiver, actors, pawn_cache, refs['pawn'], refs['player_state'])
                payload, bits = encode_pawn_player_state_content(refs['player_state'])
                sequence = (connection.channel_reliable[9]+1)&1023
                packets = [self._send_bunches(connection, [{'channel':9,'channel_name':102,
                    'reliable':True,'reliable_sequence':sequence,'payload':payload,'payload_bits':bits}])]
                self.event('pawn_player_state_experiment', {'pawn_guid':refs['pawn'],
                    'player_state_guid':refs['player_state'],'channel':9,'wire_handle':21,
                    'reliable_sequence':sequence,'movement_proved':False})
            elif command["command"] == "ControllerPlayerState":
                from .controller_player_state import validate_controller_player_state, encode_controller_player_state_content
                if command['player_state_guid'] != refs.get('player_state'):
                    raise ValueError('PlayerState GUID must equal this connection emitted actor')
                expected = {'layout_snapshot': f'evidence/rep_layout_world_{pid}.json',
                    'receiver_snapshot': f'evidence/controller_player_state_receiver_{pid}.json'}
                if any(command[key] != value for key, value in expected.items()):
                    raise ValueError('Exact fixed same-PID Controller PlayerState proof paths required')
                layouts, receiver = [json.loads((root/name).read_text()) for name in expected.values()]
                validate_current_client_proofs(pid, layouts, receiver)
                validate_controller_player_state(layouts, receiver, actors, controller_cache,
                    refs['controller'], refs['player_state'], receiver=receiver)
                payload, bits = encode_controller_player_state_content(refs['player_state'])
                sequence = (connection.channel_reliable.get(3, 0)+1)&1023
                packets = [self._send_bunches(connection, [{'channel': 3, 'channel_name': 102,
                    'reliable': True, 'reliable_sequence': sequence, 'payload': payload, 'payload_bits': bits}])]
                self.event('controller_player_state_experiment', {'controller_guid': refs['controller'],
                    'player_state_guid': refs['player_state'], 'channel': 3, 'wire_handle': 19,
                    'reliable_sequence': sequence, 'movement_proved': False,
                    'evidence': 'exact_reviewed_scalar_serializer_and_current_notification_chain'})
            elif command["command"] == "GameStateBeginPlay":
                from .game_state_begin_play import validate_game_state_begin_play
                if command["game_state_guid"] != refs.get("game_state"):
                    raise ValueError("GameState GUID must equal current retained emitted actor")
                accepted = next((m["actor"] for m in matches if m.get("guid") == refs["game_state"] and m["actor"].get("class") == "AoCGameStateBP_C"), None)
                if accepted is None:
                    raise ValueError("Exact accepted GameState GUID proof required")
                expected = {"layout_snapshot":f"evidence/rep_layout_world_{pid}.json",
                    "begin_play_snapshot":f"evidence/begin_play_serialization_{pid}.json",
                    "lifecycle_snapshot":f"evidence/world_lifecycle_prerequisites_{pid}.json"}
                if any(command[key] != name for key,name in expected.items()):
                    raise ValueError("Exact fixed same-PID GameState proof paths required")
                paths = [(root/name).resolve() for name in expected.values()]
                if any(path.parent != (root/"evidence").resolve() for path in paths):
                    raise ValueError("GameState evidence must remain inside fixed evidence directory")
                layouts, serializer, lifecycle = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
                validate_current_client_proofs(pid, layouts, serializer)
                validate_current_client_proofs(pid, lifecycle, actors)
                validate_game_state_begin_play(layouts, serializer, lifecycle, accepted, actors=actors)
                packets = self._game_state_begin_play(connection, proof_verified=True)
            elif command["command"] == "PawnAutonomous":
                from .pawn_role import validate_pawn_role_layout
                expected_layout = f"evidence/rep_layout_world_{pid}.json"
                expected_role = f"evidence/role_serialization_{pid}.json"
                if command["layout_snapshot"] != expected_layout or command["role_snapshot"] != expected_role:
                    raise ValueError("Exact fixed same-PID layout/role evidence paths required")
                paths = [(root/name).resolve() for name in (expected_layout, expected_role)]
                if any(path.parent != (root/"evidence").resolve() for path in paths):
                    raise ValueError("Role evidence must stay inside fixed evidence directory")
                layouts, role_proof = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
                validate_current_client_proofs(pid, layouts, role_proof)
                pawn_cache = next((item for item in by_address.values() if item["class"] == "PlayerPawn_C"), None)
                if pawn_cache is None or not pawn_cache.get("header_weak_class_matches") or not pawn_cache.get("fields_base_matches"):
                    raise ValueError("Exact verified pawn class cache required")
                validate_pawn_role_layout(layouts, role_proof, pawn_cache)
                state_pawn = state.get("pawn") or {}
                ack_pawn = state.get("acknowledged_pawn") or {}
                if state_pawn.get("address") != pawn["address"] or ack_pawn.get("address") != pawn["address"] or (state_pawn.get("controller") or {}).get("address") != controller["address"]:
                    raise ValueError("Fresh snapshot must prove exact local possessed pawn and controller backpointer")
                if state_pawn.get("network_roles", {}).get("Role") != 1 or state_pawn.get("network_roles", {}).get("RemoteRole") != 4:
                    raise ValueError("Role-only experiment requires observed prior pawn SimulatedProxy1/Authority4")
                packets = self._pawn_autonomous(connection, proof_verified=True)
                # Bind envelope recognition to the independently verified inherited cache.
                cursor, seen, move = pawn_cache, set(), None
                while cursor and cursor['cache'] not in seen:
                    seen.add(cursor['cache'])
                    if not cursor.get('header_weak_class_matches') or not cursor.get('fields_base_matches'):
                        break
                    move = next((field for field in cursor['fields'] if
                        field.get('name') == 'ServerMovePacked' and field.get('kind') == 'UFunction' and
                        field.get('owner_class') == 'Character' and field.get('field_net_index') == 44), None)
                    if move:
                        break
                    cursor = by_address.get(cursor.get('super_cache'))
                if move and pawn_cache.get('normal_rpc_field_maximum') == 198:
                    connection.pawn_movement_contract = {'pawn_guid': dict(refs['pawn']),
                        'field_max': 198, 'server_move_field': 44, 'cache_snapshot': command['cache_snapshot']}
            elif command["command"] == "ClientSetHUD":
                if set_hud is None or set_hud["field_net_index"] != 53:
                    raise ValueError("Verified inherited ClientSetHUD field must be53")
                packets = self._client_set_hud(connection, 53, field_max, cache_verified=True, actors_verified=True)
            else:
                packets = self._client_restart(connection, 45, field_max, cache_verified=True, actors_verified=True)
                connection.possession_ack_contract = {"field_index": acknowledgement["field_net_index"],
                    "field_max": field_max, "controller_guid": dict(refs["controller"]),
                    "pawn_guid": dict(refs["pawn"]), "cache_snapshot": command["cache_snapshot"]}
                connection.possession_acknowledged = False
            self.event("client_restart_experiment_consumed", {"id": command_id, "peer": str(peer),
                       "command": command["command"], "client_pid": pid, "evidence": "fresh_live_build_identity_cache_and_exact_actor_GUID_acceptance"})
            return packets
        except (ValueError, OSError, KeyError, TypeError, StopIteration, IndexError, struct.error) as exc:
            self.event("client_restart_experiment_rejected", {"id": command_id, "peer": str(peer), "reason": str(exc)})
            return []
