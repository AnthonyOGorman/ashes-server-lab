"""Apply the existing fixed, fresh-proof-bound stages to one joined local world.

Does not launch/restart the game, click Play, send movement, or claim success.
Every one-shot must be observed consumed before advancing to the next stage.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_proof import client_proof, EXPECTED_EXE
from refresh_world_proofs import refresh
from inspect_player_state import inspect as inspect_actors
from inspect_stats_receiver import inspect as inspect_receiver
from inspect_stats_mapping import inspect as inspect_mapping
from inspect_class_net_arrays import inspect as inspect_arrays
from inspect_driver_net_cache import inspect as inspect_cache
from create_client_restart_experiment import command

ROOT = Path(__file__).resolve().parents[1]


def control(action):
    req=urllib.request.Request('http://127.0.0.1:8765/api/control',
        data=json.dumps({'action':action}).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        result=json.load(response)
    if result.get('ok') is not True:
        raise ValueError(result)


def wait_stats_delegate(pid, actor_path, receiver_path, timeout=15.):
    """BeginPlay queues native initialization; require readback before stats."""
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        observed=inspect_mapping(pid,actor_path,receiver_path)
        if int(observed['delegate_wrapper'],16)!=0:
            return observed
        time.sleep(.1)
    raise ValueError('Native stat delegate did not initialize after BeginPlay')


def initialize(pid, port):
    db=sqlite3.connect(f'file:{ROOT / "data/lab.sqlite"}?mode=ro', uri=True)
    def save(stem, data):
        data['pid']=pid;data['client_proof']=client_proof(pid)
        path=ROOT/'evidence'/f'{stem}_{pid}.json'
        path.write_text(json.dumps(data,indent=2),encoding='utf-8')
        return path
    def actors():
        return save('player_state_world',inspect_actors(pid,EXPECTED_EXE))
    def dispatch(operation):
        value=command('127.0.0.1',port,pid,operation)
        last=db.execute('select max(id) from events').fetchone()[0] or 0
        path=ROOT/'data/client-restart-experiment.json';tmp=path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(value,indent=2),encoding='utf-8');tmp.replace(path)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            for row_id,kind,raw in db.execute('select id,kind,detail from events where id>? order by id',(last,)):
                last=row_id
                if kind not in ('client_restart_experiment_consumed','client_restart_experiment_rejected'):
                    continue
                detail=json.loads(raw)
                if detail.get('id')==value['id']:
                    if kind.endswith('rejected'):raise ValueError(detail)
                    print('consumed '+operation,flush=True)
                    return
            time.sleep(.1)
        raise ValueError('No verified consumption of '+operation)
    try:
        control('controller_bootstrap');control('scene_bootstrap')
        try:
            refresh(pid)
        except ValueError as error:
            if str(error)!='Fresh accepted mutual possession and clean actor/layout proof required':raise
        dispatch('ClientSetHUD');actors();dispatch('ClientRestart')
        refresh(pid);dispatch('PawnAutonomous');refresh(pid)
        actor_path=ROOT/'evidence'/f'player_state_world_{pid}.json'
        receiver=save('stats_receiver',inspect_receiver(pid,actor_path))
        dispatch('StatsComponentExport')
        # Export creates the current native cache/layout for this exact class.
        arrays=save('stats_class_net_arrays',inspect_arrays(ROOT/'evidence'/f'runtime_stats_reflection_{pid}.json'))
        save('stats_driver_net_cache',inspect_cache(arrays))
        # Export while gameplay is unstarted, then initialize the native
        # stat delegate through BeginPlay. Apply gravity immediately after
        # readback instead of delaying it behind a full reflection refresh.
        dispatch('GameStateBeginPlay')
        save('stats_mapping',wait_stats_delegate(pid,actor_path,receiver))
        dispatch('StatsGravity')
        receiver=save('stats_receiver',inspect_receiver(pid,actor_path))
        save('stats_mapping',inspect_mapping(pid,actor_path,receiver))
        dispatch('StatsSpeed')
        life=refresh(pid)
        if life['begun_play'] is not True:raise ValueError('Actual BeginPlay required')
        report={'pid':pid,'pawn':life['pawn'],'controller':life['controller'],
                'stages_consumed':True,'stats_exported_before_begin_play':True,
                'movement_verified':False}
        print(json.dumps(report),flush=True)
        return report
    finally:
        db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',type=int,required=True);p.add_argument('--port',type=int,required=True)
    a=p.parse_args()
    if not 0<a.port<=65535:p.error('Valid local peer port required')
    initialize(a.pid,a.port)
