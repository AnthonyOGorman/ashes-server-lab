import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.protocol_proof import proof_paths, validate_current_client_proofs, EXPECTED_SHA256, stream_sha256


class ProofTests(unittest.TestCase):
    def test_stream_hash_works_without_file_digest_and_bounds_each_read(self):
        from io import BytesIO
        import hashlib
        source = b"verified-build"*200000
        class BoundedStream(BytesIO):
            def read(self, count):
                if not 0 < count <= 1024*1024:
                    raise AssertionError("Unbounded file read")
                return super().read(count)
        with patch.object(hashlib, "file_digest", create=True, side_effect=AttributeError("Python3.10")):
            self.assertEqual(stream_sha256(BoundedStream(source)), hashlib.sha256(source).hexdigest())
    def test_path_binding_allows_same_dynamic_pid_only_inside_evidence(self):
        root = Path(__file__).resolve().parents[1]
        pid, cache, actors = proof_paths(root, "evidence/driver_net_cache_world_73000.json", "evidence/player_state_world_73000.json")
        self.assertEqual(pid, 73000)
        self.assertEqual(cache.parent, (root/"evidence").resolve())
        for cache_name, actor_name in (("evidence/../driver_net_cache_world_73000.json", "evidence/player_state_world_73000.json"),
                                      ("evidence/driver_net_cache_world_73000.json", "evidence/player_state_world_73001.json"),
                                      ("evidence/driver_net_cache_world_0.json", "evidence/player_state_world_0.json")):
            with self.assertRaises(ValueError):
                proof_paths(root, cache_name, actor_name)

    def test_pid_reuse_wrong_build_and_stale_snapshots_cannot_dispatch(self):
        proof = {"pid": 73000, "exe": "exact-verified-client", "sha256": EXPECTED_SHA256,
                 "process_created_filetime": 12345, "observed_at": time.time()}
        snapshot = {"pid": 73000, "client_proof": dict(proof)}
        with patch("tools.protocol_proof.client_proof", return_value=proof):
            self.assertEqual(validate_current_client_proofs(73000, snapshot, snapshot), proof)
            for key, value in (("pid", 73001), ("exe", "other-client"), ("sha256", "0"*64),
                               ("process_created_filetime", 9999), ("observed_at", time.time()-181)):
                bad = {"pid": 73000, "client_proof": {**proof, key: value}}
                with self.assertRaises(ValueError):
                    validate_current_client_proofs(73000, snapshot, bad)
        with patch("tools.protocol_proof.client_proof", side_effect=ValueError("client exited")):
            with self.assertRaises(ValueError):
                validate_current_client_proofs(73000, snapshot, snapshot)
