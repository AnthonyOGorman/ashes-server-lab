import json
import math
from pathlib import Path
import unittest

from tools.reconstruct_cooked_support import support_surface, validate_support_surface
from tools.export_cooked_convex import validated_surface
from tests.test_static_collision import box
from lab.static_collision import from_export


class CookedSupportTests(unittest.TestCase):
    def test_captured_support_fallback_loads_with_native_world_transform(self):
        fixture=json.loads((Path(__file__).parent / 'fixtures/native_brazier_support.json').read_text())
        vertices=fixture['vertices'];indices=support_surface(vertices)
        identity={'rotation':[0,0,0,1],'translation':[0,0,0],'scale':[1,1,1]}
        cooked={'layout':'native-chaos-support-v1','vertices':vertices,'indices':indices,
                'planes':fixture['planes']}
        report={'components':[{'identity':{'address':'captured'},'asset':'mesh',
            'response':{'collision_enabled':3,'pawn_response':2},'instances':[],
            'native_component_transform':dict(identity,translation=[100,200,300])}],
            'assets':{'mesh':{'collision_trace_flag':1,'shapes':[{'type':'KConvexElem',
                'Transform':identity,'VertexData':vertices,'IndexData':indices[:-3],
                'CookedGeometry':cooked}]}}}
        colliders,unsupported=from_export(report)
        self.assertEqual(unsupported,[])
        self.assertEqual(len(colliders),1)
        self.assertEqual(colliders[0].minimum,[min(v[i] for v in vertices)+[100,200,300][i] for i in range(3)])
        cooked['indices']=indices[:-3]
        colliders,unsupported=from_export(report)
        self.assertEqual(colliders,[])
        self.assertIn('closed',unsupported[0]['reason'])

    def test_native_nonplanar_polygon_preserves_vertex_support(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/native_brazier_support.json').read_text())
        vertices = fixture['vertices']
        with self.assertRaises(ValueError):
            validated_surface(vertices, fixture['planes'])
        indices = support_surface(vertices)
        collider = validate_support_surface(vertices, indices)
        corners = [v for triangle, _ in collider.faces for v in triangle]
        # Directions cover every quadrant and a dense spherical distribution.
        # Compare actual surface support with the native all-vertex selection.
        for i in range(1000):
            z = 1 - 2 * (i + .5) / 1000
            angle = i * math.pi * (3 - math.sqrt(5))
            radius = math.sqrt(1 - z * z)
            direction = [radius * math.cos(angle), radius * math.sin(angle), z]
            support = lambda points: max(sum(a*b for a,b in zip(v, direction)) for v in points)
            self.assertAlmostEqual(support(vertices), support(corners), places=9)

    def test_closed_surface_omitting_native_extreme_point_is_rejected(self):
        vertices, indices = box([0, 0, 0], [10, 20, 30])
        # Below the old generic .05cm face tolerance, but still changes support.
        vertices.append([10.01, 10, 15])
        with self.assertRaisesRegex(ValueError, 'contain all native support'):
            validate_support_surface(vertices, indices)
        validate_support_surface(vertices, support_surface(vertices))

    def test_invalid_or_open_support_surfaces_are_rejected(self):
        vertices, indices = box([0, 0, 0], [10, 20, 30])
        with self.assertRaisesRegex(ValueError, 'closed'):
            validate_support_surface(vertices, indices[:-3])
        with self.assertRaisesRegex(ValueError, 'finite'):
            support_surface(vertices + [[float('nan'), 0, 0]])
        with self.assertRaisesRegex(ValueError, 'nondegenerate'):
            support_surface([[0,0,0], [1,0,0], [1,1,0], [0,1,0]])
