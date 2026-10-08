import copy
import struct
import unittest
from unittest.mock import patch

from tools.probe_movement import (EvidenceError, GUID_EVIDENCE,
                                  capture_snapshot, compare_snapshots,
                                  sample_from_inspection)


def identity(address, index, name, class_name):
    return {"address": hex(address), "object_index": index, "name": name,
            "class": class_name, "outer_address": "0x20000"}


def report(position=(100., 200., 300.)):
    controller = identity(0x30000, 30, "Controller_1", "AoCPlayerControllerBP_C")
    pawn = identity(0x40000, 40, "Pawn_1", "PlayerPawn_C")
    pawn["controller"] = copy.deepcopy(controller)
    root = identity(0x50000, 50, "Capsule_1", "CapsuleComponent")
    root.update(attach_parent=None, relative_location=list(position), unattached_location=list(position))
    pawn["root_component"] = root
    controller.update(pawn=pawn, acknowledged_pawn={key: pawn[key] for key in
                      ("address", "object_index", "name", "class", "outer_address")},
                      acknowledges_same_pawn=True, pawn_points_back_to_controller=True)
    local = identity(0x60000, 60, "LocalPlayer_1", "LocalPlayer")
    local["player_controller"] = {key: controller[key] for key in
                                 ("address", "object_index", "name", "class", "outer_address")}
    matches = []
    for actor, object_id, serial in ((controller, 1234, 789), (pawn, 5678, 987)):
        matches.append({"actor": copy.deepcopy(actor), "guid": {"object_id": f"0x{object_id:016x}",
                       "server_id": 1, "randomizer": 42}, "guid_hex": struct.pack("<QII", object_id, 1, 42).hex(),
                       "weak_object_index": actor["object_index"], "weak_object_serial": serial,
                       "evidence": GUID_EVIDENCE})
    return {"pid": 999, "exe": r"E:\exact\client.exe", "errors": [],
            "local_players": [local], "controllers": [controller],
            "network_guid_actor_matches": matches,
            "reflection_validation": {"name_pool_sentinel": "None", "validated_object_indices": 50}}


def sample(position=(100., 200., 300.), start=1_000_000_000, lifetime=123):
    return sample_from_inspection(report(position), lifetime, start, start+10_000_000)


