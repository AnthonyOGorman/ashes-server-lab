import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lab import terrain_relocation as relocation
from lab.terrain_movement import TerrainMovement
from lab.static_collision import ConvexCollision
from tests.test_static_collision import terrain,box


class TerrainRelocationTests(unittest.TestCase):
    def test_deeply_buried_capsule_is_rejected_even_without_surface_contact(self):
        state=TerrainMovement([terrain()],[50,50,12],half_height=10,radius=2,floor_clearance=2)
        rock=ConvexCollision(*box([100,100,-100],[200,200,200]))
        state.static_meshes=[rock]
        self.assertTrue(rock.contains_point([150,150,12]))
        self.assertFalse(rock.contains_point([99,150,12]))
        # Its top is above the allowed floor search, so terrain still supplies
        # a supported height. Every surface is farther away than the radius.
        with self.assertRaisesRegex(ValueError,'inside solid collision'):
            relocation.validated_position(state,[150,150,12])
        self.assertEqual(relocation.validated_position(state,[50,150,12]),[50,150,12])

    def test_placement_requires_support_and_capsule_clearance(self):
        state=TerrainMovement([terrain()],[50,50,12],half_height=10,radius=2,floor_clearance=2)
        self.assertEqual(relocation.validated_position(state,[150,150,12]),[150,150,12])
        for target in ([500,500,12],[150,150,0],[150,150,100],[float('nan'),150,12]):
            with self.assertRaises(ValueError):relocation.validated_position(state,target)
        state.static_meshes=[ConvexCollision(*box([149,149,5],[151,151,20]))]
        with self.assertRaises(ValueError):relocation.validated_position(state,[150,150,12])

    def test_once_only_current_session_placement_preserves_clock_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'request.json'
            state=TerrainMovement([terrain()],[50,50,12],half_height=10,radius=2,floor_clearance=2)
            state.timestamp=42;state.time_budget=.03;state.wall_observed=100
            c=SimpleNamespace(connection_id='current',terrain_experiment_id='profile',
                actor_guids={'pawn':{'pawn':1}},phase='joined',possession_acknowledged=True)
            request=dict(id='test',connection_id='current',profile_id='profile',
                pawn_guid={'pawn':1},position=[150,150,12],expires_at=120)
            path.write_text(json.dumps(dict(request,connection_id='old')))
            events=[]
            with patch.object(relocation,'REQUEST',path),patch.object(relocation.time,'time',return_value=100):
                self.assertFalse(relocation.apply_request(c,state,lambda *v:events.append(v)))
                path.write_text(json.dumps(request))
                self.assertTrue(relocation.apply_request(c,state,lambda *v:events.append(v)))
                self.assertFalse(relocation.apply_request(c,state,lambda *v:events.append(v)))
                path.write_text(json.dumps(dict(request,id='expired',expires_at=99)))
                self.assertFalse(relocation.apply_request(c,state,lambda *v:events.append(v)))
            self.assertEqual(state.position,[150,150,12])
            self.assertEqual((state.timestamp,state.time_budget,state.wall_observed),(42,.03,100))
            self.assertEqual([e[0] for e in events],['terrain_relocation_applied','terrain_relocation_rejected'])
