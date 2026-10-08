import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lab import collision_refresh as refresh
from lab.terrain_movement import TerrainMovement
from lab.static_collision import ConvexCollision
from tests.test_static_collision import terrain,box


class CollisionRefreshTests(unittest.TestCase):
    def test_terrain_admission_does_not_wait_for_static_mesh_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir();(root/'evidence').mkdir()
            tile=terrain();(root/'evidence/heights').write_bytes(tile.heights)
            (root/'evidence/materials').write_bytes(tile.materials)
            metadata={'rows':tile.rows,'cols':tile.cols,'origin':tile.origin,'scale':tile.scale,
                'minimum':tile.minimum,'quantization':tile.quantization,
                'heights':'heights','materials':'materials'}
            (root/'evidence/manifest.json').write_text(json.dumps({'tiles':[metadata]}))
            state=SimpleNamespace(tiles=[],static_meshes=[],position=[1,2,100],
                                  velocity=[0,0,-50],timestamp=42,time_budget=.01)
            c=SimpleNamespace(connection_id='a',phase='joined',possession_acknowledged=True,
                terrain_experiment_id='profile',actor_guids={'pawn':{'guid':1}},terrain_experiment=state,
                terrain_manifest_hash='terrain-old',static_extension_generation='static-old')
            events=[]
            owner=SimpleNamespace(world=SimpleNamespace(protocol_lock=threading.RLock(),
                protocol=SimpleNamespace(connections={('127.0.0.1',1):c})),event=lambda *e:events.append(e))
            entry={'port':1,'connection_id':'a','profile_id':'profile','pawn_guid':{'guid':1}}
            before=vars(state).copy()
            with patch.object(refresh,'ROOT',root),patch.object(refresh,'read_config',return_value={'enabled':True}),\
                 patch.object(refresh,'still_current',return_value=True),\
                 patch.object(refresh,'from_export',side_effect=AssertionError('static work must not run')):
                requests=refresh.publish_terrain(owner,entry,{'manifest':'evidence/manifest.json','tiles':1})
                self.assertEqual(len(requests),1)
                self.assertEqual(requests[0][1]['base_terrain_sha256'],'terrain-old')
                self.assertFalse((root/'data/static-cache-extension.json').exists())
                self.assertEqual(before,vars(state))
                self.assertEqual(events[0][0],'collision_refresh_terrain_ready')
                self.assertFalse(events[0][1]['static_export_complete'])

    def test_completed_terrain_marker_is_admitted_once_before_export_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'terrain-ready.json').write_text(json.dumps({'manifest':'ready'}))
            owner=SimpleNamespace();entry={'connection_id':'a'}
            args=['tools/refresh_streamed_collision.py']
            with patch.object(refresh,'publish_terrain',return_value=[('request',{'id':'one'})]) as publish,\
                 patch.object(refresh,'finish_requests') as finish:
                refresh.stage_progress(owner,entry,'export',args,path)
                refresh.stage_progress(owner,entry,'export',args,path)
                self.assertFalse((path/'result.json').exists())
                publish.assert_called_once();finish.assert_called_once()

    def test_early_terrain_cache_change_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir();(root/'evidence').mkdir()
            (root/'evidence/manifest.json').write_text('{}')
            c=SimpleNamespace(connection_id='a',phase='joined',possession_acknowledged=True,
                terrain_experiment_id='profile',actor_guids={'pawn':{'guid':1}},
                terrain_experiment=SimpleNamespace(tiles=[]),terrain_manifest_hash='old')
            owner=SimpleNamespace(world=SimpleNamespace(protocol_lock=threading.RLock(),
                protocol=SimpleNamespace(connections={('127.0.0.1',1):c})),event=lambda *e:None)
            entry={'port':1,'connection_id':'a','profile_id':'profile','pawn_guid':{'guid':1}}
            def change(*args):c.terrain_manifest_hash='new';return 1
            with patch.object(refresh,'ROOT',root),patch.object(refresh,'read_config',return_value={'enabled':True}),\
                 patch.object(refresh,'still_current',return_value=True),patch.object(refresh,'new_tiles',side_effect=change):
                with self.assertRaisesRegex(ValueError,'cache changed'):
                    refresh.publish_terrain(owner,entry,{'manifest':'evidence/manifest.json'})
            self.assertEqual(list((root/'data').iterdir()),[])

    def test_refresh_due_on_new_session_time_or_distance(self):
        entry={'connection_id':'a','position':[0,0,0]}
        config={'interval_seconds':60,'distance_cm':500}
        last=dict(entry,completed_at=100)
        self.assertTrue(refresh.due(entry,None,101,config))
        self.assertFalse(refresh.due(entry,last,101,config))
        self.assertTrue(refresh.due(entry,last,160,config))
        self.assertTrue(refresh.due(dict(entry,position=[501,0,0]),last,101,config))
        self.assertTrue(refresh.due(dict(entry,connection_id='b'),last,101,config))

    def test_scan_detects_new_tiles_and_meshes_without_changing_airborne_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);tile=terrain()
            (path/'heights').write_bytes(tile.heights);(path/'materials').write_bytes(tile.materials)
            metadata={'rows':tile.rows,'cols':tile.cols,'origin':tile.origin,'scale':tile.scale,
                      'minimum':tile.minimum,'quantization':tile.quantization,
                      'heights':'heights','materials':'materials'}
            manifest=path/'manifest.json';manifest.write_text(json.dumps({'tiles':[metadata]}))
            state=TerrainMovement([tile], [50,50,12],half_height=10,radius=2,floor_clearance=2)
            state.tiles=[];state.position=[50,50,100]
            state.velocity=[1,2,-3];state.mode=3;state.timestamp=42;state.time_budget=.01
            mesh=ConvexCollision(*box([100,100,0],[120,120,100]))
            before=(state.position.copy(),state.velocity.copy(),state.mode,state.timestamp,state.time_budget)
            with patch.object(refresh,'from_export',return_value=([mesh],[])):
                self.assertEqual(refresh.new_geometry(state,manifest,{}),(1,1))
                state.tiles=[tile];state.static_meshes=[mesh]
                self.assertEqual(refresh.new_geometry(state,manifest,{}),(0,0))
                metadata['minimum']=10
                manifest.write_text(json.dumps({'tiles':[metadata]}))
                with self.assertRaisesRegex(ValueError,'conflicting'):
                    refresh.new_geometry(state,manifest,{})
            self.assertEqual(before,(state.position,state.velocity,state.mode,state.timestamp,state.time_budget))

    def test_replaced_session_cannot_publish_requests(self):
        owner=SimpleNamespace(world_active=False)
        with patch.object(refresh,'read_config',return_value={'enabled':True}):
            with self.assertRaisesRegex(ValueError,'current enabled'):
                refresh.publish(owner,{'epoch':1,'connection_id':'old'}, {})

    def test_new_exports_publish_current_generations_without_resetting_physics(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir();(root/'evidence').mkdir()
            (root/'evidence/manifest.json').write_text('{}')
            (root/'evidence/snapshot.json').write_text('{}')
            state=SimpleNamespace(position=[1,2,100],velocity=[0,0,-50],timestamp=42,time_budget=.01)
            c=SimpleNamespace(connection_id='a',phase='joined',possession_acknowledged=True,
                terrain_experiment_id='profile',actor_guids={'pawn':{'guid':1}},terrain_experiment=state,
                terrain_manifest_hash='terrain-old',static_extension_generation='static-old')
            owner=SimpleNamespace(world=SimpleNamespace(protocol_lock=threading.RLock(),
                protocol=SimpleNamespace(connections={('127.0.0.1',1):c})),event=lambda *e:None)
            entry={'port':1,'connection_id':'a','profile_id':'profile','pawn_guid':{'guid':1}}
            result={'manifest':'evidence/manifest.json','snapshot':'evidence/snapshot.json'}
            before=vars(state).copy()
            def prepare(*args):
                self.assertFalse(owner.world.protocol_lock._is_owned())
                return 1,1
            with patch.object(refresh,'ROOT',root),patch.object(refresh,'read_config',return_value={'enabled':True}),\
                 patch.object(refresh,'still_current',return_value=True),\
                 patch.object(refresh,'new_geometry',side_effect=prepare):
                requests=refresh.publish(owner,entry,result)
                self.assertEqual(len(requests),2)
                self.assertEqual(requests[0][1]['base_terrain_sha256'],'terrain-old')
                self.assertEqual(requests[1][1]['base_static_sha256'],'static-old')
                self.assertEqual(vars(state),before)
                for path,request in requests:self.assertEqual(json.loads(path.read_text()),request)
                with self.assertRaisesRegex(ValueError,'existing collision extension'):
                    refresh.publish(owner,entry,result)


    def test_cache_change_during_unlocked_preparation_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir();(root/'evidence').mkdir()
            (root/'evidence/manifest.json').write_text('{}')
            (root/'evidence/snapshot.json').write_text('{}')
            state=SimpleNamespace(tiles=[],static_meshes=[],position=[1,2,3])
            c=SimpleNamespace(connection_id='a',phase='joined',possession_acknowledged=True,
                terrain_experiment_id='profile',actor_guids={'pawn':{'guid':1}},terrain_experiment=state,
                terrain_manifest_hash='old',static_extension_generation='old')
            owner=SimpleNamespace(world=SimpleNamespace(protocol_lock=threading.RLock(),
                protocol=SimpleNamespace(connections={('127.0.0.1',1):c})),event=lambda *e:None)
            entry={'port':1,'connection_id':'a','profile_id':'profile','pawn_guid':{'guid':1}}
            def changed(*args):
                self.assertFalse(owner.world.protocol_lock._is_owned())
                c.static_extension_generation='another-accepted-refresh'
                return 0,1
            with patch.object(refresh,'ROOT',root),patch.object(refresh,'read_config',return_value={'enabled':True}),\
                 patch.object(refresh,'still_current',return_value=True),\
                 patch.object(refresh,'new_geometry',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'cache changed'):
                    refresh.publish(owner,entry,{'manifest':'evidence/manifest.json','snapshot':'evidence/snapshot.json'})
            self.assertEqual(list((root/'data').iterdir()),[])

    def test_consumed_but_rejected_extension_is_not_reported_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'request.json';request={'id':'mine','manifest_sha256':'new','manifest':'x'}
            path.write_text(json.dumps(request));events=[]
            c=SimpleNamespace(terrain_extension_id='mine',terrain_manifest_hash='old')
            owner=SimpleNamespace(world=SimpleNamespace(protocol_lock=threading.RLock(),
                protocol=SimpleNamespace(connections={('127.0.0.1',1):c})),event=lambda *e:events.append(e))
            with patch.object(refresh,'still_current',return_value=True):
                with self.assertRaisesRegex(ValueError,'rejected'):
                    refresh.finish_requests(owner,{'port':1,'connection_id':'a'},[(path,request)])
            self.assertFalse(path.exists());self.assertEqual(events,[])

    def test_cleanup_preserves_a_replacement_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'request.json';path.write_text(json.dumps({'id':'other'}))
            request={'id':'mine','snapshot_sha256':'new'};events=[]
            c=SimpleNamespace(static_extension_id='mine',static_extension_generation='new')
            owner=SimpleNamespace(world=SimpleNamespace(protocol_lock=threading.RLock(),
                protocol=SimpleNamespace(connections={('127.0.0.1',1):c})),event=lambda *e:events.append(e))
            with patch.object(refresh,'still_current',return_value=True):
                refresh.finish_requests(owner,{'port':1,'connection_id':'a'},[(path,request)])
            self.assertEqual(json.loads(path.read_text()),{'id':'other'})
            self.assertEqual(events[0][0],'collision_refresh_completed')
