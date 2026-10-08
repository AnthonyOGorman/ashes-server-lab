import copy
import math
import json
from pathlib import Path
import struct
import unittest

from lab.static_collision import ConvexCollision, from_export, transform_point, box_geometry
from lab.terrain import Heightfield
from lab.terrain_movement import TerrainMovement


def box(low,high):
    vertices=[[x,y,z] for z in (low[2],high[2]) for y in (low[1],high[1]) for x in (low[0],high[0])]
    indices=[0,1,3,0,3,2,4,6,7,4,7,5,0,4,5,0,5,1,
             2,3,7,2,7,6,0,2,6,0,6,4,1,5,7,1,7,3]
    return vertices,indices


def terrain():
    return Heightfield(4,4,(0,0,0),(100,100,1),0,1,struct.pack('<16H',*([0]*16)),bytes(9))


def move(t,jump=False,acceleration=(0,0,0)):
    return {'timestamp':t,'acceleration':acceleration,'compressed_flags':int(jump)}


class StaticCollisionTests(unittest.TestCase):
    def test_native_small_mesh_contact_stays_supported_after_finite_floor_adjustment(self):
        report=json.loads((Path(__file__).parent/'fixtures/native_campfire_floor.json').read_text())
        meshes,unsupported=from_export(report)
        self.assertEqual(unsupported,[])
        state=TerrainMovement([],report['position'],half_height=96,radius=22,
            floor_clearance=2.15,gravity=-1225,static_meshes=meshes)
        initial_xy=state.position[:2].copy()
        state.advance(move(0),0)
        for i in range(1,60):state.advance(move(i*.05),i*.05)
        self.assertEqual(state.mode,1)
        self.assertEqual(state.velocity,[0,0,0])
        self.assertEqual(state.position[:2],initial_xy)
        self.assertAlmostEqual(state.position[2],report['expected_native_rest_z'],delta=.002)

    def test_falling_forward_into_steep_convex_face_cannot_launch_character(self):
        # A closed wedge with a steep face, entirely above the flat terrain.
        vertices=[[100,100,0],[200,100,0],[200,100,200],
                  [100,200,0],[200,200,0],[200,200,200]]
        indices=[0,1,2,3,5,4,0,3,4,0,4,1,1,4,5,1,5,2,0,2,5,0,5,3]
        slope=ConvexCollision(vertices,indices)
        state=TerrainMovement([terrain()],[50,150,70],speed=996,gravity=-1225,
            half_height=10,radius=2,floor_clearance=2,static_meshes=[slope])
        state.advance(move(0),0)
        result=state.advance(move(.25,acceleration=(8192,0,0)),.25)
        self.assertTrue(result['collision_hits'])
        self.assertLessEqual(state.position[2],70)
        self.assertLessEqual(state.velocity[2],0)
        for i in range(6,26):
            state.advance(move(i*.05,acceleration=(8192,0,0)),i*.05)
            self.assertLessEqual(state.velocity[2],0)

    def test_native_box_full_lengths_rotation_and_component_transform(self):
        shape={'Center':[10,20,30],'Rotation':[0,90,0],'X':2,'Y':4,'Z':6}
        transform={'rotation':[0,0,0,1],'translation':[100,200,300],'scale':[2,2,2]}
        collider=ConvexCollision(*box_geometry(shape,transform))
        self.assertEqual(collider.minimum,[116,238,354])
        self.assertEqual(collider.maximum,[124,242,366])
        self.assertEqual(collider.ground(120,240,400,.6)['height'],366)
        # Positive pitch raises +X; positive roll lowers +Y in Unreal.
        shape.update(Center=[0,0,0],Rotation=[90,0,0])
        vertices,_=box_geometry(shape,dict(transform,translation=[0,0,0],scale=[1,1,1]))
        self.assertAlmostEqual(vertices[1][2]-vertices[0][2],2)
        shape['Rotation']=[0,0,90]
        vertices,_=box_geometry(shape,dict(transform,translation=[0,0,0],scale=[1,1,1]))
        self.assertAlmostEqual(vertices[2][2]-vertices[0][2],-4)
        with self.assertRaises(ValueError):box_geometry(shape,dict(transform,scale=[1,2,1]))
        shape['X']=-1
        with self.assertRaises(ValueError):box_geometry(shape,transform)

    def test_exported_box_blocks_walk_and_supports_landing(self):
        transform={'rotation':[0,0,0,1],'translation':[0,0,0],'scale':[1,1,1]}
        report={'components':[{'identity':{'address':'box'},'asset':'mesh','instances':[],
                    'native_component_transform':transform,
                    'response':{'collision_enabled':3,'pawn_response':2}}],
                'assets':{'mesh':{'collision_trace_flag':1,'shapes':[
                    {'type':'KBoxElem','CollisionEnabled':3,'Center':[155,150,100],
                     'Rotation':[0,0,0],'X':10,'Y':100,'Z':200}]}}}
        colliders,unsupported=from_export(report)
        self.assertEqual(unsupported,[])
        state=TerrainMovement([terrain()],[50,150,12],speed=1000,half_height=10,
                              radius=2,floor_clearance=2,static_meshes=colliders)
        state.advance(move(0),0)
        result=state.advance(move(.25,acceleration=(8192,0,0)),.25)
        self.assertTrue(result['collision_hits']);self.assertLessEqual(state.position[0],148.001)
        state=TerrainMovement([terrain()],[155,150,212],half_height=10,radius=2,
                              floor_clearance=2,gravity=-1225,static_meshes=colliders)
        state.advance(move(0),0);self.assertTrue(state.advance(move(.05,True),.05)['jump_started'])
        for i in range(2,45):state.advance(move(i*.05),i*.05)
        self.assertEqual(state.mode,1);self.assertAlmostEqual(state.position[2],212)

    def test_world_transform_keeps_scale_rotation_translation_order(self):
        transform={'rotation':[0,0,math.sqrt(.5),math.sqrt(.5)],
                   'translation':[10,20,30],'scale':[2,3,-4]}
        result=transform_point(transform,[1,2,3])
        for actual,expected in zip(result,[4,22,18]):self.assertAlmostEqual(actual,expected)

    def test_convex_bounds_ground_and_broad_phase(self):
        collider=ConvexCollision(*box([10,20,0],[30,40,50]))
        self.assertEqual(collider.ground(20,30,51,.6)['height'],50)
        self.assertIsNone(collider.ground(20,30,49,.6))
        self.assertIsNone(collider.ground(0,30,100,.6))
        self.assertEqual(list(collider.triangles([100,100,100],[200,200,200])),[])

    def test_invalid_indices_and_nonconvex_faces_are_rejected(self):
        vertices,indices=box([0,0,0],[10,10,10])
        with self.assertRaises(ValueError):ConvexCollision(vertices,indices+[0,1,100])
        with self.assertRaises(ValueError):ConvexCollision(vertices+[[100,100,100]],indices)
        with self.assertRaises(ValueError):ConvexCollision(vertices,indices[:-3])

    def test_wall_blocks_fast_movement_with_clear_endpoints(self):
        wall=ConvexCollision(*box([150,100,0],[160,200,200]))
        state=TerrainMovement([terrain()],[50,150,12],speed=1000,half_height=10,radius=2,
                              floor_clearance=2,static_meshes=[wall])
        state.advance(move(0),0)
        result=state.advance(move(.25,acceleration=(8192,0,0)),.25)
        self.assertTrue(result['collision_hits'])
        self.assertGreater(state.position[0],50)
        self.assertLessEqual(state.position[0],148.001)
        self.assertEqual(state.velocity[0],0)

    def test_mesh_supports_idle_jump_and_landing_above_terrain(self):
        platform=ConvexCollision(*box([100,100,100],[200,200,150]))
        state=TerrainMovement([terrain()],[150,150,162],half_height=10,radius=2,
                              floor_clearance=2,gravity=-1225,static_meshes=[platform])
        state.advance(move(0),0)
        state.advance(move(.05),.05)
        self.assertEqual(state.mode,1)
        self.assertTrue(state.advance(move(.1,True),.1)['jump_started'])
        for i in range(3,45):state.advance(move(i*.05),i*.05)
        self.assertEqual(state.mode,1)
        self.assertAlmostEqual(state.position[2],162)
        self.assertEqual(state.velocity[2],0)

    def test_platform_can_support_over_a_terrain_hole(self):
        tile=terrain();tile.materials=bytes([255]*9)
        platform=ConvexCollision(*box([100,100,90],[200,200,100]))
        state=TerrainMovement([tile],[150,150,112],half_height=10,radius=2,
                              floor_clearance=2,static_meshes=[platform])
        state.advance(move(0),0);state.advance(move(.1),.1)
        self.assertEqual(state.mode,1);self.assertAlmostEqual(state.position[2],112)

    def test_roof_is_a_ceiling_and_not_a_floor_from_below(self):
        roof=ConvexCollision(*box([100,100,10],[200,200,20]))
        state=TerrainMovement([terrain()],[150,150,2],half_height=2,radius=1,
                              gravity=-1225,static_meshes=[roof])
        self.assertEqual(state.floor(150,150),2)
        state.velocity[2]=153.125;state.advance(move(0),0)
        result=state.advance(move(.25),.25)
        self.assertTrue(any(hit['normal'][2]<-.99 for hit in result['collision_hits']))
        self.assertLessEqual(state.position[2],8.001)

    def test_export_reports_unsupported_shapes_and_skips_probe_only(self):
        vertices,indices=box([0,0,0],[10,10,10])
        identity={'rotation':[0,0,0,1],'translation':[0,0,0],'scale':[1,1,1]}
        report={'components':[{'identity':{'address':'component'},'asset':'mesh',
                    'response':{'collision_enabled':3,'pawn_response':2},'instances':[],
                    'native_component_transform':identity}],
                'assets':{'mesh':{'collision_trace_flag':0,'shapes':[
                    {'type':'KConvexElem','Transform':identity,'VertexData':vertices,
                     'IndexData':indices,'CollisionEnabled':3},
                    {'type':'KSphereElem','CollisionEnabled':3}]}}}
        colliders,unsupported=from_export(report)
        self.assertEqual(len(colliders),1);self.assertEqual(unsupported[0]['shape'],'KSphereElem')
        probe=copy.deepcopy(report);probe['components'][0]['response']['collision_enabled']=4
        self.assertEqual(from_export(probe),([],[]))
        malformed=copy.deepcopy(report)
        bad=copy.deepcopy(malformed['assets']['mesh']['shapes'][0])
        bad['IndexData'][-1]=100
        malformed['assets']['mesh']['shapes'].insert(0,bad)
        colliders,unsupported=from_export(malformed)
        self.assertEqual(len(colliders),1)
        self.assertTrue(any('index outside' in row.get('reason','') for row in unsupported))
