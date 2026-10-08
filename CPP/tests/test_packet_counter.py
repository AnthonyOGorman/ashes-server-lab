"""Independent test driver for the C++ persisted packet counter, on isolated ports/data."""
import json, pathlib, shutil, socket, sqlite3, subprocess, time, urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
run = root / 'runs' / ('packet-counter-' + str(time.time_ns()))
(run / 'config').mkdir(parents=True)
(run / 'data').mkdir()
shutil.copyfile(root / 'config/contracts.json', run / 'config/contracts.json')
shutil.copyfile(root / 'data/characters.json', run / 'data/characters.json')
config = json.loads((root / 'config/backend.json').read_text())
config.update(dashboard_port=18865, world_port=28089, lobby_port=26051, tether_port=28090,
              auto_initialize=False)
(run / 'config/backend.json').write_text(json.dumps(config))
db = run / 'data/lab.sqlite'
with sqlite3.connect(db) as connection:
    connection.execute("CREATE TABLE packets(id INTEGER PRIMARY KEY,ts REAL,channel TEXT,direction TEXT,kind TEXT,hex TEXT,decoded TEXT,label TEXT DEFAULT '',annotation TEXT DEFAULT '',confidence TEXT DEFAULT 'observed')")
    connection.executemany("INSERT INTO packets(id,decoded) VALUES(?, '{}')", [(10,), (100,), (1000,)])
checks = []
def check(condition, label):
    assert condition, label
    checks.append(label)
def state():
    return json.load(urllib.request.urlopen('http://127.0.0.1:18865/api/state', timeout=5))
def start():
    process = subprocess.Popen([str(root / 'build/msvc/Debug/ashes_lab.exe'), '--root', str(run), '--start-services'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            return process, state()
        except OSError:
            assert process.poll() is None, 'Isolated C++ server exited'
            time.sleep(.05)
    process.terminate()
    process.wait(timeout=5)
    raise AssertionError('Isolated C++ server readiness timeout')
def wait_count(expected):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if state()['packet_count'] == expected:
            return True
        time.sleep(.02)
    return False
process, initial = start()
try:
    check(initial['packet_count'] == 3, 'Startup counts persisted rows rather than maximum row ID')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
        for _ in range(16):
            peer.sendto(b'bad-local-test-packet', ('127.0.0.1', 28089))
        check(wait_count(19), 'Each committed receive increments the maintained counter')
        with sqlite3.connect(db) as connection:
            connection.execute("CREATE TRIGGER reject_test BEFORE INSERT ON packets BEGIN SELECT RAISE(FAIL, 'test rejection'); END")
        peer.sendto(b'rejected-local-test-packet', ('127.0.0.1', 28089))
        time.sleep(.1)
        check(state()['packet_count'] == 19, 'A failed packet insert cannot increment the counter')
        with sqlite3.connect(db) as connection:
            connection.execute('DROP TRIGGER reject_test')
        peer.sendto(b'committed-local-test-packet', ('127.0.0.1', 28089))
        check(wait_count(20), 'Counter remains correct after a failed insert')
    with sqlite3.connect(db) as connection:
        check(connection.execute('SELECT COUNT(*) FROM packets').fetchone()[0] == state()['packet_count'],
              'API counter agrees with persisted rows')
finally:
    process.terminate()
    process.wait(timeout=5)
process, restarted = start()
try:
    check(restarted['packet_count'] == 20, 'Restart restores the committed total')
finally:
    process.terminate()
    process.wait(timeout=5)
result = {'passed': len(checks), 'checks': checks, 'run_directory': str(run)}
(run / 'verification.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
