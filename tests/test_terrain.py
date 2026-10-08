import math
import struct
import unittest
from lab.terrain import Heightfield, highest_ground


def tile(values=(0,10,20,60), material=0):
    return Heightfield(2,2,(100,200,300),(100,100,2),0,1,
                       struct.pack('<4H',*values),bytes([material]))


class TerrainTests(unittest.TestCase):
    def test_triangle_diagonal_not_bilinear(self):
        self.assertAlmostEqual(tile().ground(175,225)['height'],340)
        self.assertAlmostEqual(tile().ground(125,275)['height'],350)
        self.assertAlmostEqual(tile().ground(150,250)['height'],360)

    def test_hole_never_supplies_ground(self):
        self.assertIsNone(tile(material=255).ground(150,250))

    def test_missing_and_boundary_never_extrapolate(self):
        for point in ((99,250),(200,250),(150,300),(150,199)):
            self.assertIsNone(tile().ground(*point))

    def test_slope_normal_is_unit_length(self):
        n=tile((0,10,0,10)).ground(150,250)['normal']
        self.assertAlmostEqual(sum(v*v for v in n),1)
        self.assertLess(n[0],0)
        self.assertAlmostEqual(n[1],0)

    def test_flat_floor_and_overlapping_tiles(self):
        a=tile((2,2,2,2));b=tile((3,3,3,3))
        self.assertEqual(highest_ground([a,b],150,250)['height'],306)
        self.assertIsNone(highest_ground([a,b],0,0))

    def test_invalid_binary_counts_rejected(self):
        with self.assertRaises(ValueError):
            Heightfield(2,2,(0,0,0),(1,1,1),0,1,b'\0',b'\0')
        with self.assertRaises(ValueError):
            tile().ground(math.nan,0)
