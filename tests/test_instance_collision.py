import copy
import math
import unittest

from lab.static_collision import from_export,instance_point
from lab.terrain_movement import TerrainMovement
from tests.test_static_collision import terrain,move


def matrix(scale=1,translation=(0,0,0)):
    return [scale,0,0,0,0,scale,0,0,0,0,scale,0,*translation,1]


def report():
    transform={'rotation':[0,0,0,1],'translation':[0,0,0],'scale':[1,1,1]}
    return {'components':[{'identity':{'address':'instance'},'asset':'mesh','mobility':0,
        'response':{'collision_enabled':3,'pawn_response':2},'native_component_transform':transform,
        'instance_transform_proof':'native-uniform-instance-transform-v1',
        'instances':[{'index':0,'matrix':matrix(1,(150,150,100))},
                     {'index':1,'matrix':matrix(1,(250,150,100))}]}],
        'assets':{'mesh':{'collision_trace_flag':2,'shapes':[{'type':'KBoxElem','index':0,
            'CollisionEnabled':3,'Center':[0,0,0],'Rotation':[0,0,0],'X':20,'Y':100,'Z':200}]}}}


class InstanceCollisionTests(unittest.TestCase):
    def test_composes_instance_then_component_rotation_translation_and_scale(self):
        r=report();c=r['components'][0];c['native_component_transform']={
            'rotation':[0,0,math.sqrt(.5),math.sqrt(.5)],'translation':[100,200,0],'scale':[3,3,3]}
        c['instances']=[{'index':0,'matrix':matrix(2,(50,0,0))}]
        shape=r['assets']['mesh']['shapes'][0];shape.update(X=10,Y=20,Z=30)
        meshes,unsupported=from_export(r)
        self.assertEqual(unsupported,[]);self.assertEqual(len(meshes),1)
        for actual,expected in zip(meshes[0].minimum,[40,320,-90]):self.assertAlmostEqual(actual,expected)
        for actual,expected in zip(meshes[0].maximum,[160,380,90]):self.assertAlmostEqual(actual,expected)

    def test_both_instances_block_capsule_movement_as_distinct_solids(self):
        meshes,unsupported=from_export(report());self.assertEqual(unsupported,[])
        self.assertEqual(len(meshes),2)
        self.assertTrue(meshes[0].contains_point([150,150,100]))
        self.assertFalse(meshes[1].contains_point([150,150,100]))
        state=TerrainMovement([terrain()],[50,150,12],speed=996,half_height=10,radius=2,
                              floor_clearance=2,static_meshes=meshes)
        state.advance(move(0),0)
        for i in range(1,11):state.advance(move(i*.05,acceleration=(8192,0,0)),i*.05)
        self.assertAlmostEqual(state.position[0],138,delta=.01)
        self.assertEqual(state.mode,1)

    def test_instanced_complex_concave_mesh_keeps_notch_and_blocks_wall(self):
        from tests.test_triangle_collision import concave_solid
        vertices,triangles=concave_solid();r=report();c=r['components'][0]
        c['instances']=[{'index':0,'matrix':matrix(1,(100,100,0))},
                        {'index':1,'matrix':matrix(1,(300,100,0))}]
        r['assets']['mesh']={'collision_trace_flag':3,'shapes':[],
            'CookedTriangles':[{'layout':'native-chaos-triangles16-v1','vertices':vertices,
                'triangles':triangles,'bounds':[0,0,0,100,100,100]}]}
        meshes,errors=from_export(r);self.assertEqual(errors,[]);self.assertEqual(len(meshes),2)
        self.assertTrue(meshes[0].contains_point([120,120,50]))
        self.assertFalse(meshes[0].contains_point([160,160,50]))
        self.assertTrue(meshes[1].contains_point([320,120,50]))
        state=TerrainMovement([terrain()],[160,160,12],speed=996,half_height=10,radius=2,
                              floor_clearance=2,static_meshes=meshes)
        state.advance(move(0),0)
        for i in range(1,11):state.advance(move(i*.05,acceleration=(-8192,0,0)),i*.05)
        self.assertAlmostEqual(state.position[0],142,delta=.01)
        self.assertEqual(state.mode,1)

    def test_unverified_moving_sheared_nonuniform_and_mirrored_instances_fail_closed(self):
        for kind in ('proof','moving','shear','nonuniform','mirror','affine','nan'):
            r=report();c=r['components'][0];m=c['instances'][1]['matrix']
            if kind=='proof':c.pop('instance_transform_proof')
            if kind=='moving':c['mobility']=1
            if kind=='shear':m[1]=.2
            if kind=='nonuniform':m[0]=2
            if kind=='mirror':m[0]=-1
            if kind=='affine':m[3]=1
            if kind=='nan':m[0]=float('nan')
            meshes,unsupported=from_export(r)
            self.assertEqual(meshes,[],kind);self.assertTrue(unsupported,kind)
