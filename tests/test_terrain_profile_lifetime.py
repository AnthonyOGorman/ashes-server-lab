import unittest
from types import SimpleNamespace
from lab.terrain_movement_experiment import profile_active, current_generation_moves


class TerrainProfileLifetimeTests(unittest.TestCase):
    def test_previous_clock_pending_moves_cannot_poison_new_generation(self):
        new={'kind':'new','timestamp':.08}
        pending={'kind':'pending','timestamp':.05}
        old={'kind':'old','timestamp':239.97}
        self.assertEqual(current_generation_moves([old,pending,new]),[pending,new])

    def test_normal_pending_moves_are_retained(self):
        moves=[{'kind':'old','timestamp':10.0},{'kind':'pending','timestamp':10.1},
               {'kind':'new','timestamp':10.2}]
        self.assertEqual(current_generation_moves(moves),moves)

    def setup_profile(self, mode='connection-landscape-locomotion-v1'):
        config={'mode':mode,'id':'trial','peer':['127.0.0.1',1234],
                'connection_id':'world','pawn_guid':{'id':1},'expires_at':120.}
        connection=SimpleNamespace(phase='joined',connection_id='world',
                actor_guids={'pawn':{'id':1}},possession_acknowledged=True)
        return connection,config,('127.0.0.1',1234)

    def activate(self, c, p):
        c.terrain_experiment=object()
        c.terrain_experiment_id=p['id']
        c.terrain_experiment_config=dict(p)

    def test_activation_deadline_cannot_start_expired_authority(self):
        c,p,peer=self.setup_profile()
        self.assertTrue(profile_active(c,p,peer,1.))
        self.assertFalse(profile_active(c,p,peer,121.))

    def test_connected_authority_survives_two_minute_deadline(self):
        c,p,peer=self.setup_profile();self.activate(c,p)
        self.assertTrue(profile_active(c,p,peer,3600.))

    def test_bounded_trial_still_expires(self):
        c,p,peer=self.setup_profile('bounded-landscape-locomotion-v1');self.activate(c,p)
        self.assertFalse(profile_active(c,p,peer,121.))

    def test_closed_or_repossessed_connection_cannot_reuse_authority(self):
        for change in ('closed','pawn','possession','connection'):
            c,p,peer=self.setup_profile();self.activate(c,p)
            if change=='closed':c.phase='closed'
            if change=='pawn':c.actor_guids['pawn']={'id':2}
            if change=='possession':c.possession_acknowledged=False
            if change=='connection':c.connection_id='new-world'
            self.assertFalse(profile_active(c,p,peer,3600.))

    def test_changed_configuration_requires_fresh_validation(self):
        c,p,peer=self.setup_profile();self.activate(c,p)
        p['spawn']=[0,0,100]
        self.assertFalse(profile_active(c,p,peer,3600.))
        self.assertFalse(profile_active(c,p,('127.0.0.1',5678),1.))
