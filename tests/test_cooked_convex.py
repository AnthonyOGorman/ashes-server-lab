import unittest

from tools.export_cooked_convex import validated_surface
from lab.static_collision import from_export
from tests.test_static_collision import box


class CookedConvexTests(unittest.TestCase):
    def test_fallback_requires_valid_planes_and_applies_world_transform(self):
        vertices,indices=box([0,0,0],[10,20,30])
        planes=[[0,0,0,-1,0,0],[10,0,0,1,0,0],
                [0,0,0,0,-1,0],[0,20,0,0,1,0],
                [0,0,0,0,0,-1],[0,0,30,0,0,1]]
        identity={'rotation':[0,0,0,1],'translation':[0,0,0],'scale':[1,1,1]}
        cooked={'layout':'native-chaos-convex-v1','vertices':vertices,
                'indices':indices,'planes':planes}
        report={'components':[{'identity':{'address':'component'},'asset':'mesh',
            'response':{'collision_enabled':3,'pawn_response':2},'instances':[],
            'native_component_transform':dict(identity,translation=[100,200,300])}],
            'assets':{'mesh':{'collision_trace_flag':1,'shapes':[{'type':'KConvexElem',
                'Transform':identity,'VertexData':vertices,'IndexData':indices[:-3],
                'CookedGeometry':cooked}]}}}
        colliders,unsupported=from_export(report)
        self.assertEqual(unsupported,[]);self.assertEqual(len(colliders),1)
        self.assertEqual(colliders[0].minimum,[100,200,300])
        self.assertEqual(colliders[0].maximum,[110,220,330])
        cooked['planes']=planes[:-1]
        colliders,unsupported=from_export(report)
        self.assertEqual(colliders,[])
        self.assertIn('matching native plane',unsupported[0]['reason'])

    def test_surface_must_match_all_native_planes(self):
        vertices,_=box([0,0,0],[10,20,30])
        planes=[[0,0,0,-1,0,0],[10,0,0,1,0,0],
                [0,0,0,0,-1,0],[0,20,0,0,1,0],
                [0,0,0,0,0,-1],[0,0,30,0,0,1]]
        self.assertEqual(len(validated_surface(vertices,planes)),36)
        with self.assertRaisesRegex(ValueError,'matching native plane'):
            validated_surface(vertices,planes[:-1])
        with self.assertRaisesRegex(ValueError,'outside native'):
            validated_surface(vertices+[[100,100,100]],planes)
        with self.assertRaisesRegex(ValueError,'missing from reconstructed'):
            validated_surface(vertices,planes+[[100,0,0,1,0,0]])

    def test_malformed_native_geometry_cannot_be_triangulated(self):
        vertices,_=box([0,0,0],[10,20,30])
        planes=[[0,0,0,-1,0,0],[10,0,0,1,0,0],
                [0,0,0,0,-1,0],[0,20,0,0,1,0],
                [0,0,0,0,0,-1],[0,0,30,0,0,1]]
        with self.assertRaisesRegex(ValueError,'unit native'):
            validated_surface(vertices,planes[:-1]+[[0,0,30,0,0,2]])
        with self.assertRaisesRegex(ValueError,'finite cooked'):
            validated_surface(vertices+[[float('nan'),0,0]],planes)
        with self.assertRaisesRegex(ValueError,'nondegenerate cooked'):
            validated_surface([[0,0,0],[10,0,0],[0,20,0],[10,20,0]],planes)
