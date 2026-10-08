import threading
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lab.world_initialization import ready_entry,still_current,run_stage


class WorldInitializationTests(unittest.TestCase):
    def test_stage_progress_runs_while_owned_export_child_is_still_running(self):
        owner,connection,config=self.fixture();entry=ready_entry(owner,config)
        class Child:
            returncode=None
            def poll(self):return self.returncode
            def terminate(self):self.returncode=-15
            def wait(self,timeout):return self.returncode
        child=Child();observed=[]
        def progress(*args):
            observed.append(child.poll())
            child.returncode=0
        owner.stage_progress=progress
        with patch('lab.world_initialization.read_config',return_value=config),\
             patch('lab.world_initialization.subprocess.Popen',return_value=child),\
             patch('lab.world_initialization.time.sleep'):
            with tempfile.TemporaryDirectory() as directory:
                run_stage(owner,entry,'export',['export.py'],Path(directory))
        self.assertEqual(observed,[None,0])

    def fixture(self):
        client=SimpleNamespace(pid=123,poll=lambda:None)
        connection=SimpleNamespace(phase='joined',connection_id='entry',bootstrap_sent=False,
                                   possession_acknowledged=False)
        world=SimpleNamespace(protocol_lock=threading.RLock(),
            protocol=SimpleNamespace(connections={('127.0.0.1',456):connection}))
        owner=SimpleNamespace(client=client,inventory={'sha256':'build'},world_active=True,
            world=world,world_epoch=3,world_connection_id='entry',
            milestones={'world_loaded':{'status':'passed','world_epoch':3}})
        return owner,connection,{'enabled':True,'pid':123,'sha256':'build'}

    def test_fresh_single_loaded_loopback_world_is_selected(self):
        owner,connection,config=self.fixture()
        result=ready_entry(owner,config)
        self.assertEqual(result['port'],456);self.assertFalse(result['initialized'])
        self.assertTrue(still_current(owner,result))

    def test_existing_verified_initialization_is_retained(self):
        owner,connection,config=self.fixture()
        connection.gravity_stat_supplied=connection.speed_stat_supplied=True
        connection.terrain_experiment=object();connection.possession_acknowledged=True
        self.assertTrue(ready_entry(owner,config)['initialized'])

    def test_stale_world_load_wrong_client_and_foreign_peer_are_rejected(self):
        for change in ('epoch','pid','build','closed','peer','extra'):
            owner,connection,config=self.fixture()
            if change=='epoch':owner.milestones['world_loaded']['world_epoch']=2
            if change=='pid':config['pid']=124
            if change=='build':config['sha256']='other'
            if change=='closed':owner.world_active=False
            if change=='peer':owner.world.protocol.connections={('192.0.2.1',456):connection}
            if change=='extra':owner.world.protocol.connections[('127.0.0.1',457)]=connection
            self.assertIsNone(ready_entry(owner,config),change)

    def test_departure_or_replacement_cancels_owned_initialization(self):
        owner,connection,config=self.fixture();entry=ready_entry(owner,config)
        owner.world_active=False;self.assertFalse(still_current(owner,entry))
        owner.world_active=True;owner.world_connection_id='replacement'
        self.assertFalse(still_current(owner,entry))

    def test_replaced_world_never_starts_a_stage_process(self):
        owner,connection,config=self.fixture();entry=ready_entry(owner,config)
        owner.world_connection_id='replacement'
        with patch('lab.world_initialization.read_config',return_value=config):
            with patch('lab.world_initialization.subprocess.Popen') as process:
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(ValueError,'Current configured world'):
                        run_stage(owner,entry,'test',['script.py'],Path(directory))
                process.assert_not_called()

    def test_stage_cancellation_stops_only_its_owned_child(self):
        owner,connection,config=self.fixture();entry=ready_entry(owner,config)
        class Child:
            returncode=None
            stopped=False
            def poll(self):
                owner.world_active=False
                return self.returncode
            def terminate(self):self.stopped=True;self.returncode=-15
            def wait(self,timeout):return self.returncode
        child=Child()
        with patch('lab.world_initialization.read_config',return_value=config):
            with patch('lab.world_initialization.subprocess.Popen',return_value=child):
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(ValueError,'world changed'):
                        run_stage(owner,entry,'test',['script.py'],Path(directory))
        self.assertTrue(child.stopped)
