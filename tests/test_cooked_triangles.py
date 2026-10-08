import unittest

from tools.export_cooked_triangles import validate_buffers


class CookedTriangleValidationTests(unittest.TestCase):
    vertices=[[0,0,0],[10,0,0],[0,10,0],[0,0,10]]
    triangles=[[0,2,1],[0,1,3],[0,3,2],[1,2,3]]
    bounds=[0,0,0,10,10,10]

    def test_closed_oriented_tetrahedron_and_open_surface_are_distinguished(self):
        closed=validate_buffers(self.vertices,self.triangles,self.bounds)
        self.assertTrue(closed['closed_oriented_surface'])
        self.assertEqual(closed['oppositely_oriented_edges'],6)
        opened=validate_buffers(self.vertices,self.triangles[:-1],self.bounds)
        self.assertFalse(opened['closed_oriented_surface']);self.assertEqual(opened['boundary_edges'],3)

    def test_bad_winding_and_nonmanifold_faces_cannot_claim_a_solid(self):
        wrong=[list(reversed(self.triangles[0])),*self.triangles[1:]]
        self.assertFalse(validate_buffers(self.vertices,wrong,self.bounds)['closed_oriented_surface'])
        duplicate=validate_buffers(self.vertices,self.triangles+[self.triangles[0]],self.bounds)
        self.assertFalse(duplicate['closed_oriented_surface']);self.assertEqual(duplicate['nonmanifold_edges'],3)

    def test_invalid_native_bounds_indices_and_vertices_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'bounds disagree'):
            validate_buffers(self.vertices,self.triangles,[0,0,0,100,10,10])
        with self.assertRaisesRegex(ValueError,'index outside'):
            validate_buffers(self.vertices,[[0,1,4]],self.bounds)
        with self.assertRaisesRegex(ValueError,'finite'):
            validate_buffers([[float('nan'),0,0],*self.vertices[1:]],self.triangles,self.bounds)
