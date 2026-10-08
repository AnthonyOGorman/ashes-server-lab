import math
import struct
import unittest
from lab.capsule_sweep import segment_triangle_distance, sweep_capsule, move_capsule,limit_upward_slide
from lab.terrain import Heightfield

FLOOR=((-100.,-100.,0.),(100.,-100.,0.),(0.,100.,0.))
WALL=((0.,-100.,-100.),(0.,100.,-100.),(0.,0.,200.))


class CapsuleSweepTests(unittest.TestCase):
    def test_falling_slide_cannot_convert_forward_motion_into_ascent(self):
        normal=[-math.sqrt(.75),0,.5]
        self.assertEqual(limit_upward_slide([5,10,8],[10,10,-2],normal),[0.,10.,0.])
        jump=limit_upward_slide([5,10,8],[10,10,4],normal)
        self.assertAlmostEqual(jump[2],4)
        self.assertAlmostEqual(jump[1],10)
        self.assertEqual(limit_upward_slide([1,2,-3],[4,5,-2],normal),[1,2,-3])

    def test_falling_capsule_does_not_ride_up_an_inclined_wall(self):
        ramp=((0,-100,-100),(0,100,-100),(100,0,100))
        result,hits=move_capsule([-10,0,0],[100,20,-5],10,2,
            lambda *args:[ramp],limit_falling_ascent=True)
        self.assertTrue(hits)
        self.assertLessEqual(result[2],0)
        self.assertGreater(result[1],0)

    def test_segment_crossing_face_has_zero_distance(self):
        distance,p,q=segment_triangle_distance([0,0,-2],[0,0,2],FLOOR)
        self.assertEqual(distance,0.)
        self.assertEqual(p,q)

    def test_segment_parallel_to_face_uses_interior_distance(self):
        distance,_,_=segment_triangle_distance([-10,0,5],[10,0,5],FLOOR)
        self.assertAlmostEqual(distance,5.)

    def test_capsule_fall_hits_floor_before_crossing_it(self):
        hit=sweep_capsule([0,0,20],[0,0,-30],10,2,[FLOOR])
        self.assertAlmostEqual(hit['fraction'],1/3,places=5)
        self.assertAlmostEqual(hit['normal'][2],1.)

    def test_thin_wall_blocks_high_speed_motion_with_clear_endpoints(self):
        hit=sweep_capsule([-100,0,50],[200,0,0],10,2,[WALL])
        self.assertAlmostEqual(hit['fraction'],.49,places=5)
        self.assertAlmostEqual(hit['normal'][0],-1.)

    def test_motion_tangent_to_touching_wall_is_not_blocked(self):
        self.assertIsNone(sweep_capsule([-2,0,30],[0,20,0],10,2,[WALL]))

    def test_motion_away_from_touching_wall_is_not_blocked(self):
        self.assertIsNone(sweep_capsule([-2,0,30],[-20,0,0],10,2,[WALL]))

    def test_sliding_keeps_tangential_displacement(self):
        result,hits=move_capsule([-5,0,30],[10,20,0],10,2,lambda *args:[WALL])
        self.assertLessEqual(result[0],-2.)
        self.assertGreaterEqual(result[0],-2.001)
        self.assertAlmostEqual(result[1],20.,places=3)
        self.assertTrue(hits)

    def test_corner_blocks_both_inward_axes(self):
        other=tuple((p[1],p[0],p[2]) for p in WALL)
        result,hits=move_capsule([-5,-5,30],[10,10,0],10,2,lambda *args:[WALL,other])
        for value in result[:2]:
            self.assertLessEqual(value,-2.)
            self.assertGreaterEqual(value,-2.001)
        self.assertGreaterEqual(len(hits),2)

    def test_capsule_top_blocks_jump_into_ceiling(self):
        ceiling=tuple((x,y,150.) for x,y,z in FLOOR)
        hit=sweep_capsule([0,0,96],[0,0,100],40,10,[ceiling])
        self.assertAlmostEqual(hit['fraction'],.14,places=5)
        self.assertLess(hit['normal'][2],-.99)

    def test_landscape_holes_emit_no_collision_triangles(self):
        tile=Heightfield(2,2,(0,0,0),(100,100,1),0,1,struct.pack('<4H',0,0,0,0),b'\xff')
        self.assertEqual(list(tile.triangles([0,0],[100,100])),[])

    def test_native_diagonal_and_world_height_are_preserved(self):
        tile=Heightfield(2,2,(10,20,30),(100,100,2),0,1,struct.pack('<4H',0,1,2,3),b'\x00')
        triangles=list(tile.triangles([10,20],[110,120]))
        self.assertEqual(triangles[0],((10,20,30),(110,20,32),(110,120,36)))
        self.assertEqual(triangles[1],((10,20,30),(110,120,36),(10,120,34)))
