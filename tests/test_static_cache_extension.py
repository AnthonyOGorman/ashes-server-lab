import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lab import static_cache_extension as extension
from lab.static_collision import ConvexCollision
from lab.terrain_movement import TerrainMovement
from tests.test_static_collision import box,terrain


class StaticCacheExtensionTests(unittest.TestCase):
    def test_added_wall_blocks_motion_without_resetting_physics(self):
        state=TerrainMovement([terrain()],[50,50,12],half_height=10,radius=2,floor_clearance=2)
        state.timestamp=42;state.wall_observed=100;state.time_budget=.03
        before=copy.deepcopy({k:v for k,v in vars(state).items() if k not in ('tiles','static_meshes')})
        wall=ConvexCollision(*box([80,0,0],[100,300,200]))
        self.assertEqual(extension.extend_meshes(state,[wall,wall]),1)
        self.assertEqual({k:v for k,v in vars(state).items() if k not in ('tiles','static_meshes')},before)
        hits=[]
        for index in range(1,11):
            result=state.advance({'timestamp':42+index*.05,'acceleration':[8192,0,0],
                'compressed_flags':0,'kind':'new'},100+index*.05)
            hits.extend(result['collision_hits'])
        self.assertTrue(hits);self.assertLessEqual(state.position[0],78.001)
        self.assertEqual(state.mode,1)
        self.assertEqual(extension.extend_meshes(state,[wall]),0)


    def test_background_preparation_does_not_wait_for_geometry_and_reuses_exact_bytes(self):
        started=threading.Event();release=threading.Event();finished=threading.Event()
        raw=b'{"unique-background-test":true}'
        wall=ConvexCollision(*box([80,0,0],[100,300,200]))
        def build(report):
            started.set()
            if not release.wait(2):raise RuntimeError('test preparation deadline')
            return [wall],[]
        real_remember=extension.remember_geometry
        def remember(*args):
            result=real_remember(*args);finished.set();return result
        with extension._prepared_lock:extension._prepared.pop(extension.preparation_key(raw),None)
        with patch.object(extension,'from_export',side_effect=build) as decoder,\
             patch.object(extension,'remember_geometry',side_effect=remember):
            try:
                self.assertIsNone(extension.prepared_geometry(raw))
                self.assertTrue(started.wait(1))
                self.assertIsNone(extension.prepared_geometry(raw))
                self.assertEqual(decoder.call_count,1)
            finally:release.set()
            self.assertTrue(finished.wait(2))
            self.assertEqual(extension.prepared_geometry(raw),([wall],[]))
            self.assertTrue(hasattr(wall,'_static_signature'))
            self.assertEqual(decoder.call_count,1)

    def test_prepared_cache_is_bounded_and_byte_hash_scoped(self):
        wall=ConvexCollision(*box([80,0,0],[100,300,200]))
        for raw in (b'one',b'two',b'three'):extension.remember_geometry(raw,[wall],[])
        with extension._prepared_lock:
            self.assertLessEqual(len(extension._prepared),2)
            self.assertNotIn(extension.preparation_key(b'one'),extension._prepared)
            self.assertIn(extension.preparation_key(b'two'),extension._prepared)
            self.assertNotEqual(extension.preparation_key(b'two'),extension.preparation_key(b'two '))

    def test_request_guards_reject_old_world_moving_and_unsupported_shapes(self):
        for failure in ('none','world','moving','unsupported','base','session','expired'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'evidence').mkdir()
                proof={'pid':7,'exe':'client','sha256':'build','process_created_filetime':1,'observed_at':100}
                base={'world':{'address':'world'},'pawn':{'address':'pawn'}}
                raw=json.dumps(base).encode();(root/'evidence'/'base.json').write_bytes(raw)
                transform={'rotation':[0,0,0,1],'translation':[0,0,0],'scale':[1,1,1]}
                vertices,indices=box([80,0,0],[100,300,200])
                report={**base,'pid':7,'client_proof':proof,'components':[{'identity':{'address':'component'},
                    'asset':'mesh','mobility':0,'instances':[],'native_component_transform':transform,
                    'response':{'collision_enabled':3,'pawn_response':2}}],
                    'assets':{'mesh':{'collision_trace_flag':0,'shapes':[{'type':'KConvexElem',
                        'Transform':transform,'VertexData':vertices,'IndexData':indices}]}}}
                if failure=='world':report['world']={'address':'old'}
                if failure=='moving':report['components'][0]['mobility']=2
                if failure=='unsupported':report['assets']['mesh']['collision_trace_flag']=3
                snapshot=json.dumps(report).encode();(root/'evidence'/'extra_7.json').write_bytes(snapshot)
                request={'id':'update','profile_id':'profile','connection_id':'current','pawn_guid':{'pawn':1},
                    'base_static_sha256':hashlib.sha256(raw).hexdigest(),'snapshot':'evidence/extra_7.json',
                    'snapshot_sha256':hashlib.sha256(snapshot).hexdigest(),'expires_at':120}
                if failure=='base':request['base_static_sha256']='stale'
                if failure=='session':request['connection_id']='stale'
                if failure=='expired':request['expires_at']=99
                path=root/'request.json';path.write_text(json.dumps(request))
                connection=SimpleNamespace(connection_id='current',terrain_experiment_id='profile',phase='joined',
                    possession_acknowledged=True,actor_guids={'pawn':{'pawn':1}},terrain_experiment_config={
                    'pid':7,'static_collision_snapshot':'evidence/base.json','static_collision_sha256':hashlib.sha256(raw).hexdigest()})
                state=TerrainMovement([terrain()],[50,50,12],half_height=10,radius=2)
                state.timestamp=42;state.time_budget=.03;events=[]
                with patch.object(extension,'ROOT',root),patch.object(extension,'REQUEST',path),\
                     patch.object(extension.time,'time',return_value=100),\
                     patch('tools.protocol_proof.client_proof',return_value=proof):
                    extension.prepare_geometry(snapshot)
                    if failure=='none':
                        with patch.object(extension,'prepared_geometry',return_value=None):
                            self.assertFalse(extension.apply_request(connection,state,lambda *v:events.append(v)))
                            self.assertIsNone(connection.static_extension_id)
                            self.assertEqual(state.static_meshes,[])
                            self.assertEqual(events,[])
                        self.assertTrue(extension.apply_request(connection,state,lambda *v:events.append(v)))
                        self.assertFalse(extension.apply_request(connection,state,lambda *v:events.append(v)))
                        self.assertEqual(len(state.static_meshes),1)
                    elif failure=='session':
                        self.assertFalse(extension.apply_request(connection,state,lambda *v:events.append(v)))
                    else:
                        with self.assertRaises(ValueError):extension.apply_request(connection,state,lambda *v:events.append(v))
                        self.assertFalse(extension.apply_request(connection,state,lambda *v:events.append(v)))
                    if failure!='none':self.assertEqual(state.static_meshes,[])
                    self.assertEqual((state.timestamp,state.time_budget),(42,.03))
