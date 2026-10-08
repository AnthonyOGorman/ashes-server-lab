from types import SimpleNamespace
import unittest

from tools.export_static_collision import CollisionProbe


class CollisionWorldOwnershipTests(unittest.TestCase):
    def fixture(self, owning):
        objects={1:{'class_address':'SceneComponent','outer_address':2},
                 2:{'class_address':'Actor','outer_address':3},
                 3:{'class_address':'Level','outer_address':4},
                 4:{'class_address':'World','outer_address':0},
                 5:{'class_address':'World','outer_address':0}}
        probe=CollisionProbe.__new__(CollisionProbe)
        probe.world_cache={}
        def identity(address, expected):
            self.assertEqual(objects[address]['class_address'], expected)
        probe.p=SimpleNamespace(reflection=SimpleNamespace(obj=lambda a:objects[a],class_name=lambda a:a),
            fields=lambda a,n:{'OwningWorld':{'status':'read','value':{'address':hex(owning)} if owning else None}},
            identity=identity)
        return probe

    def test_streamed_level_uses_gameplay_world_instead_of_package_world(self):
        probe=self.fixture(5)
        self.assertEqual(probe.world(1),5)
        self.assertEqual(probe.world(3),5)
        self.assertEqual(probe.world(4),4)

    def test_unattached_level_is_not_assigned_to_its_package_world(self):
        probe=self.fixture(None)
        self.assertIsNone(probe.world(1))
        self.assertIsNone(probe.world(3))

    def test_ordinary_runtime_world_ownership_is_preserved(self):
        probe=self.fixture(4)
        self.assertEqual(probe.world(1),4)
