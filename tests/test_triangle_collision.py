import math
import unittest

from lab.triangle_collision import TriangleCollision,triangle_surfaces
from lab.static_collision import from_export
from lab.terrain_movement import TerrainMovement
from lab.terrain_relocation import validated_position
from tests.test_static_collision import terrain,move


def concave_solid():
    polygon=[(0,0),(100,0),(100,40),(40,40),(40,100),(0,100)]
    vertices=[[x,y,z] for z in (0,100) for x,y in polygon]
    cap=[[0,1,2],[0,2,3],[0,3,5],[3,4,5]]
    triangles=[list(reversed(t)) for t in cap]+[[i+6 for i in t] for t in cap]
    for a in range(6):
        b=(a+1)%6;triangles.extend(([a,b,b+6],[a,b+6,a+6]))
    return vertices,triangles


class TriangleCollisionTests(unittest.TestCase):
    def test_concave_volume_distinguishes_solid_from_empty_notch(self):
        mesh=TriangleCollision(*concave_solid())
        self.assertTrue(mesh.closed)
        self.assertTrue(mesh.contains_point([20,20,50]))
        self.assertTrue(mesh.contains_point([0,20,50]))
        self.assertFalse(mesh.contains_point([60,60,50]))
        self.assertFalse(mesh.contains_point([200,20,50]))
        self.assertEqual(mesh.ground(20,20,110,.6)['height'],100)
        self.assertIsNone(mesh.ground(60,60,110,.6))

    def test_shared_edge_surface_preserves_faces_and_closed_core_volume(self):
        vertices,triangles=concave_solid()
        vertices.append([50,-50,50]);triangles.extend(([0,1,12],[12,1,0]))
        meshes=triangle_surfaces(vertices,triangles)
        self.assertEqual(sum(len(m.faces) for m in meshes),len(triangles))
        self.assertEqual(sum(m.closed for m in meshes),1)
        self.assertTrue(any(m.contains_point([20,20,50]) for m in meshes))
        self.assertFalse(any(m.contains_point([60,60,50]) for m in meshes))
        expected=sorted(tuple(tuple(vertices[i]) for i in t) for t in triangles)
        actual=sorted(tuple(tuple(v) for v in t) for m in meshes for t,n in m.faces)
        self.assertEqual(actual,expected)

    def test_buried_capsule_rejected_while_notch_remains_clear(self):
        state=TerrainMovement([terrain()],[150,150,12],half_height=10,radius=2,floor_clearance=2,
                              static_meshes=[TriangleCollision(*concave_solid())])
        with self.assertRaisesRegex(ValueError,'inside solid'):
            validated_position(state,[20,20,12])
        self.assertEqual(validated_position(state,[60,60,12]),[60,60,12])

    def test_capsule_blocks_at_concave_wall_and_lands_on_mesh_roof(self):
        mesh=TriangleCollision(*concave_solid())
        state=TerrainMovement([terrain()],[60,60,12],speed=996,half_height=10,radius=2,
                              floor_clearance=2,static_meshes=[mesh])
        state.advance(move(0),0)
        for i in range(1,11):state.advance(move(i*.05,acceleration=(-8192,0,0)),i*.05)
        self.assertAlmostEqual(state.position[0],42,delta=.01)
        self.assertEqual(state.mode,1)
        fall=TerrainMovement([terrain()],[20,20,200],half_height=10,radius=2,
                             floor_clearance=2,gravity=-1225,static_meshes=[mesh])
        fall.advance(move(0),0)
        for i in range(1,30):fall.advance(move(i*.05),i*.05)
        self.assertAlmostEqual(fall.position[2],112,delta=.01)
        self.assertEqual(fall.velocity,[0,0,0]);self.assertEqual(fall.mode,1)

    def test_spatial_queries_match_brute_force_and_restrict_local_candidates(self):
        vertices=[];triangles=[]
        for y in range(50):
            for x in range(50):
                base=len(vertices);vertices.extend(([x,y,0],[x+1,y,0],[x+1,y+1,0],[x,y+1,0]))
                triangles.extend(([base,base+1,base+2],[base,base+2,base+3]))
        mesh=TriangleCollision(vertices,triangles)
        self.assertFalse(mesh.closed)
        low=[20.2,20.2,-1];high=[20.8,20.8,1]
        selected=list(mesh.triangles(low,high))
        brute=[t for t,n in mesh.faces if all(max(v[i] for v in t)>=low[i] and
                                            min(v[i] for v in t)<=high[i] for i in range(3))]
        self.assertEqual(selected,brute);self.assertEqual(len(selected),2)
        self.assertEqual(mesh.ground(20.5,20.5,1,.6)['height'],0)

    def test_native_triangle_export_applies_world_transform_and_preserves_nonconvexity(self):
        vertices,triangles=concave_solid()
        r={'components':[{'identity':{'address':'cliff'},'asset':'mesh','instances':[],
            'response':{'collision_enabled':3,'pawn_response':2},
            'native_component_transform':{'rotation':[0,0,0,1],'translation':[1000,2000,0],'scale':[2,2,2]}}],
            'assets':{'mesh':{'collision_trace_flag':3,'CookedTriangles':[{
                'layout':'native-chaos-triangles16-v1','vertices':vertices,'triangles':triangles,
                'bounds':[0,0,0,100,100,100]}]}}}
        meshes,errors=from_export(r);self.assertEqual(errors,[])
        self.assertEqual(meshes[0].minimum,[1000,2000,0])
        self.assertTrue(meshes[0].contains_point([1040,2040,100]))
        self.assertFalse(meshes[0].contains_point([1120,2120,100]))
