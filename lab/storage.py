import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, scenario TEXT, status TEXT, started REAL, ended REAL, detail TEXT);
          CREATE TABLE IF NOT EXISTS packets(id INTEGER PRIMARY KEY, ts REAL, run_id TEXT, channel TEXT, direction TEXT, kind TEXT, size INTEGER, hex TEXT, decoded TEXT, annotation TEXT DEFAULT '', confidence TEXT DEFAULT 'observed', label TEXT DEFAULT '');
          CREATE INDEX IF NOT EXISTS packet_runs ON packets(run_id,id);
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts REAL, run_id TEXT, kind TEXT, detail TEXT);
          CREATE TABLE IF NOT EXISTS characters(id TEXT PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE, world TEXT, proto BLOB);
        ''')
        if 'parent_run_id' not in {row[1] for row in self.db.execute('PRAGMA table_info(runs)')}:
            self.db.execute('ALTER TABLE runs ADD COLUMN parent_run_id TEXT')
        self.db.commit()

    def query(self, sql, args=()):
        with self.lock:
            return [dict(x) for x in self.db.execute(sql, args).fetchall()]

    def execute(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.lastrowid

    def run(self, scenario, parent_run_id=None, identifier=None):
        identifier = identifier or uuid.uuid4().hex[:12]
        self.execute('INSERT INTO runs(id,scenario,status,started,ended,detail,parent_run_id) VALUES(?,?,?,?,?,?,?)', (identifier, scenario, 'running', time.time(), None, '',parent_run_id))
        return identifier

    def packet(self, run_id, channel, direction, data, kind, decoded=None, ts=None):
        return self.execute('INSERT INTO packets(ts,run_id,channel,direction,kind,size,hex,decoded) VALUES(?,?,?,?,?,?,?,?)',
                            (ts or time.time(), run_id, channel, direction, kind, len(data), data.hex(), json.dumps(decoded or {})))

    def packets(self, run_id=None, limit=100, after=0, kind=None):
        clause = 'id > ?'
        args = [after]
        if run_id:
            matches = self.query('SELECT parent_run_id,started,ended FROM runs WHERE id=?',(run_id,))
            if matches and matches[0]['parent_run_id']:
                run = matches[0]
                clause += ' AND ts>=? AND ts<=?'
                args.extend((run['started'],run['ended'] or time.time()))
                run_id = run['parent_run_id']
            clause += ' AND run_id=?'
            args.append(run_id)
        if kind:
            clause += ' AND kind=?'
            args.append(kind)
        args.append(min(max(int(limit), 1), 1000))
        rows = self.query(f'SELECT * FROM packets WHERE {clause} ORDER BY id DESC LIMIT ?', args)
        for row in rows:
            row['decoded'] = json.loads(row['decoded'])
        return rows
