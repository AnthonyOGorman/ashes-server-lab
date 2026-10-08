import hashlib
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lab import terrain_movement_experiment as experiment
from lab import static_cache_extension
from lab.terrain_movement import TerrainMovement
from tests.test_static_collision import terrain


class CollisionReloadTests(unittest.TestCase):
    def test_new_geometry_keeps_position_velocity_and_clock_budget(self):
        self.exercise(False)

    def test_changed_collision_source_cannot_replace_retained_geometry(self):
        self.exercise(True)

    def exercise(self, tamper):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'evidence').mkdir()
            source=root/'evidence/collision_123.json'
            transform={'rotation':[0,0,0,1],'translation':[0,0,0],'scale':[1,1,1]}
            source.write_text(json.dumps({'components':[{'identity':{'address':'mesh'},
                'asset':'asset','instances':[],'native_component_transform':transform,
                'response':{'collision_enabled':3,'pawn_response':2}}],
                'assets':{'asset':{'collision_trace_flag':1,'shapes':[{'type':'KBoxElem',
                    'Center':[150,150,20],'Rotation':[0,0,0],'X':20,'Y':20,'Z':40}]}}}))
            config=dict(mode='connection-landscape-locomotion-v1',id='profile',peer=['127.0.0.1',1234],
                connection_id='current',pawn_guid={'pawn':1},pid=123,expires_at=0,
                cache_snapshot='unused',actor_snapshot='unused',terrain_manifest='unused',
                terrain_sha256='unused',spawn=[50,50,12],stats_mapping_snapshot='unused',
                static_collision_snapshot='evidence/collision_123.json',
                static_collision_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
            profile=root/'profile.json';profile.write_text(json.dumps(config))
            state=TerrainMovement([terrain()],[50,50,12],half_height=10,radius=2)
            state.timestamp=42;state.time_budget=.037;state.jump_pressed=True
            state.velocity=[12,3,-4]
            connection=SimpleNamespace(connection_id='current',phase='joined',
                actor_guids={'pawn':{'pawn':1}},possession_acknowledged=True,
                terrain_experiment_id='profile',terrain_experiment_config=config,
                terrain_experiment=state)
            if tamper:source.write_text('{}')
            with patch.object(experiment,'ROOT',root),patch.object(experiment,'PROFILE',profile),\
                 patch.object(static_cache_extension,'ROOT',root):
                self.assertIs(experiment.initialize(connection,('127.0.0.1',1234)),state)
                self.assertEqual(state.static_meshes,[])  # Old cache remains active during preparation.
                deadline=time.monotonic()+3
                while static_cache_extension._retaining and time.monotonic()<deadline:
                    time.sleep(.01)
                self.assertFalse(static_cache_extension._retaining)
                if tamper:
                    with self.assertRaisesRegex(ValueError,'hash mismatch'):
                        experiment.initialize(connection,('127.0.0.1',1234))
                    self.assertEqual(state.static_meshes,[])
                else:
                    self.assertIs(experiment.initialize(connection,('127.0.0.1',1234)),state)
                    self.assertEqual(len(state.static_meshes),1)
            self.assertEqual(state.position,[50,50,12]);self.assertEqual(state.velocity,[12,3,-4])
            self.assertEqual(state.timestamp,42);self.assertEqual(state.time_budget,.037)
            self.assertTrue(state.jump_pressed)
