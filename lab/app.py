import argparse
import json
import mimetypes
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .contracts import Contracts
from .lobby import Lobby, MAP, WORLD
from .storage import Store
from .udp_service import UdpService
from .tether import Tether, decode_tether
from .automation import Runner, WindowsDriver
from .automation import learn_template, resolve_template
from . import automation

ROOT = Path(__file__).resolve().parent.parent
GAME = Path(r'E:\Games\Steam Library\steamapps\common\Ashes of Creation\Game\AOC\Binaries\Win64\AOCClient-Win64-Shipping.exe')
MILESTONES = [('authentication','Authentication'),('lobby','Lobby'),('udp_handshake','UDP handshake'),
              ('welcome','Welcome'),('world_loaded','World loaded'),('player_spawned','Player spawned'),('movement','Movement')]
WORLD_MILESTONES = ('udp_handshake','welcome','world_loaded','player_spawned','movement')
DEFAULT_SCENARIO = {'name':'Login and walk','calibrated':False,'steps':[
    {'name':'Authentication','action':'wait_milestone','milestone':'authentication','timeout':45},
    {'name':'Enter realm','action':'click','x':-1,'y':-1},
    {'name':'Lobby','action':'wait_milestone','milestone':'lobby','timeout':20},
    {'name':'Play','action':'click','x':-1,'y':-1},
    {'name':'Server welcome','action':'wait_milestone','milestone':'welcome','timeout':30,'fresh':True},
    {'name':'World loaded','action':'wait_milestone','milestone':'world_loaded','timeout':60,'fresh':True},
    {'name':'Player spawned','action':'wait_milestone','milestone':'player_spawned','timeout':15,'fresh':True},
    {'name':'Walk forward','action':'key','key':'w','duration':1},
    {'name':'Movement confirmed','action':'wait_milestone','milestone':'movement','timeout':10,'fresh':True}]}


