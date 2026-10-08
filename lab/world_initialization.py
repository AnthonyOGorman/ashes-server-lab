"""Opt-in entry initialization using the existing proof-bound local tools."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'data/auto-world-initialize.json'


def read_config():
    if not CONFIG.exists():return None
    value=json.loads(CONFIG.read_text())
    if set(value)!={'enabled','pid','sha256'} or value['enabled'] is not True:
        return None
    if type(value['pid']) is not int or value['pid']<=0 or not isinstance(value['sha256'],str):
        raise ValueError('exact local-client initialization configuration required')
    return value


def ready_entry(owner,config):
    """A loaded, accepted, single loopback world belonging to the configured client."""
    client=owner.client
    if client is None or client.poll() is not None or client.pid!=config['pid']:
        return None
    if owner.inventory['sha256']!=config['sha256'] or not owner.world_active or owner.world is None:
        return None
    milestone=owner.milestones.get('world_loaded',{})
    if milestone.get('status')!='passed' or milestone.get('world_epoch')!=owner.world_epoch:
        return None
    with owner.world.protocol_lock:
        joined=[(peer,c) for peer,c in owner.world.protocol.connections.items() if c.phase=='joined']
        if len(joined)!=1:return None
        peer,connection=joined[0]
        if peer[0]!='127.0.0.1' or connection.connection_id!=owner.world_connection_id:
            return None
        initialized=(getattr(connection,'gravity_stat_supplied',False) and
                     getattr(connection,'speed_stat_supplied',False) and
                     getattr(connection,'terrain_experiment',None) is not None and
                     connection.possession_acknowledged)
        return {'pid':client.pid,'port':peer[1],'connection_id':connection.connection_id,
                'epoch':owner.world_epoch,'initialized':bool(initialized),
                'bootstrap_started':bool(getattr(connection,'bootstrap_sent',False))}


def still_current(owner,entry):
    return (owner.world_active and owner.world_epoch==entry['epoch'] and
            owner.world_connection_id==entry['connection_id'] and
            owner.client is not None and owner.client.pid==entry['pid'] and
            owner.client.poll() is None)


def run_stage(owner,entry,name,arguments,directory,timeout=240.):
    config=read_config()
    if (not config or config['pid']!=entry['pid'] or
            config['sha256']!=owner.inventory['sha256'] or not still_current(owner,entry)):
        raise ValueError('Current configured world required before starting initialization stage')
    path=directory/(name+'.log')
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    with path.open('w',encoding='utf-8') as output:
        child=subprocess.Popen([sys.executable,*arguments],cwd=ROOT,stdout=output,
                               stderr=subprocess.STDOUT,creationflags=flags)
        deadline=time.monotonic()+timeout
        try:
            while child.poll() is None:
                config=read_config()
                if (not config or config['pid']!=entry['pid'] or
                        config['sha256']!=owner.inventory['sha256'] or not still_current(owner,entry)
                        or time.monotonic()>=deadline):
                    raise ValueError('Initialization cancelled, world changed, or stage timed out')
                progress=getattr(owner,'stage_progress',None)
                if progress is not None:
                    progress(entry,name,arguments,directory)
                time.sleep(.25)
            if child.returncode!=0:
                raise ValueError(f'{name} failed; inspect {path}')
            progress=getattr(owner,'stage_progress',None)
            if progress is not None:
                progress(entry,name,arguments,directory)
        finally:
            if child.poll() is None:
                child.terminate();child.wait(timeout=10)
    return path


def initialize_entry(owner,entry):
    directory=ROOT/'evidence'/f'auto_entry_epoch{entry["epoch"]}_{entry["connection_id"]}'
    directory.mkdir(parents=True,exist_ok=True)
    pid=str(entry['pid']);port=str(entry['port'])
    init_log=run_stage(owner,entry,'character',[
        'tools/initialize_joined_character.py','--pid',pid,'--port',port],directory)
    lines=init_log.read_text().splitlines()
    result=next((json.loads(line) for line in reversed(lines) if line.startswith('{')),None)
    if not result or not result.get('stages_consumed'):
        raise ValueError('Verified character initialization report required')
    collision=ROOT/'evidence'/f'static_collision_epoch{entry["epoch"]}_{pid}.json'
    run_stage(owner,entry,'collision',['tools/export_static_collision.py','--pid',pid,
        '--pawn',result['pawn'],'--centre','0','0','0','--all-loaded','--output',str(collision)],directory)
    run_stage(owner,entry,'terrain',['tools/activate_terrain_authority.py','--pid',pid,
        '--port',port,'--connection',entry['connection_id'],'--epoch',str(entry['epoch']),
        '--static-collision',str(collision)],directory)
    profile=json.loads((ROOT/'data/terrain-movement-experiment.json').read_text())
    if profile['connection_id']!=entry['connection_id'] or not still_current(owner,entry):
        raise ValueError('Current initialized world profile required')
    summary={**entry,'pawn':result['pawn'],'stages_consumed':True,
             'profile_id':profile['id'],'movement_verified':False}
    (directory/'result.json').write_text(json.dumps(summary,indent=2))
    return summary


def worker(owner):
    attempted=set()
    while True:
        entry=None
        try:
            config=read_config()
            if not config:return
            entry=ready_entry(owner,config)
            if entry and entry['connection_id'] not in attempted:
                attempted.add(entry['connection_id'])
                if entry['initialized']:
                    owner.event('auto_world_initialization_retained',entry)
                elif entry['bootstrap_started']:
                    raise ValueError('Manual or partial initialization already started; no duplicate bootstrap sent')
                else:
                    owner.event('auto_world_initialization_started',entry)
                    result=initialize_entry(owner,entry)
                    owner.event('auto_world_initialization_completed',result)
        except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:
            owner.event('auto_world_initialization_failed',{
                'connection_id':entry['connection_id'] if entry else None,'reason':str(exc)})
            if entry is None:return
        time.sleep(1.)


def ensure_worker(owner):
    if owner is None or not all(hasattr(owner,name) for name in
                               ('world_active','world_epoch','client','inventory','milestones')):
        return None
    if read_config() is None:return None
    existing=getattr(owner,'world_initialization_thread',None)
    if existing is not None and existing.is_alive():return existing
    thread=threading.Thread(target=worker,args=(owner,),name='local-world-initialization',daemon=True)
    owner.world_initialization_thread=thread
    thread.start()
    return thread
