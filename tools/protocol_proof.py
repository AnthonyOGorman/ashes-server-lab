"""Read-only process identity and bounded freshness for local protocol tests."""
import ctypes
from ctypes import wintypes
import hashlib
from pathlib import Path
import re
import time

EXPECTED_SHA256 = "4f1cd43ceeb89190f048734efd4d63152b9f8e11fa31fc41093b0d90f4a1cd43"
EXPECTED_EXE = Path(r"E:\Games\Steam Library\steamapps\common\Ashes of Creation\Game\AOC\Binaries\Win64\AOCClient-Win64-Shipping.exe")
_digest_cache = {}


def stream_sha256(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024*1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def live_identity(pid):
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Positive explicit client PID required")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    handle = kernel.OpenProcess(0x1000, False, pid)  # query only; no memory write or invocation
    if not handle:
        raise ValueError("Current client cannot be opened for identity verification")
    try:
        code = wintypes.DWORD()
        path, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        stamps = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
            raise ValueError("Verified client has exited")
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)) or Path(path.value).resolve() != EXPECTED_EXE.resolve():
            raise ValueError("Client executable path does not match the verified build")
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(stamp) for stamp in stamps)):
            raise ValueError("Cannot verify client process creation time")
        return {"pid": pid, "exe": str(EXPECTED_EXE),
                "process_created_filetime": (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime}
    finally:
        kernel.CloseHandle(handle)


def client_proof(pid):
    identity = live_identity(pid)
    stat = EXPECTED_EXE.stat()
    signature = (stat.st_mtime_ns, stat.st_size)
    digest = _digest_cache.get(signature)
    if digest is None:
        with EXPECTED_EXE.open("rb") as stream:
            digest = stream_sha256(stream)
        _digest_cache[signature] = digest
    if digest != EXPECTED_SHA256:
        raise ValueError("Client executable SHA256 does not match the verified protocol build")
    return {**identity, "sha256": digest, "observed_at": time.time()}


def proof_paths(root, cache_name, actor_name):
    """Only fixed local evidence basenames with a matching explicit PID."""
    cache = re.fullmatch(r"evidence/driver_net_cache_world_([1-9][0-9]{0,9})\.json", cache_name or "")
    actor = re.fullmatch(r"evidence/player_state_world_([1-9][0-9]{0,9})\.json", actor_name or "")
    if cache is None or actor is None or cache[1] != actor[1]:
        raise ValueError("Matching PID-suffixed cache/actor evidence paths required")
    evidence = (root/"evidence").resolve()
    paths = [(root/name).resolve() for name in (cache_name, actor_name)]
    if any(path.parent != evidence for path in paths):
        raise ValueError("Evidence must stay in the fixed local evidence directory")
    return int(cache[1]), *paths


def validate_current_client_proofs(pid, cache, actors):
    live = client_proof(pid)
    for snapshot in (cache, actors):
        proof = snapshot.get("client_proof", {})
        if snapshot.get("pid") != pid or any(proof.get(key) != live[key] for key in ("pid", "exe", "sha256", "process_created_filetime")):
            raise ValueError("Snapshots and live client must have identical build/PID/creation identity")
        observed = proof.get("observed_at")
        if isinstance(observed, bool) or not isinstance(observed, (float, int)) or not 0 <= time.time()-observed <= 180:
            raise ValueError("Both current-client proof snapshots must be at most180 seconds old")
    return live
