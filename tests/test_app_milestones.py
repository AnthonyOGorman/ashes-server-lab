import json
import threading
import unittest
from unittest.mock import patch, Mock
from pathlib import Path

from lab.app import Lab


class RecordingStore:
    def __init__(self):
        self.events = []

    def execute(self, sql, values):
        if sql.startswith('INSERT INTO events'):
            self.events.append({'ts':values[0], 'run_id':values[1], 'kind':values[2],
                                'detail':json.loads(values[3])})


class MilestoneTests(unittest.TestCase):
    def setUp(self):
        # Event-state tests need no services, client process, disk database or input.
        self.lab = Lab.__new__(Lab)
        self.lab.lock = threading.RLock()
        self.lab.store = RecordingStore()
        self.lab.run_id = 'session'
        self.lab.reset_milestones()

    def emit(self, timestamp, kind, detail='proof'):
        with patch('lab.app.time.time', return_value=timestamp):
            self.lab.event(kind, detail)

    def test_world_entry_refused_before_any_input_when_connection_is_active(self):
        self.emit(10, 'udp_handshake', {'connection_id':'current'})
        self.lab.client = Mock()
        self.lab.client.poll.return_value = None
        self.lab.runner = None
        self.lab.scenario_path = Path(__file__).resolve().parents[1] / 'config/scenarios/character-selection-world-entry-1280.json'
        self.lab.driver_for = Mock(side_effect=AssertionError('No input driver may be activated'))
        with self.assertRaisesRegex(ValueError, 'already in a world'):
            self.lab.run_test('walk', 'attached')
        self.lab.driver_for.assert_not_called()

    def test_initialization_errors_preserve_startup_context_without_claiming_a_cause(self):
        startup = {'category':'LogIntrepidEOS', 'severity':'Error', 'message':'Both SandboxId and DeploymentId must be a valid value to run EOS: EMPTY EMPTY'}
        self.lab.observe_initialization_failure(json.dumps(startup))
        self.emit(10, 'udp_handshake', {'connection_id':'current'})
        self.lab.observe_initialization_failure(json.dumps({'category':'LogIntrepidEOS', 'severity':'Error', 'message':'EACExitGame: '}))
        self.lab.observe_initialization_failure(json.dumps({'category':'LogAoC_Game', 'severity':'Error', 'message':'Custom Failure: '}))
        self.assertEqual(len(self.lab.initialization_failures), 3)
        self.assertEqual(self.lab.initialization_failures[0]['message'], startup['message'])
        self.assertEqual(self.lab.initialization_failure['connection_id'], 'current')
        self.assertFalse(self.lab.initialization_failure['cause_verified'])
        self.assertTrue(self.lab.world_active)
        self.lab.observe_initialization_failure('invalid json')
        self.lab.observe_initialization_failure(json.dumps({'category':'LogUObjectGlobals', 'severity':'Error', 'message':'EACExitGame: '}))
        self.assertEqual(len(self.lab.initialization_failures), 3)
        self.lab.reset_milestones()
        self.assertEqual(self.lab.initialization_failures, [])

    def test_fresh_query_rejects_old_evidence_without_losing_default_reuse(self):
        self.emit(10, 'udp_handshake', {'connection_id':'first'})
        self.emit(12, 'welcome')
        self.assertTrue(self.lab.has_milestone('welcome'))
        self.assertTrue(self.lab.has_milestone('welcome', since=12))
        self.assertFalse(self.lab.has_milestone('welcome', since=13))
        self.assertFalse(self.lab.has_milestone('unknown', since=0))

    def test_fresh_handshake_clears_world_evidence_and_preserves_login(self):
        self.emit(1, 'authentication')
        self.emit(2, 'lobby')
        self.emit(3, 'udp_handshake', {'connection_id':'first'})
        for name in ('welcome','world_loaded','player_spawned','movement'):
            self.emit(4, name)
        self.emit(20, 'udp_handshake', {'connection_id':'second','replaces_existing':True})
        self.assertEqual(self.lab.world_epoch, 2)
        self.assertTrue(self.lab.has_milestone('authentication'))
        self.assertTrue(self.lab.has_milestone('lobby'))
        self.assertTrue(self.lab.has_milestone('udp_handshake', since=20))
        for name in ('welcome','world_loaded','player_spawned','movement'):
            self.assertFalse(self.lab.has_milestone(name))
            self.assertIsNone(self.lab.milestones[name]['observed_at'])
        self.emit(21, 'welcome')
        self.assertTrue(self.lab.has_milestone('welcome', since=20))
        self.assertEqual(self.lab.milestones['welcome']['world_epoch'], 2)

    def test_duplicate_handshake_cannot_refresh_or_clear_current_world(self):
        self.emit(10, 'udp_handshake', {'connection_id':'first'})
        self.emit(11, 'world_loaded')
        self.emit(20, 'udp_handshake', {'connection_id':'first'})
        self.assertEqual(self.lab.world_epoch, 1)
        self.assertTrue(self.lab.has_milestone('world_loaded'))
        self.assertFalse(self.lab.has_milestone('udp_handshake', since=15))
        self.assertFalse(self.lab.store.events[-1]['detail']['accepted'])

    def test_close_and_late_evidence_cannot_resurrect_world(self):
        self.emit(10, 'udp_handshake', {'connection_id':'first'})
        self.emit(11, 'world_loaded')
        self.emit(12, 'udp_connection_closed', {'connection_id':'first'})
        self.assertFalse(self.lab.world_active)
        self.assertFalse(self.lab.has_milestone('udp_handshake'))
        self.emit(13, 'welcome')
        self.assertFalse(self.lab.has_milestone('welcome'))
        self.assertFalse(self.lab.store.events[-1]['detail']['accepted'])
        self.emit(14, 'udp_handshake', {'connection_id':'second'})
        self.emit(15, 'welcome')
        self.assertTrue(self.lab.has_milestone('welcome'))

    def test_prior_connection_messages_cannot_clear_or_pass_new_world(self):
        self.emit(10, 'udp_handshake', {'connection_id':'first'})
        self.emit(20, 'udp_handshake', {'connection_id':'second'})
        self.emit(21, 'udp_connection_closed', {'connection_id':'first'})
        self.assertTrue(self.lab.world_active)
        self.emit(22, 'player_spawned', {'connection_id':'first'})
        self.assertFalse(self.lab.has_milestone('player_spawned'))
        self.emit(23, 'player_spawned', {'connection_id':'second'})
        self.assertTrue(self.lab.has_milestone('player_spawned', since=20))
        evidence = self.lab.store.events[-1]
        self.assertEqual(evidence['ts'], 23)
        self.assertEqual(evidence['detail']['observed_at'], 23)
        self.assertEqual(evidence['detail']['connection_id'], 'second')
        self.assertEqual(evidence['detail']['world_epoch'], 2)

    def test_confirmed_lobby_browse_clears_world_once_without_clearing_login(self):
        self.emit(1, 'authentication')
        self.emit(2, 'lobby')
        self.emit(10, 'udp_handshake', {'connection_id':'first'})
        self.emit(11, 'world_loaded')
        self.lab.observe_lobby_browse('LoadMap: /Game/Levels/Character_Login/Character_Lobby')
        self.assertTrue(self.lab.world_active)
        line = '{"category":"LogNet","message":"Browse: /Game/Levels/Character_Login/Character_Lobby"}'
        with patch('lab.app.time.time', return_value=12):
            self.lab.observe_lobby_browse(line)
        self.assertFalse(self.lab.world_active)
        self.assertFalse(self.lab.has_milestone('world_loaded'))
        self.assertTrue(self.lab.has_milestone('authentication'))
        self.assertTrue(self.lab.has_milestone('lobby'))
        evidence = self.lab.store.events[-1]
        self.assertEqual(evidence['kind'], 'world_return_detected')
        self.assertEqual(evidence['detail']['connection_id'], 'first')
        count = len(self.lab.store.events)
        self.lab.observe_lobby_browse(line)
        self.assertEqual(len(self.lab.store.events), count)


if __name__ == '__main__':
    unittest.main()
