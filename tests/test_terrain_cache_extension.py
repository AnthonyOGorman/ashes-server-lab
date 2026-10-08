import copy
import struct
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lab.terrain import Heightfield
from lab.terrain_movement import TerrainMovement
from lab.terrain_cache_extension import extend_tiles
from lab import terrain_cache_extension as extension
from tests.test_static_collision import terrain


class TerrainCacheExtensionTests(unittest.TestCase):
    def test_extension_preserves_airborne_physics_and_clock(self):
        state = TerrainMovement([terrain()], [50, 50, 12], half_height=10, radius=2, floor_clearance=2)
        state.position = [350, 50, 80]
        state.velocity = [0, 0, -50]
        state.mode = 3
        state.timestamp = 72.3
        state.wall_observed = 200
        state.time_budget = .031
        state.jump_pressed = True
        before = copy.deepcopy({k: v for k, v in vars(state).items() if k != 'tiles'})
        extra = Heightfield(4, 4, (300, 0, 0), (100, 100, 1), 0, 1,
                            struct.pack('<16H', *([0]*16)), bytes(9))
        self.assertEqual(extend_tiles(state, [extra]), 1)
        self.assertEqual({k: v for k, v in vars(state).items() if k != 'tiles'}, before)
        for index in range(1, 21):
            state.advance({'timestamp':72.3+index*.05, 'kind':'new',
                'acceleration':[0, 0, 0], 'compressed_flags':0}, 200+index*.05)
        self.assertEqual(state.mode, 1)
        self.assertEqual(state.position, [350, 50, 12])
        self.assertEqual(state.velocity, [0, 0, 0])

    def test_identical_tiles_are_deduplicated(self):
        state = TerrainMovement([terrain()], [50, 50, 12], half_height=10, radius=2)
        original = state.tiles[0]
        self.assertEqual(extend_tiles(state, [terrain(), terrain()]), 0)
        self.assertEqual(state.tiles, [original])

    def test_conflict_rejects_entire_addition_before_mutation(self):
        state = TerrainMovement([terrain()], [50, 50, 12], half_height=10, radius=2)
        original = state.tiles
        extra = Heightfield(4, 4, (300, 0, 0), (100, 100, 1), 0, 1,
                            struct.pack('<16H', *([0]*16)), bytes(9))
        conflicting = terrain()
        conflicting.heights = struct.pack('<16H', *([1]*16))
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            extend_tiles(state, [extra, conflicting])
        self.assertIs(state.tiles, original)

    def test_request_session_world_hash_and_freshness_guards(self):
        for failure in ('none', 'session', 'world', 'base', 'buffer', 'expired', 'old_proof'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);area=root/'evidence'/'area';area.mkdir(parents=True)
                heights=struct.pack('<16H', *([0]*16));materials=bytes(9)
                (area/'heights').write_bytes(heights);(area/'materials').write_bytes(materials)
                proof={'pid':7,'exe':'client','sha256':'build','process_created_filetime':1,'observed_at':100}
                world={'address':'world'}
                geometry=json.dumps({'world':world}).encode();(root/'evidence'/'mesh.json').write_bytes(geometry)
                report={'pid':7,'client_proof':dict(proof),'world':world,'tiles':[{
                    'rows':4,'cols':4,'origin':[300,0,0],'scale':[100,100,1],
                    'minimum':0,'quantization':1,'heights':'heights','materials':'materials',
                    'heights_sha256':hashlib.sha256(heights).hexdigest(),
                    'materials_sha256':hashlib.sha256(materials).hexdigest()}]}
                if failure=='world':report['world']={'address':'other-world'}
                if failure=='old_proof':report['client_proof']['observed_at']=-100
                raw=json.dumps(report).encode();(area/'manifest.json').write_bytes(raw)
                if failure=='buffer':(area/'heights').write_bytes(b'corrupt')
                request={'id':'update','profile_id':'profile','connection_id':'current',
                    'pawn_guid':{'pawn':1},'base_terrain_sha256':'base',
                    'manifest':'evidence/area/manifest.json','manifest_sha256':hashlib.sha256(raw).hexdigest(),
                    'expires_at':120}
                if failure=='session':request['connection_id']='stale'
                if failure=='base':request['base_terrain_sha256']='stale'
                if failure=='expired':request['expires_at']=99
                path=root/'request.json';path.write_text(json.dumps(request))
                connection=SimpleNamespace(connection_id='current',terrain_experiment_id='profile',
                    actor_guids={'pawn':{'pawn':1}},phase='joined',possession_acknowledged=True,
                    terrain_manifest_hash='base',terrain_experiment_config={'pid':7,
                    'static_collision_snapshot':'evidence/mesh.json',
                    'static_collision_sha256':hashlib.sha256(geometry).hexdigest()})
                state=TerrainMovement([terrain()],[50,50,12],half_height=10,radius=2)
                state.timestamp=42;state.time_budget=.031;events=[]
                with patch.object(extension,'ROOT',root),patch.object(extension,'REQUEST',path),\
                     patch.object(extension.time,'time',return_value=100),\
                     patch('tools.protocol_proof.client_proof',return_value=proof):
                    if failure=='none':
                        self.assertTrue(extension.apply_request(connection,state,lambda *v:events.append(v)))
                        self.assertFalse(extension.apply_request(connection,state,lambda *v:events.append(v)))
                        self.assertEqual(len(state.tiles),2)
                        self.assertEqual(events[0][0],'terrain_cache_extended')
                    elif failure=='session':
                        self.assertFalse(extension.apply_request(connection,state,lambda *v:events.append(v)))
                    else:
                        with self.assertRaises(ValueError):extension.apply_request(connection,state,lambda *v:events.append(v))
                    if failure!='none':
                        self.assertEqual(len(state.tiles),1)
                        self.assertEqual(connection.terrain_manifest_hash,'base')
                        self.assertEqual(events,[])
                    self.assertEqual((state.timestamp,state.time_budget),(42,.031))