class Lab:
    def __init__(self):
        self.lock = threading.RLock()
        self.c = Contracts(ROOT/'evidence/client_contracts.pb')
        self.store = Store(ROOT/'data/lab.sqlite')
        self.inventory = json.loads((ROOT/'evidence/client_inventory.json').read_text(encoding='utf-8'))
        self.run_id = None
        self.lobby = self.tether = self.world = None
        self.client = None
        self.runner = None
        self.client_dir = None
        self.latest_screenshot = None
        self.importing = False
        self.screenshot_error = None
        self.driver = None
        self.background_driver = None
        self.attached_driver = None
        self.driver_mode = 'foreground'
        self.milestones = {}
        self.reset_milestones()
        self.scenario_path = ROOT/'data/scenario.json'
        if not self.scenario_path.exists():
            self.scenario_path.write_text(json.dumps(DEFAULT_SCENARIO,indent=2),encoding='utf-8')

    def reset_milestones(self):
        self.initialization_failure = None
        self.initialization_failures = []
        self.world_epoch = 0
        self.world_connection_id = None
        self.world_started_at = None
        self.world_active = False
        self.milestones = {key:{'id':key,'label':label,'status':'pending','detail':'',
                              'observed_at':None,'world_epoch':None} for key,label in MILESTONES}

    def reset_world_milestones(self, include_handshake=False):
        for key in WORLD_MILESTONES if include_handshake else WORLD_MILESTONES[1:]:
            self.milestones[key].update(status='pending',detail='',observed_at=None,
                                        world_epoch=self.world_epoch)

    def has_milestone(self,key,since=None):
        with self.lock:
            milestone = self.milestones.get(key,{})
            observed = milestone.get('observed_at')
            return (milestone.get('status')=='passed' and
                    (since is None or observed is not None and observed >= since))

    def event(self,kind,detail):
        with self.lock:
            observed_at = time.time()
            accept_milestone = True
            connection_id = detail.get('connection_id') if isinstance(detail,dict) else None
            if kind == 'udp_handshake':
                # The protocol emits this only for a validated new connection.
                # Replayed notifications for the same connection cannot refresh evidence.
                if connection_id and connection_id == self.world_connection_id:
                    accept_milestone = False
                else:
                    self.world_epoch += 1
                    self.world_connection_id = connection_id
                    self.world_started_at = observed_at
                    self.world_active = True
                    self.reset_world_milestones()
            elif kind in ('udp_connection_closed','world_return_detected'):
                if connection_id is None or connection_id == self.world_connection_id:
                    self.world_active = False
                    self.reset_world_milestones(include_handshake=True)
            elif kind in WORLD_MILESTONES:
                accept_milestone = self.world_active and (connection_id is None or connection_id == self.world_connection_id)
            if kind in WORLD_MILESTONES:
                event_detail = {'detail':detail,'observed_at':observed_at,'world_epoch':self.world_epoch,
                                'connection_id':self.world_connection_id,'accepted':accept_milestone}
            else:
                event_detail = detail
            event_run_id = detail.get('run_id',self.run_id) if isinstance(detail,dict) and kind in ('step_started','step_finished','run_finished','screenshot','visual_checkpoint','position_observation') else self.run_id
            self.store.execute('INSERT INTO events(ts,run_id,kind,detail) VALUES(?,?,?,?)',
                               (observed_at,event_run_id,kind,json.dumps(event_detail)))
            if kind in self.milestones and accept_milestone:
                self.milestones[kind].update(status='passed',detail=detail if isinstance(detail,str) else json.dumps(detail),
                                            observed_at=observed_at,
                                            world_epoch=self.world_epoch if kind in WORLD_MILESTONES else None)
            if kind == 'screenshot' and isinstance(detail,dict) and detail.get('path'):
                self.latest_screenshot = Path(detail['path'])
            if kind == 'run_finished' and isinstance(detail,dict):
                self.store.execute('UPDATE runs SET status=?,ended=?,detail=? WHERE id=?',
                     (detail['status'],time.time(),detail.get('reason') or '',detail.get('run_id',self.run_id)))

    def record(self,channel,direction,data,kind,decoded=None):
        self.store.packet(self.run_id,channel,direction,data,kind,decoded)

    def record_udp(self,channel,direction,data):
        try:
            if channel == 'tether': decoded = decode_tether(data)
            else:
                from .unreal import decode_packet
                decoded = decode_packet(data,direction='client' if direction=='C2S' else 'server')
            kind = decoded.get('kind') or decoded.get('type') or 'unknown'
        except Exception as exc:
            decoded,kind = {'error':str(exc)},'malformed'
        self.record(channel,direction,data,str(kind),decoded)

    def start_services(self):
        with self.lock:
            if self.lobby: return 'Services already running'
            from .unreal import WorldProtocol
            lobby = Lobby(self.c,self.store,self.record,self.event)
            tether = world = None
            try:
                lobby.start()
                tether = UdpService(0,Tether(self.c,15051,self.event),'tether',self)
                world = UdpService(17089,WorldProtocol(event=self.world_event),'world',self)
                tether.start()
                world.start()
            except Exception:
                lobby.stop()
                if tether: tether.stop()
                if world: world.stop()
                raise
            self.lobby,self.tether,self.world = lobby,tether,world
            return 'Lobby, launcher tether, and world listener are running locally'

    def world_event(self,kind,detail):
        if kind == 'welcome':
            # Sent Welcome is not proof the client accepted it; client stdout confirms it.
            self.event('welcome_sent',detail)
        else: self.event(kind,detail)

    def stop_services(self):
        if self.client and self.client.poll() is None:
            raise ValueError('Stop the client before stopping its services')
        with self.lock:
            for service in (self.world,self.tether,self.lobby):
                if service: service.stop()
            self.lobby=self.tether=self.world=None
        return 'Local services stopped'

    def controller_bootstrap(self):
        if not self.world:
            raise ValueError('Start the world listener first')
        with self.world.protocol_lock:
            protocol = self.world.protocol
            joined = [(addr,c) for addr,c in protocol.connections.items() if c.phase == 'joined']
            if len(joined) != 1:
                raise ValueError('This experiment requires exactly one joined local client')
            addr,connection = joined[0]
            if getattr(connection,'bootstrap_sent',False):
                raise ValueError('Controller bootstrap was already attempted; reconnect for another experiment')
            for packet in protocol._bootstrap(connection):
                self.world.sock.sendto(packet,addr)
                self.record_udp('world','S2C',packet)
            connection.bootstrap_sent = True
        self.event('controller_bootstrap_experiment',{'peer':str(addr),'evidence':'authored_controller_export_sent; client acceptance and possession unverified'})
        return 'Experimental controller sent. Inspect client logs; this does not confirm pawn spawn or movement.'

    def scene_bootstrap(self):
        if not self.world:
            raise ValueError('Start the world listener first')
        with self.world.protocol_lock:
            protocol = self.world.protocol
            joined = [(addr,c) for addr,c in protocol.connections.items() if c.phase == 'joined']
            if len(joined) != 1:
                raise ValueError('This experiment requires exactly one joined local client')
            addr,connection = joined[0]
            if not getattr(connection,'bootstrap_sent',False):
                raise ValueError('Attempt controller bootstrap first')
            if getattr(connection,'scene_sent',False):
                raise ValueError('Scene bootstrap was already attempted; reconnect for another experiment')
            for packet in protocol._bootstrap_scene(connection):
                self.world.sock.sendto(packet,addr)
                self.record_udp('world','S2C',packet)
            connection.scene_sent = True
        return 'Experimental GameState, pawn and PlayerState sent. Possession and movement are still unverified.'

    def reload_world_protocol(self):
        import hashlib
        import importlib
        from . import unreal, world_bootstrap, movement_rpc, movement_serialization, character_info_component
        if not self.world:
            raise ValueError('Start the world listener first')
        with self.world.protocol_lock:
            old = self.world.protocol
            importlib.reload(unreal)
            importlib.reload(world_bootstrap)
            importlib.reload(movement_rpc)
            importlib.reload(movement_serialization)
            importlib.reload(character_info_component)
            new = unreal.WorldProtocol(event=self.world_event,map_name=old.map_name,game_mode=old.game_mode)
            new.secret,new.connections = old.secret,old.connections
            self.world.protocol = new
        hashes = {name:hashlib.sha256((ROOT/'lab'/name).read_bytes()).hexdigest() for name in
                  ('unreal.py','world_bootstrap.py','movement_rpc.py','movement_serialization.py')}
        self.event('world_protocol_reloaded',{'source_sha256':hashes,'connections_preserved':len(new.connections)})
        return 'Updated local world parser and serializers loaded; connection state retained. Reconnect if channel layouts changed.'

    def reload_tester(self):
        import hashlib
        import importlib
        if self.runner and self.runner.snapshot()['status']=='running':
            raise ValueError('Stop the active test before reloading its driver')
        for driver in (self.driver,self.background_driver,self.attached_driver):
            if driver: driver.release_all()
        importlib.reload(automation)
        self.driver = automation.WindowsDriver(self.client.pid) if self.client and self.client.poll() is None else None
        self.background_driver = None
        self.attached_driver = None
        self.event('tester_reloaded',{'source_sha256':hashlib.sha256((ROOT/'lab/automation.py').read_bytes()).hexdigest()})
        return 'Updated local tester code loaded. The game process and global focus are unchanged.'

    def launch_client(self, world_probe=False):
        with self.lock:
            if self.client and self.client.poll() is None: return 'Client already running'
            self.start_services()
            if self.run_id:
                self.store.execute("UPDATE runs SET status='completed',ended=? WHERE id=? AND status='running'",(time.time(),self.run_id))
            self.run_id = self.store.run('direct world protocol probe' if world_probe else 'client session')
            self.reset_milestones()
            self.runner = None
            self.latest_screenshot = None
            self.screenshot_error = None
            self.client_dir = ROOT/'runs'/self.run_id
            self.client_dir.mkdir(parents=True,exist_ok=True)
            if not GAME.is_file(): raise FileNotFoundError(GAME)
            override = ROOT/'config/WindowsEngine.ini'
            args = [str(GAME),f'-LauncherTetherPort={self.tether.port}', '-windowed','-ResX=1280','-ResY=720',
                    '-WinX=100','-WinY=100','-ForceRes',
                    '-log','-stdout','-FullStdOutLogOutput',f'-UserDir={ROOT / "client-profile"}',
                    f'-abslog={self.client_dir / "game.log"}',f'-iniFile={override}',
                    '-LogCmds=LogNet Verbose,LogNetTraffic Verbose,LogNetPackageMap Verbose,LogCore Warning']
            if world_probe:
                # Fixed loopback URL only. This isolates serializers; it never
                # establishes that realm selection or lobby Play succeeded.
                args.insert(1,f'127.0.0.1:{self.world.port}?map={MAP}?driver=/Script/IntrepidNet.IntrepidNetDriver?world_id={WORLD}')
            (self.client_dir/'launch.json').write_text(json.dumps({'args':args,'client_sha256':self.inventory['sha256'],
                'mode':'direct_world_probe' if world_probe else 'lobby'},indent=2),encoding='utf-8')
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 1
            self.client = subprocess.Popen(args,cwd=self.client_dir,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,startupinfo=startup,
                                            text=True,encoding='utf-8',errors='replace')
            self.driver = WindowsDriver(self.client.pid)
            self.background_driver = None
            self.attached_driver = None
            threading.Thread(target=self.read_client,args=(self.client,self.client_dir,self.run_id),daemon=True).start()
        return f'Launched game process {self.client.pid}; session {self.run_id}'

    def read_client(self,process,directory,session_id):
        with (directory/'stdout.log').open('w',encoding='utf-8') as out:
            for line in process.stdout:
                out.write(line)
                out.flush()
                if self.client is not process or self.run_id != session_id: continue
                self.observe_lobby_browse(line)
                self.observe_initialization_failure(line)
                if 'XClient_AsyncSessionReplySink' in line and 'IcsStatusCodeSuccess' in line and 'Missing' not in line:
                    self.event('authentication','Client accepted a successful local XClient SessionReply')
                if 'XClient_AsyncGetCharactersReplySink' in line and 'IcsStatusCodeSuccess' in line:
                    self.event('lobby','Client accepted a successful local character-list reply')
                if 'Welcomed by server' in line:
                    self.event('welcome','Client accepted the server Welcome and map name')
                if ('Load map complete' in line or 'LoadMap Load map complete' in line) and 'Verra_World_Master' in line:
                    self.event('world_loaded','Client completed loading Verra; pawn possession still requires verification')
                if 'AAoCPlayerController - No valid pawn' in line:
                    self.event('controller_created','Client instantiated AAoCPlayerController; it reports no valid pawn')
                if 'NetworkFailure' in line or 'PendingConnectionFailure' in line:
                    self.event('client_network_error',line.strip()[:1000])
        self.event('client_exit',f'Game process exited with code {process.wait()}')

    def observe_initialization_failure(self, line):
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            return
        message = record.get('message', '')
        category = record.get('category')
        if not isinstance(message, str) or (category, record.get('severity')) not in (
                ('LogIntrepidEOS', 'Error'), ('LogAoC_Game', 'Error')):
            return
        if not (message.startswith('Both SandboxId and DeploymentId must be a valid value to run EOS:') or
                message.startswith('EACExitGame:') or message.startswith('Custom Failure:')):
            return
        with self.lock:
            self.initialization_failure = {'message': message[:1000], 'category': category,
                'client_timestamp': record.get('timestamp'), 'world_epoch': self.world_epoch,
                'connection_id': self.world_connection_id, 'cause_verified': False}
            self.initialization_failures = (self.initialization_failures + [self.initialization_failure])[-10:]
            self.event('client_initialization_failure', self.initialization_failure)

    def observe_lobby_browse(self,line):
        # The accepted client logs this exact Browse message on lobby travel.
        # LoadMap or a mere asset-name mention is not proof of leaving the world.
        if 'Browse: /Game/Levels/Character_Login/Character_Lobby' not in line:
            return
        with self.lock:
            if self.world_active:
                self.event('world_return_detected',{'connection_id':self.world_connection_id,
                           'world_epoch':self.world_epoch,'evidence':'client_announced_lobby_browse',
                           'message':line.strip()[:1000]})

    def stop_client(self):
        if self.runner and self.runner.snapshot().get('status') == 'running':
            self.runner.stop()
            self.runner.thread.join(timeout=2)
        for driver in (self.background_driver,self.attached_driver):
            if driver: driver.release_all()
        if self.client and self.client.poll() is None:
            self.client.terminate()
            self.client.wait(timeout=10)
        if self.run_id:
            self.store.execute("UPDATE runs SET status='completed',ended=? WHERE id=? AND status='running'",(time.time(),self.run_id))
        return 'Client stopped'

    def driver_for(self,mode):
        if mode not in ('foreground','background','attached'):
            raise ValueError('Choose the foreground, background or attached driver')
        if not self.client or self.client.poll() is not None:
            raise ValueError('Launch the game first')
        self.driver_mode = mode
        if mode == 'foreground': return self.driver
        if mode == 'attached':
            if not hasattr(automation,'AttachedWindowsDriver'):
                raise ValueError('The experimental input adapter is still being built')
            if not self.attached_driver:
                self.attached_driver = automation.AttachedWindowsDriver(self.client.pid)
            return self.attached_driver
        if not self.background_driver:
            self.background_driver = automation.BackgroundWindowsDriver(self.client.pid)
        return self.background_driver

    def run_test(self,scenario_name=None,driver_mode='foreground'):
        if not self.client or self.client.poll() is not None:
            raise ValueError('Launch the game before running a scenario')
        if self.runner and self.runner.snapshot()['status']=='running':
            raise ValueError('A test is already running')
        selection = scenario_name or 'walk'
        if selection not in ('login','walk'):
            raise ValueError('Choose the login or walk scenario')
        scenario = Runner.validate(json.loads(self.scenario_path.read_text(encoding='utf-8')))
        if self.world_active and any(step.get('action') == 'wait_milestone' and
                                     step.get('milestone') == 'welcome' for step in scenario['steps']):
            raise ValueError('This client is already in a world connection. World-entry scenarios require the lobby.')
        if selection == 'login':
            lobby_index = next((index for index,step in enumerate(scenario['steps'])
                                if step['action']=='wait_milestone' and step.get('milestone')=='lobby'),None)
            if lobby_index is None:
                raise ValueError('Login sequence requires a wait_milestone step for lobby')
            scenario['steps'] = scenario['steps'][:lobby_index+1]
        scenario['name'] = 'Login sequence' if selection=='login' else scenario.get('name','Custom scenario')
        independent_input = driver_mode in ('background','attached')
        scenario['steps'].insert(0,{'name':'Background test countdown' if independent_input else 'Focus game countdown','action':'wait','duration':1 if independent_input else 5})
        Runner.validate(scenario)
        # The run attaches to this client session; evidence is never inherited from a previous launch.
        self.runner = automation.Runner(self.driver_for(driver_mode),self.event,
                     self.has_milestone,
                     movement_evidence=lambda started:None,screenshot_dir=self.client_dir/'tests',
                     position_sampler=self.position_sample)
        active = self.runner.start(scenario)
        self.store.run(scenario['name'],parent_run_id=self.run_id,identifier=active['run_id'])
        if driver_mode == 'attached':
            return 'Experimental process input adapter test started; verify screenshots and protocol gates. Desktop input is not used.'
        if driver_mode == 'background':
            return 'Background test started against the exact game window. Global mouse and keyboard input are not used.'
        return 'Test starts in five seconds. Put the game in the foreground; input stops if focus changes.'

    def position_sample(self):
        from tools.probe_movement import capture_snapshot
        if not self.client or self.client.poll() is not None:
            return {'status':'blocked','error':'The launched client has exited'}
        return capture_snapshot(self.client.pid)

    def capture_screenshot(self,driver_mode='foreground'):
        if not self.client or self.client.poll() is not None:
            raise ValueError('Launch the game before capturing its screen')
        self.latest_screenshot = None
        self.screenshot_error = None
        process,driver,directory=self.client,self.driver_for(driver_mode),self.client_dir
        def capture():
            time.sleep(5)
            if self.client is not process or process.poll() is not None: return
            try:
                path=directory/'calibration.png'
                info=driver.screenshot(path)
                self.latest_screenshot=path
                self.event('calibration_screenshot',info)
            except Exception as exc:
                self.screenshot_error=str(exc)
                self.event('screenshot_error',str(exc))
        threading.Thread(target=capture,daemon=True).start()
        if driver_mode in ('background','attached'): return 'Background window capture in five seconds; keep the game restored. No focus change is required.'
        return 'Capture in five seconds. Put the game in the foreground.'

    def import_capture(self,path):
        allowed = [ROOT,Path(r'E:\Ashes Of Creation Wire Shark'),Path(r'E:\Ashes Of Creation')]
        target = Path(path).resolve()
        if not any(target.is_relative_to(folder.resolve()) for folder in allowed) or target.suffix.lower() not in ('.pcap','.pcapng'):
            raise ValueError('Choose a PCAP inside the supplied game research folders')
        if not target.is_file(): raise FileNotFoundError(target)
        if self.importing: raise ValueError('A capture import is already running')
        identifier = self.store.run('capture: '+target.name)
        self.importing = True
        def work():
            from tools.import_capture import iter_capture
            try:
                count = 0
                clients = {}
                for row in iter_capture(target):
                    data = bytes.fromhex(row['hex'])
                    channel = 'world' if data.startswith(bytes.fromhex('96760c50')) else 'tether' if data.startswith(bytes.fromhex('a55a')) else row['channel']
                    direction = row['direction']
                    if channel == 'world':
                        from .unreal import decode_packet
                        source = (row['source']['address'],row['source']['port'])
                        destination = (row['destination']['address'],row['destination']['port'])
                        conversation = frozenset((source,destination))
                        header = decode_packet(data)
                        if header.get('kind') == 'stateless.Initial':
                            clients[conversation] = source
                        client = clients.get(conversation)
                        direction = ('C2S' if source == client else 'S2C') if client else 'unknown'
                    elif channel == 'tether': direction = 'unknown'
                    try:
                        if channel=='world':
                            from .unreal import decode_packet
                            decoded = decode_packet(data,direction='server' if direction=='S2C' else 'client')
                        elif channel=='tether': decoded=decode_tether(data)
                        else: decoded=row['decoded']
                    except Exception as exc: decoded={'error':str(exc),'interpretation':'unknown'}
                    decoded.update(frame=row['frame'],source=row['source'],destination=row['destination'])
                    if channel == 'world':
                        decoded['direction_evidence'] = 'observed_stateless_initial_sender' if client else 'client_endpoint_not_yet_observed'
                    kind = decoded.get('kind',row['kind'])
                    self.store.packet(identifier,channel,direction,data,kind,decoded,row['ts'])
                    count += 1
                self.store.execute('UPDATE runs SET status=?,ended=?,detail=? WHERE id=?',('imported',time.time(),f'{count} scoped payloads imported',identifier))
            except Exception as exc:
                self.store.execute('UPDATE runs SET status=?,ended=?,detail=? WHERE id=?',('failed',time.time(),str(exc),identifier))
            finally: self.importing=False
        threading.Thread(target=work,daemon=True).start()
        return f'Import started: {identifier}'

    def screenshot(self):
        if self.latest_screenshot and self.latest_screenshot.is_file(): return self.latest_screenshot
        raise FileNotFoundError(self.screenshot_error or 'No client screenshot yet. Choose a driver and capture the launched game.')

    def presets(self):
        return [{'id':'login-world-1280','name':'Login and world · 1280 pixels','start_screen':'Warning screen after startup loading'},
                {'id':'attached-login-world-1280','name':'Attached login and world · 1280 pixels',
                 'start_screen':'Warning screen after startup loading; client area 1280 × 720'},
                {'id':'attached-login-world-entry-1280','name':'Background login and fresh world entry · 1280 pixels',
                 'start_screen':'Warning screen after startup loading; client area 1280 × 720'},
                {'id':'world-from-lobby-1280','name':'World entry · 1280 pixels','start_screen':'Character selection with LabExplorer selected'},
                {'id':'character-selection-world-entry-1280','name':'Character selection world entry · 1280 pixels',
                 'start_screen':'Visible lobby character selection with LabExplorer selected; client area 1280 × 720'}]

    def load_preset(self,identifier):
        if identifier not in {p['id'] for p in self.presets()}:
            raise ValueError('Unknown scenario preset')
        scenario = Runner.validate(json.loads((ROOT/'config/scenarios'/f'{identifier}.json').read_text(encoding='utf-8')))
        self.scenario_path.write_text(json.dumps(scenario,indent=2),encoding='utf-8')
        return 'Preset loaded. Confirm its starting screen and window size before running.'

    def learn_checkpoint(self,body):
        from PIL import Image
        name = body.get('name','')
        if not isinstance(name,str) or Path(name).name != name or len(name)>80:
            raise ValueError('Choose a short local PNG filename')
        source = self.screenshot()
        with Image.open(source) as screenshot:
            metadata = learn_template(screenshot,name,body.get('bbox'))
        metadata.update(source_run=self.run_id,source_screenshot=str(source))
        resolve_template(name).with_suffix('.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        return metadata

    def state(self):
        counts = self.store.query('SELECT kind,channel,COUNT(*) count,confidence FROM packets GROUP BY kind,channel,confidence ORDER BY count DESC')
        services = [{'id':'lobby','name':'Lobby','port':15051,'running':self.lobby is not None},
                    {'id':'tether','name':'Tether','port':self.tether.port if self.tether else None,'running':self.tether is not None},
                    {'id':'world','name':'World','port':17089,'running':self.world is not None}]
        running = self.client is not None and self.client.poll() is None
        active = self.runner.snapshot() if self.runner else None
        if active:
            active.update(id=active['run_id'],scenario=active.get('name','Custom scenario'))
        return {'server_pid':os.getpid(),'services':services,'runs':self.store.query('SELECT * FROM runs ORDER BY started'),
                'milestones':list(self.milestones.values()),'catalog':counts,
                'world_entry':{'epoch':self.world_epoch,'connection_id':self.world_connection_id,
                               'started_at':self.world_started_at,'active':self.world_active},
                'initialization_failure': self.initialization_failure,
                'initialization_failures': self.initialization_failures,
                'packet_count':self.store.query('SELECT COUNT(*) count FROM packets')[0]['count'],
                'client':{'running':running,'status':'running' if running else 'stopped','pid':self.client.pid if running else None,
                          'path':str(GAME),'sha256':self.inventory['sha256'],'contracts':len(self.c.files),'driver':self.driver_mode},
                'active_run':active,'importing':self.importing}


class Handler(BaseHTTPRequestHandler):
    lab = None
    def log_message(self,*args): pass

    def send(self,value,status=200,content_type='application/json'):
        data = json.dumps(value).encode() if content_type=='application/json' else value
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        if self.headers.get('Host') not in ('127.0.0.1:8765','localhost:8765'):
            raise ValueError('Invalid local Host header')
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765'):
            raise ValueError('Control requests must originate from this local dashboard')
        length = int(self.headers.get('Content-Length','0'))
        if not 0 < length <= 65536: raise ValueError('Invalid request body size')
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        try:
            parsed=urlparse(self.path)
            path,query=parsed.path,parse_qs(parsed.query)
            arg=lambda key,default:query.get(key,[default])[0]
            from .world_view import handle as handle_world_view
            if handle_world_view(self): return
            if path=='/api/state': return self.send(self.lab.state())
            if path=='/api/runs': return self.send(self.lab.store.query('SELECT * FROM runs ORDER BY started'))
            if path=='/api/packets': return self.send(self.lab.store.packets(arg('run_id',None),int(arg('limit',100)),int(arg('after',0)),arg('kind',None)))
            if path=='/api/packet':
                rows=self.lab.store.query('SELECT * FROM packets WHERE id=?',(int(arg('id',0)),))
                if not rows: return self.send({'ok':False,'message':'Packet not found'},404)
                rows[0]['decoded']=json.loads(rows[0]['decoded'])
                return self.send(rows[0])
            if path=='/api/events': return self.send(self.lab.store.query('SELECT * FROM events ORDER BY id DESC LIMIT 100'))
            if path=='/api/scenario': return self.send(json.loads(self.lab.scenario_path.read_text(encoding='utf-8')))
            if path=='/api/presets': return self.send(self.lab.presets())
            if path=='/api/templates': return self.send([json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT/'config/templates').glob('*.json'))])
            if path=='/api/screenshot': return self.send(self.lab.screenshot().read_bytes(),content_type='image/png')
            target=(ROOT/'web'/('index.html' if path=='/' else path.lstrip('/'))).resolve()
            if not target.is_relative_to((ROOT/'web').resolve()) or not target.is_file():
                return self.send({'ok':False,'message':'Not found'},404)
            return self.send(target.read_bytes(),content_type=mimetypes.guess_type(target)[0] or 'application/octet-stream')
        except Exception as exc: self.send({'ok':False,'message':str(exc)},400)

    def do_PUT(self):
        try:
            if self.path!='/api/scenario': return self.send({'ok':False,'message':'Not found'},404)
            scenario=Runner.validate(self.body())
            scenario.setdefault('name','Custom scenario')
            self.lab.scenario_path.write_text(json.dumps(scenario,indent=2),encoding='utf-8')
            self.send({'ok':True,'message':'Scenario saved'})
        except Exception as exc: self.send({'ok':False,'message':str(exc)},400)

    def do_POST(self):
        try:
            body=self.body()
            if self.path=='/api/template':
                metadata = self.lab.learn_checkpoint(body)
                return self.send({'ok':True,'message':'Visual checkpoint learned from the saved client screenshot','template':metadata})
            if self.path=='/api/annotate':
                if body.get('confidence') not in ('observed','hypothesis','verified'): raise ValueError('Invalid confidence')
                self.lab.store.execute('UPDATE packets SET annotation=?,confidence=?,label=? WHERE id=?',
                    (str(body.get('note',''))[:4000],body['confidence'],str(body.get('label',''))[:200],int(body['packet_id'])))
                return self.send({'ok':True,'message':'Annotation saved'})
            if self.path!='/api/control': return self.send({'ok':False,'message':'Not found'},404)
            action=body.get('action')
            if action=='import_capture': message=self.lab.import_capture(body.get('capture',''))
            elif action=='load_preset': message=self.lab.load_preset(body.get('preset'))
            elif action=='capture_screenshot': message=self.lab.capture_screenshot(body.get('driver','foreground'))
            elif action=='controller_bootstrap': message=self.lab.controller_bootstrap()
            elif action=='scene_bootstrap': message=self.lab.scene_bootstrap()
            elif action=='reload_world_protocol': message=self.lab.reload_world_protocol()
            elif action=='reload_tester': message=self.lab.reload_tester()
            elif action=='launch_world_probe': message=self.lab.launch_client(world_probe=True)
            elif action=='run_test': message=self.lab.run_test(body.get('scenario'),body.get('driver','foreground'))
            elif action=='cancel_test':
                if self.lab.runner: self.lab.runner.stop()
                message='Test cancellation requested'
            elif action in ('start_services','stop_services','launch_client','stop_client'):
                message=getattr(self.lab,action)()
            else: raise ValueError('Unknown action')
            self.send({'ok':True,'message':message})
        except Exception as exc: self.send({'ok':False,'message':str(exc)},400)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--start-services',action='store_true')
    args=parser.parse_args()
    Handler.lab=Lab()
    if args.start_services: Handler.lab.start_services()
    server=ThreadingHTTPServer(('127.0.0.1',8765),Handler)
    print('Ashes Lab listening at http://127.0.0.1:8765',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        Handler.lab.stop_client()
        Handler.lab.stop_services()
        server.server_close()


if __name__=='__main__': main()
