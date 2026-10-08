"""Scoped W/left-Shift IPC driver; the general MCP key allowlist stays unchanged."""
import sys
import time

from ashes_testing.bridge import InputGate, bounded_duration
from ashes_testing.telemetry import NativeTelemetry, Unavailable, WORKSPACE

sys.path.insert(0, str(WORKSPACE))
from lab.automation import AttachedWindowsDriver, Cancelled

KEY_INFO = {'w': (0x57, 0x57, 0x11), 'lshift': (0xA0, 0x10, 0x2A)}


def sprint_scope(lease, keys, duration):
    bounded_duration(duration)
    if keys not in (('w',), ('lshift', 'w')):
        raise Unavailable('Only W or left-Shift plus W comparison is supported')
    if (lease.get('test_phase') != 'sprint-comparison' or lease.get('allowed_keys') != list(keys) or
            lease.get('remaining_pulses') != 0 or not lease.get('pulse_reserved_at') or
            duration > lease.get('max_key_seconds', 0)):
        raise Unavailable('Exact separately released and reserved sprint-comparison pulse required')


class SprintDriver(AttachedWindowsDriver):
    def __init__(self, pid, adapter):
        self.virtual_held = []
        self.native = NativeTelemetry(pid)
        self.gate = InputGate(True)
        super().__init__(pid, adapter=adapter)

    def combo(self, keys, duration, cancel):
        sprint_scope(self.gate.verify(self.native.proof(), action='movement'), keys, duration)
        status = self.adapter.status()
        if status['build_id'] != 0x0c32ad42 or status['active'] or status['held']:
            raise Unavailable('Idle reviewed CPP Shift adapter required')
        with self.lock:
            try:
                if cancel.is_set():
                    raise Cancelled('Comparison cancelled before activation')
                self._activate_adapter()
                for key in keys:
                    if cancel.is_set():
                        raise Cancelled('Comparison cancelled before key down')
                    self.gate.verify(self.native.proof(), action='movement')
                    vk, message_vk, scan = KEY_INFO[key]
                    # Keep uncertain requests in cleanup ownership as well.
                    self.virtual_held.append(key)
                    self.adapter.set_key(vk, True)
                    self._post(0x100, message_vk, 1 | (scan << 16))
                deadline = time.monotonic() + duration
                while time.monotonic() < deadline:
                    self._validate()
                    sprint_scope(self.gate.verify(self.native.proof(), action='movement'), keys, duration)
                    if cancel.wait(min(.02, max(0, deadline - time.monotonic()))):
                        raise Cancelled('Sprint comparison cancelled')
            finally:
                self.release_all()

    def release_all(self):
        error = None
        with self.lock:
            had_keys = bool(self.virtual_held)
            for key in reversed(self.virtual_held):
                vk, message_vk, scan = KEY_INFO[key]
                try:
                    self.adapter.set_key(vk, False)
                    self._post(0x101, message_vk, 1 | (scan << 16) | (3 << 30), cleanup=True)
                except Exception as exc:
                    error = error or exc
            self.virtual_held.clear()
            try:
                if had_keys:
                    time.sleep(.2)  # Keep virtual released states while the game drains key-up messages.
                super().release_all()  # Deactivation also clears both Shift states/watchdog ownership.
            finally:
                if error:
                    raise error
