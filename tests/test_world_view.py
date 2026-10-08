import base64
import struct
import threading
import unittest
from types import SimpleNamespace

from lab import world_view
from lab.terrain_movement import TerrainMovement
from tests.test_static_collision import terrain, box
from lab.static_collision import ConvexCollision


class WorldViewTests(unittest.TestCase):
    def fixture(self):
        state=TerrainMovement([terrain()],[50,50,12],half_height=10,radius=2)
        state.static_meshes=[ConvexCollision(*box([100,100,0],[120,120,100]))]
        c=SimpleNamespace(phase='joined',connection_id='one',terrain_experiment=state,
                          terrain_manifest_hash='terrain',static_extension_generation='mesh')
        owner=SimpleNamespace(world=SimpleNamespace(protocol_lock=threading.RLock(),
            protocol=SimpleNamespace(connections={('127.0.0.1',1):c})))
        return owner,c,state

    def test_all_joined_players_are_visible_without_modifying_physics(self):
        owner,c,state=self.fixture()
        before=(state.position.copy(),state.velocity.copy(),state.timestamp,state.time_budget)
        other=SimpleNamespace(**vars(c));other.connection_id='two'
        owner.world.protocol.connections[('127.0.0.1',2)]=other
        result=world_view.snapshot(owner)
        self.assertEqual({p['id'] for p in result['players']},{'one','two'})
        self.assertEqual(result['players'][0]['position'],state.position)
        result['players'][0]['position'][0]=999
        result['players'][0]['trail'][0][0]=999
        self.assertEqual(before,(state.position,state.velocity,state.timestamp,state.time_budget))
        self.assertNotEqual(world_view.snapshot(owner)['players'][0]['trail'][0][0],999)
        owner.world.protocol.connections.clear()
        self.assertEqual(world_view.snapshot(owner)['players'],[])

    def test_geometry_encodes_admitted_edges_in_rebased_metres(self):
        owner,c,state=self.fixture()
        result=world_view.geometry(owner,'one',[100,100,0],1000,1,'full')
        raw=base64.b64decode(result['collision'])
        self.assertEqual(len(raw),18*24)  # Includes each face's triangulation diagonal.
        vertices=list(struct.iter_unpack('<3f',raw))
        self.assertAlmostEqual(min(p[0] for p in vertices),0)
        self.assertAlmostEqual(max(p[0] for p in vertices),.2,places=6)
        self.assertAlmostEqual(max(p[2] for p in vertices),1)
        self.assertEqual(result['generation'],['terrain','mesh'])
        self.assertEqual(result['segments']['collision'],18)
        self.assertEqual(result['clipped'],{'terrain':False,'collision':False})

    def test_native_holes_are_not_bridged_by_coarse_grid(self):
        owner,c,state=self.fixture()
        tile=state.tiles[0];tile.materials=bytes([255])*len(tile.materials)
        result=world_view.geometry(owner,'one',[50,50,0],1000,4)
        self.assertEqual(result['terrain'],'')
        self.assertGreater(result['segments']['collision'],0)

    def test_light_and_bounds_display_leave_server_geometry_intact(self):
        owner,c,state=self.fixture();mesh=state.static_meshes[0]
        before=list(mesh.faces)
        full=world_view.geometry(owner,'one',[100,100,0],1000,1,'full')
        light=world_view.geometry(owner,'one',[100,100,0],1000,1,'light')
        bounds=world_view.geometry(owner,'one',[100,100,0],1000,1,'bounds')
        self.assertEqual(bounds['segments']['collision'],12)
        self.assertEqual(light['collision_detail'],'light')
        self.assertEqual(light['nearby_colliders'],1)
        self.assertEqual(mesh.faces,before)
        self.assertEqual(full['generation'],light['generation'])

    def test_invalid_or_departed_player_cannot_return_geometry(self):
        owner,c,state=self.fixture()
        with self.assertRaisesRegex(ValueError,'active player'):
            world_view.geometry(owner,'old',[50,50,0])
        with self.assertRaisesRegex(ValueError,'finite'):
            world_view.geometry(owner,'one',[float('nan'),0,0])
        with self.assertRaisesRegex(ValueError,'bounded'):
            world_view.geometry(owner,'one',[50,50,0],1000000)
