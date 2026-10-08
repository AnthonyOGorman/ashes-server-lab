from __future__ import annotations

import json
import math
import threading
import time
import uuid
from pathlib import Path

from .telemetry import NativeTelemetry, ServerTelemetry, Unavailable, WORKSPACE

HOME = WORKSPACE / 'client-testing'
ALLOWED_KEYS = frozenset(('w', 'a', 's', 'd', 'space'))


def bounded_duration(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not .05 <= value <= 2:
        raise ValueError('Key duration must be finite and between 0.05 and 2 seconds')
    return value


def displacement(before, after):
    for key in ('pawn', 'root', 'movement_component'):
        if before[key] != after[key]:
            raise Unavailable('Pawn or components changed; positions cannot be compared')
    if not NativeTelemetry.same_process(before['client_proof'], after['client_proof']):
        raise Unavailable('Client lifetime changed during comparison')
    delta = [b - a for a, b in zip(before['position_cm'], after['position_cm'])]
    return {'delta_cm': delta, 'horizontal_cm': math.hypot(*delta[:2]),
            'vertical_cm': delta[2], 'claim': 'observed displacement; causality and jitter-free walking not established'}


class InputGate:
    def __init__(self, enabled=False, path=None):
        self.enabled = enabled
        self.path = path or HOME / 'session-access.json'

    def verify(self, proof, action=None, key=None, duration=None):
        if not self.enabled:
            raise Unavailable('Bridge is in observation mode; input was not enabled at startup')
        lease = json.loads(self.path.read_text(encoding='utf-8'))
        now = time.time()
        if lease.get('mode') != 'client-testing-exclusive' or not lease.get('coordinated_window'):
            raise Unavailable('Server developer has not released a coordinated testing window')
        if lease.get('owner_thread') != '01a116ae-2ec4-7de0-b563-31251b0c4533':
            raise Unavailable('Testing window belongs to another chat')
        expires = lease.get('expires_at', 0)
        if not isinstance(expires, (int, float)) or not 0 < expires - now <= 900:
            raise Unavailable('Testing window expired or exceeds the 15-minute limit')
        if any(lease.get(k) != proof[k] for k in ('pid', 'process_created_filetime')):
            raise Unavailable('Testing window belongs to another process lifetime')
        if 'allowed_actions' in lease:
            allowed = lease['allowed_actions']
            if not isinstance(allowed, list) or not all(isinstance(k, str) and k in
                    ('adapter-setup', 'ui-entry', 'movement') for k in allowed):
                raise Unavailable('Testing window has an invalid action scope')
            if action is not None and action not in allowed:
                raise Unavailable('This action is outside the coordinated testing window scope')
        if action == 'movement' and key is not None:
            if 'allowed_keys' in lease and (not isinstance(lease['allowed_keys'], list) or
                    any(k not in ALLOWED_KEYS for k in lease['allowed_keys']) or key not in lease['allowed_keys']):
                raise Unavailable('This movement key is outside the released window')
            if 'max_key_seconds' in lease:
                maximum = lease['max_key_seconds']
                if (isinstance(maximum, bool) or not isinstance(maximum, (int, float)) or
                        not math.isfinite(maximum) or maximum <= 0 or duration is None or duration > maximum):
                    raise Unavailable('Key duration exceeds the released window limit')
            if 'remaining_pulses' in lease and (type(lease['remaining_pulses']) is not int or lease['remaining_pulses'] <= 0):
                raise Unavailable('Released movement pulse has already been reserved or completed')
        return lease


class Bridge:
    def __init__(self, pid=None, enable_input=False, native=None, server=None, driver_factory=None, output=None, gate=None):
        self.native = native or NativeTelemetry(pid)
        self.server = server or ServerTelemetry()
        self.gate = gate or InputGate(enable_input)
        self.output = output or HOME / 'runs'
        self.driver_factory = driver_factory
        self.lock = threading.RLock()
        self.cancel = threading.Event()

    def record(self, kind, value):
        self.output.mkdir(parents=True, exist_ok=True)
        path = self.output / (kind + '-' + uuid.uuid4().hex + '.json')
        path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
        return {**value, 'evidence_path': str(path)}

    def _server(self, kind):
        try:
            return self.server.get(kind)
        except Exception as exc:
            return {'source': 'server_observation', 'unavailable': str(exc)}

    def get_status(self):
        return {'input_enabled': self.gate.enabled, 'session_access': json.loads((HOME / 'session-access.json').read_text()),
                'ue4ss': 'staged dependency; live compatibility not certified',
                'scope': 'client-testing only; server telemetry uses GET only',
                'server': self._server('state')}

    def get_player_state(self):
        with self.lock:
            return self.record('player', self.native.sample())

    def get_world_state(self):
        with self.lock:
            sample = self.native.sample()
            return self.record('world', {'client_proof': sample['client_proof'], 'observed_at': sample['observed_at'],
                                        'client': sample['world'], 'server': self._server('world'),
                                        'connections': self._server('connections')})

    def _driver(self, attached=False):
        pid = self.native.proof()['pid']
        if self.driver_factory:
            return self.driver_factory(pid, attached)
        if str(WORKSPACE) not in __import__('sys').path:
            __import__('sys').path.insert(0, str(WORKSPACE))
        from lab.automation import BackgroundWindowsDriver, AttachedWindowsDriver
        if not attached:
            return BackgroundWindowsDriver(pid)
        from .input import resident_adapter
        return AttachedWindowsDriver(pid, adapter=resident_adapter(pid))

    def capture_screen(self):
        with self.lock:
            before = self.native.proof()
            self.output.mkdir(parents=True, exist_ok=True)
            path = self.output / ('screen-' + uuid.uuid4().hex + '.png')
            result = self._driver().screenshot(path)
            after = self.native.proof()
            if not NativeTelemetry.same_process(before, after):
                raise Unavailable('Client lifetime changed during capture')
            return self.record('capture', {**result, 'client_proof': after, 'observed_at': time.time()})

    def _press(self, key, duration):
        if key not in ALLOWED_KEYS:
            raise ValueError('Only WASD and space are available through this bridge')
        bounded_duration(duration)
        if self.cancel.is_set():
            raise Unavailable('Action was cancelled before input')
        self.gate.verify(self.native.proof(), action='movement', key=key, duration=duration)
        before = self.native.sample()
        self.gate.verify(before['client_proof'], action='movement', key=key, duration=duration)
        driver = self._driver(attached=True)
        try:
            driver.key(key, duration, self.cancel)
        finally:
            driver.release_all()
        after = self.native.sample()
        return {'key': key, 'duration': duration, 'before': before, 'after': after,
                'comparison': displacement(before, after), 'input_proof': driver.last_input_proof,
                'server': self._server('world'), 'events': self._server('events')}

    def press_key(self, key, duration=.5, cancel=None):
        with self.lock:
            self.cancel = cancel if cancel is not None else threading.Event()
            try:
                return self.record('input', self._press(key, duration))
            except Exception as exc:
                self.record('input-error', {'key': key, 'duration': duration, 'error': str(exc), 'observed_at': time.time()})
                raise

    def run_scenario(self, steps, min_horizontal_cm=5.0, max_vertical_cm=50.0, cancel=None):
        if not isinstance(steps, list) or not 1 <= len(steps) <= 10:
            raise ValueError('Scenario must contain between 1 and 10 key steps')
        for step in steps:
            if not isinstance(step, dict) or set(step) != {'key', 'duration'} or step['key'] not in ALLOWED_KEYS:
                raise ValueError('Every step must contain only an allowlisted key and duration')
            bounded_duration(step['duration'])
        if sum(step['duration'] for step in steps) > 10:
            raise ValueError('Scenario total key duration exceeds 10 seconds')
        for value in (min_horizontal_cm, max_vertical_cm):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 10000:
                raise ValueError('Displacement thresholds must be finite, positive and at most 10000 cm')
        with self.lock:
            self.cancel = cancel if cancel is not None else threading.Event()
            results = []
            try:
                if self.cancel.is_set():
                    raise Unavailable('Scenario cancelled before input')
                self.gate.verify(self.native.proof(), action='movement')
                screen_before = self.capture_screen()
                first = self.native.sample()
                for step in steps:
                    if self.cancel.is_set():
                        raise Unavailable('Scenario cancelled')
                    results.append(self._press(**step))
                last = self.native.sample()
                comparison = displacement(first, last)
                assertions = {'horizontal_displacement': comparison['horizontal_cm'] >= min_horizontal_cm,
                              'vertical_displacement_within_limit': abs(comparison['vertical_cm']) <= max_vertical_cm}
                return self.record('scenario', {'status': 'passed' if all(assertions.values()) else 'failed',
                    'assertion_scope': 'native net displacement only; server agreement, collision and replay not certified',
                    'thresholds': {'min_horizontal_cm': min_horizontal_cm, 'max_vertical_cm': max_vertical_cm},
                    'assertions': assertions, 'comparison': comparison, 'steps': results,
                    'before': screen_before, 'after': self.capture_screen(), 'observed_at': time.time()})
            except Exception as exc:
                return self.record('scenario', {'status': 'blocked', 'error': str(exc), 'steps': results,
                                                'observed_at': time.time()})

    def cancel_test(self):
        self.cancel.set()
        return {'cancellation_requested': True, 'cleanup': 'Active action releases keys in its finally block'}
