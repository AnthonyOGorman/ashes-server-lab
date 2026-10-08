import math
import unittest
from lab.shared_collision import SharedCollision,resident_faces
from lab.static_collision import ConvexCollision,placement_matrix,transform_point,instance_point
from lab.triangle_collision import TriangleCollision
from lab.static_cache_extension import extend_meshes
from types import SimpleNamespace
from tests.test_static_collision import box


class SharedCollisionTests(unittest.TestCase):
    def source(self,triangle=False):
        vertices,indices=box([-30,-20,-10],[30,20,10])
        return (TriangleCollision(vertices,[list(reversed(indices[i:i+3])) for i in range(0,len(indices),3)])
                if triangle else ConvexCollision(vertices,indices))

    def test_composed_native_transform_matches_expanded_vertices_and_normals(self):
        angle=.37
        transform={'translation':[-700000,400000,15000],'scale':[1.7]*3,
                   'rotation':[0,math.sin(angle/2),0,math.cos(angle/2)]}
        instance=[0,2,0,0,-2,0,0,0,0,0,2,0,120,-250,35,1]
        for triangular in (False,True):
            source=self.source(triangular);shared=SharedCollision(source,placement_matrix(transform,instance))
            for (face,normal),(world,world_normal) in zip(source.faces,shared.faces):
                for a,b in zip(face,world):
                    expected=transform_point(transform,instance_point(instance,a))
                    self.assertLess(math.dist(expected,b),1e-8)
                    self.assertLess(math.dist(a,shared.inverse(b)),1e-8)
                self.assertAlmostEqual(math.sqrt(sum(v*v for v in world_normal)),1)
            self.assertTrue(shared.contains_point(shared.point([0,0,0])))
            self.assertFalse(shared.contains_point(shared.point([300,0,0])))

    def test_rotated_triangle_ground_and_bounded_queries_match_world_mesh(self):
        source=self.source(True)
        transform={'translation':[-700000,400000,15000],'scale':[2.]*3,
                   'rotation':[math.sin(.1),0,0,math.cos(.1)]}
        shared=SharedCollision(source,placement_matrix(transform))
        vertices=[];triangles=[];lookup={}
        for face,_ in shared.faces:
            triangle=[]
            for point in face:
                key=tuple(point)
                if key not in lookup:
                    lookup[key]=len(vertices);vertices.append(point)
                triangle.append(lookup[key])
            triangles.append(triangle)
        # Use the exact expanded faces as an independent world-space query.
        # A convex hull also supplies consistent volume and ground queries.
        indices=[i for t in triangles for i in t]
        expanded=ConvexCollision(vertices,indices)
        for x in (-700020,-700000,-699980):
            for y in (399990,400000,400010):
                actual=shared.ground(x,y,15100,.6);expected=expanded.ground(x,y,15100,.6)
                self.assertAlmostEqual(actual['height'],expected['height'],places=7)
        low=[-700010,399990,14990];high=[-699990,400010,15030]
        a=list(shared.triangles(low,high));b=list(expanded.triangles(low,high))
        self.assertEqual(len(a),len(b))

    def test_thousands_of_placements_share_storage_and_keep_distinct_collision(self):
        source=self.source(True)
        shapes=[SharedCollision(source,[1,0,0,0,0,1,0,0,0,0,1,0,i*100,0,0,1]) for i in range(1000)]
        self.assertTrue(all(s.source is source for s in shapes))
        self.assertEqual(resident_faces(shapes),12)
        self.assertEqual(sum(len(s.faces) for s in shapes),12000)
        state=SimpleNamespace(static_meshes=[])
        self.assertEqual(extend_meshes(state,shapes),1000)
        self.assertEqual(extend_meshes(state,shapes),0)
        self.assertTrue(shapes[999].contains_point([99900,0,0]))
        self.assertFalse(shapes[0].contains_point([99900,0,0]))