class MovementEvidenceTests(unittest.TestCase):
    def test_same_pawn_horizontal_change_is_observed_but_not_walking(self):
        result = compare_snapshots(sample(), sample((103., 204., 300.), 2_000_000_000))
        self.assertEqual(result["status"], "compared")
        self.assertTrue(result["possession_proven"])
        self.assertTrue(result["position_changed"])
        self.assertEqual(result["delta_cm"], [3., 4., 0.])
        self.assertEqual(result["distance_cm"], 5.)
        self.assertFalse(result["server_authoritative_walking_verified"])

    def test_vertical_fall_never_proves_walking(self):
        result = compare_snapshots(sample(), sample((100., 200., -1000.), 2_000_000_000))
        self.assertTrue(result["position_changed"])
        self.assertEqual(result["horizontal_distance_cm"], 0.)
        self.assertEqual(result["vertical_delta_cm"], -1300.)
        self.assertFalse(result["server_authoritative_walking_verified"])

    def test_stationary_and_small_jitter_are_not_changed(self):
        for position in ((100., 200., 300.), (100.001, 200., 300.)):
            with self.subTest(position=position):
                result = compare_snapshots(sample(), sample(position, 2_000_000_000))
                self.assertEqual(result["status"], "compared")
                self.assertFalse(result["position_changed"])

    def test_incomplete_possession_is_refused(self):
        for field in ("acknowledges_same_pawn", "pawn_points_back_to_controller"):
            source = report()
            source["controllers"][0][field] = False
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                sample_from_inspection(source, 123, 1, 2)

    def test_ack_identity_and_pawn_back_pointer_must_agree(self):
        for target in ("ack", "back"):
            source = report()
            obj = (source["controllers"][0]["acknowledged_pawn"] if target == "ack"
                   else source["controllers"][0]["pawn"]["controller"])
            obj["object_index"] += 1
            with self.subTest(target=target), self.assertRaises(EvidenceError):
                sample_from_inspection(source, 123, 1, 2)

    def test_missing_duplicate_or_invalid_guid_proof_is_refused(self):
        for damage in ("missing", "duplicate", "serial", "key", "provenance"):
            source = report()
            rows = source["network_guid_actor_matches"]
            if damage == "missing":
                rows.pop()
            elif damage == "duplicate":
                rows.append(copy.deepcopy(rows[-1]))
            elif damage == "serial":
                rows[-1]["weak_object_serial"] = 0
            elif damage == "key":
                rows[-1]["guid_hex"] = "00" * 16
            else:
                rows[-1]["evidence"] = "guessed"
            with self.subTest(damage=damage), self.assertRaises(EvidenceError):
                sample_from_inspection(source, 123, 1, 2)

    def test_attached_or_nonfinite_root_is_refused(self):
        for damage in ("attached", "nan", "infinite", "missing", "bool"):
            source = report()
            root = source["controllers"][0]["pawn"]["root_component"]
            if damage == "attached":
                root["attach_parent"] = identity(0x70000, 70, "Parent", "SceneComponent")
            elif damage == "missing":
                root.pop("unattached_location")
            else:
                root["unattached_location"][0] = {"nan": float("nan"), "infinite": float("inf"), "bool": True}[damage]
            with self.subTest(damage=damage), self.assertRaises(EvidenceError):
                sample_from_inspection(source, 123, 1, 2)

    def test_inspector_errors_and_ambiguous_local_players_are_refused(self):
        for damage in ("error", "multiple", "validation"):
            source = report()
            if damage == "error":
                source["errors"].append({"error": "Unreadable actor"})
            elif damage == "multiple":
                source["local_players"].append(copy.deepcopy(source["local_players"][0]))
            else:
                source["reflection_validation"] = {}
            with self.subTest(damage=damage), self.assertRaises(EvidenceError):
                sample_from_inspection(source, 123, 1, 2)

    def test_pid_lifetime_root_and_guid_swaps_block_comparison(self):
        for damage in ("pid", "lifetime", "root", "guid", "serial"):
            before = sample()
            source = report((101., 200., 300.))
            if damage == "pid":
                source["pid"] = 1000
            elif damage == "root":
                source["controllers"][0]["pawn"]["root_component"]["address"] = "0x51000"
            elif damage == "guid":
                row = source["network_guid_actor_matches"][-1]
                row["guid"]["randomizer"] = 43
                row["guid_hex"] = struct.pack("<QII", 5678, 1, 43).hex()
            elif damage == "serial":
                source["network_guid_actor_matches"][-1]["weak_object_serial"] += 1
            after = sample_from_inspection(source, 456 if damage == "lifetime" else 123,
                                           2_000_000_000, 2_010_000_000)
            with self.subTest(damage=damage):
                result = compare_snapshots(before, after)
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["position_changed"])

    def test_intervals_and_mutated_proof_are_refused(self):
        for after in (sample(start=1_005_000_000), sample(start=500_000_000),
                      sample(start=200_000_000_000)):
            self.assertEqual(compare_snapshots(sample(), after)["status"], "blocked")
        after = sample(start=2_000_000_000)
        after["position"][0] += 100
        self.assertEqual(compare_snapshots(sample(), after)["status"], "blocked")

    def test_crashed_process_returns_blocked_not_success(self):
        with patch("tools.probe_movement._process_created_filetime", side_effect=EvidenceError("Process has exited")):
            result = capture_snapshot(999)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["possession_proven"])
        self.assertFalse(result["server_authoritative_walking_verified"])


if __name__ == "__main__":
    unittest.main()
