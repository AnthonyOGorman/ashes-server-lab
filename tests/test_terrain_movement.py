import struct
import unittest
from lab.terrain import Heightfield
from lab.terrain_movement import TerrainMovement
from lab.movement_response import encode_move_correction_content
from lab.world_bootstrap import decode_actor_rpc_content
from lab.movement_serialization import decode_move_response_argument


def move(t,a=(0,0,0)):
    return {'timestamp':t,'acceleration':a,'compressed_flags':0}


class TerrainMovementTests(unittest.TestCase):
    def test_native_reset_can_follow_small_overshoot_without_new_time_allowance(self):
        s=self.system();s.advance(move(240.01007080078125),10)
        reset=move(.04);reset['kind']='new'
        result=s.advance(reset,10.04)
        self.assertTrue(result['timestamp_reset'])
        self.assertEqual(s.timestamp,.04)
        self.assertLessEqual(s.time_budget,.5)

    def test_late_reset_recovery_discards_gap_and_requires_elapsed_server_time(self):
        s=self.system();s.advance(move(240.01),10)
        reset=move(20.);reset['kind']='new'
        self.assertIsNone(s.advance(reset,11))
        before=s.position.copy()
        result=s.advance(reset,30)
        self.assertTrue(result['timestamp_reset'])
        self.assertIn('discarded_time',result)
        self.assertEqual(s.position,before)
        self.assertEqual(s.timestamp,20.)
        self.assertLessEqual(s.time_budget,.5)

    def system(self):
        tile=Heightfield(4,4,(0,0,0),(100,100,1),0,1,struct.pack('<16H',*([0]*16)),bytes(9))
        return TerrainMovement([tile],[150,150,97.99])

    def test_delayed_idle_then_movement_batch_keeps_wall_funded_input(self):
        s=self.system();s.advance(move(0),0)
        # A delayed idle packet and two movement packets arrive together.
        # Their total simulated time stays below real time already elapsed.
        idle=s.advance(move(.2),.36)
        first=s.advance(move(.275,(8192,0,0)),.367)
        second=s.advance(move(.35,(8192,0,0)),.375)
        for result in (idle,first,second):self.assertNotIn('discarded_time',result)
        self.assertGreater(s.position[0]-150,30)
        self.assertLessEqual(s.time_budget,.5)

    def test_input_advances_server_state_independent_of_client_location(self):
        s=self.system();s.advance(move(10),100)
        m=move(10.1,(8192,0,0));m['client_location']=[999999,999999,999999]
        result=s.advance(m,100.1)
        self.assertAlmostEqual(result['server_position'][0],172)
        self.assertAlmostEqual(result['server_position'][2],s.half_height)
        self.assertEqual(result['movement_mode'],1)

    def test_idle_brakes_and_stays_supported(self):
        s=self.system();s.advance(move(1),0);s.advance(move(1.1,(8192,0,0)),0.1)
        x=s.position[0];s.advance(move(1.2),0.2)
        self.assertAlmostEqual(s.position[0],x)

    def test_native_clock_reset_continues_gravity_without_new_time_budget(self):
        s=self.system();s.position[2]+=100;s.velocity[2]=-100
        s.advance(move(239.97305297851562),10)
        m=move(.0087890625);m['kind']='new'
        result=s.advance(m,10.036184310913086)
        self.assertTrue(result['timestamp_reset'])
        self.assertLess(s.position[2],197.99)
        self.assertLess(s.velocity[2],-100)
        self.assertNotIn('discarded_time',result)
        result=s.advance(move(.0587890625),10.086184310913086)
        self.assertNotIn('discarded_time',result)

    def test_old_move_or_arbitrary_rollback_cannot_reset_clock(self):
        s=self.system();s.advance(move(239.97),0)
        self.assertIsNone(s.advance(move(.01),.04))
        m=move(120);m['kind']='new'
        self.assertIsNone(s.advance(m,.04))
        self.assertEqual(s.timestamp,239.97)

    def test_missing_terrain_falls_with_gravity(self):
        s=self.system();s.position=[299,150,200];s.advance(move(1),0)
        result=s.advance(move(1.1,(8192,0,0)),0.1)
        self.assertEqual(result['movement_mode'],3)
        self.assertLess(result['server_position'][2],200)
        self.assertLess(result['server_velocity'][2],0)

    def test_swept_capsule_cannot_skip_thin_landscape_ridge(self):
        # Start and proposed endpoint have equal low floors; a tall ridge
        # between them must still block the whole fast movement interval.
        samples=struct.pack('<10H',0,0,200,0,0,0,0,200,0,0)
        tile=Heightfield(2,5,(0,0,0),(100,100,1),0,1,samples,b'\x00'*4)
        s=TerrainMovement([tile],[50,50,12],speed=1000,half_height=10,radius=2,floor_clearance=2)
        s.advance(move(0),0)
        result=s.advance(move(.25,(8192,0,0)),.25)
        self.assertLess(s.position[0],130)
        self.assertGreater(s.position[0],50)
        self.assertTrue(result['collision_hits'])
        self.assertAlmostEqual(s.velocity[0],0.)

    def test_timestamp_and_acceleration_abuse_rejected(self):
        s=self.system();s.advance(move(1),0)
        self.assertIsNone(s.advance(move(1),0.1))
        result=s.advance(move(2),1)
        self.assertEqual(result['delta'],[0,0,0])
        self.assertEqual(result['discarded_time'],1)
        with self.assertRaises(ValueError):s.advance(move(2.1,(999999,0,0)),1.1)

    def test_loss_recovers_without_simulating_discarded_time(self):
        s=self.system();s.advance(move(1),0)
        s.advance(move(1.3,(8192,0,0)),0.3)
        result=s.advance(move(1.4,(8192,0,0)),0.4)
        self.assertAlmostEqual(result['server_position'][0],172)

    def test_repeated_clock_lead_cannot_manufacture_movement(self):
        s=self.system();s.advance(move(1),0)
        for i in range(1,10):s.advance(move(1+i*0.2,(8192,0,0)),0)
        self.assertEqual(s.position,[150,150,97.99])

    def test_queued_history_recovers_and_idle_update_is_accepted(self):
        s=self.system();s.advance(move(1),0)
        for i in range(1,20):s.advance(move(1+i*.2),0)
        last=s.timestamp
        result=s.advance(move(last+.2),.2)
        self.assertNotIn('discarded_time',result)
        self.assertEqual(result['movement_mode'],1)

    def test_burst_cannot_spend_more_than_wall_time_allowance(self):
        s=self.system();s.advance(move(0),0)
        for i in range(1,100):s.advance(move(i*.05,(8192,0,0)),0)
        self.assertLessEqual(s.position[0]-150,220*.125+.001)

    def test_exact_ordinary_correction_roundtrip(self):
        for mode in (1,3):
            data,bits=encode_move_correction_content(12.25,[1,2,3],[4,5,6],mode)
            field=decode_actor_rpc_content(data,bits,198)['fields'][0]
            decoded=decode_move_response_argument(bytes.fromhex(field['argument_hex']),field['argument_bits'])
            self.assertEqual(field['field_index'],35)
            self.assertFalse(decoded['acknowledgement'])
            self.assertEqual(decoded['correction']['server_location'],[1,2,3])
            self.assertEqual(decoded['correction']['movement_mode'],mode)

    def test_jump_reaches_apex_and_lands_without_client_position(self):
        s=self.system();s.gravity=-1225.;s.advance(move(0),0)
        first=move(.05);first['compressed_flags']=1
        result=s.advance(first,.05)
        self.assertTrue(result['jump_started'])
        peak=s.position[2];falling_down=False
        for i in range(2,41):
            s.advance(move(i*.05),i*.05)
            peak=max(peak,s.position[2])
            falling_down|=s.mode==3 and s.velocity[2]<0
        self.assertGreater(peak,400)
        self.assertTrue(falling_down)
        self.assertEqual(s.mode,1)
        self.assertEqual(s.velocity[2],0)
        self.assertAlmostEqual(s.position[2],s.floor(150,150))

    def test_held_jump_does_not_repeat_after_landing(self):
        s=self.system();s.gravity=-1225.;s.advance(move(0),0)
        jumps=0
        for i in range(1,61):
            m=move(i*.05);m['compressed_flags']=1
            jumps+=s.advance(m,i*.05)['jump_started']
        self.assertEqual(jumps,1)
        self.assertEqual(s.mode,1)
        s.advance(move(3.05),3.05)
        m=move(3.1);m['compressed_flags']=1
        self.assertTrue(s.advance(m,3.1)['jump_started'])

    def test_interval_crossing_apex_hits_overhead_geometry(self):
        class RoofTile(Heightfield):
            def triangles(self, low, high):
                yield from super().triangles(low, high)
                yield ((100.,100.,10.), (200.,100.,10.), (200.,200.,10.))
                yield ((100.,100.,10.), (200.,200.,10.), (100.,200.,10.))
        tile=RoofTile(4,4,(0,0,0),(100,100,1),0,1,
                      struct.pack('<16H',*([0]*16)),bytes(9))
        s=TerrainMovement([tile],[150,150,2],half_height=2,radius=1,gravity=-1225.)
        s.velocity[2]=153.125
        s.advance(move(0),0)
        # The unchecked ballistic endpoint returns to z2, but the path's
        # apex would put the capsule through the roof between endpoints.
        result=s.advance(move(.25),.25)
        self.assertTrue(any(hit['normal'][2]<-.99 for hit in result['collision_hits']))
        self.assertLessEqual(s.position[2],8.001)
        self.assertLessEqual(s.velocity[2],0.)

    def test_large_accepted_interval_matches_short_physics_steps(self):
        coarse=self.system();fine=self.system()
        coarse.gravity=fine.gravity=-1225.
        coarse.advance(move(0),0);fine.advance(move(0),0)
        command=move(.25,(8192,0,0));command['compressed_flags']=1
        result=coarse.advance(command,.25)
        jumps=0
        for i in range(1,6):
            command=move(i*.05,(8192,0,0));command['compressed_flags']=1
            jumps+=fine.advance(command,i*.05)['jump_started']
        self.assertTrue(result['jump_started']);self.assertEqual(jumps,1)
        for actual,expected in zip(coarse.position+coarse.velocity,fine.position+fine.velocity):
            self.assertAlmostEqual(actual,expected)

    def test_simulation_step_is_bounded(self):
        tile=self.system().tiles[0]
        for value in (0,-1,float('nan'),.1):
            with self.assertRaises(ValueError):
                TerrainMovement([tile],[150,150,97.99],max_simulation_step=value)
