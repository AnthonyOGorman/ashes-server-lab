"""Snapshot only the selected connection's movement events; no replay or writes to the database."""
from pathlib import Path
import urllib.request,json,sqlite3,argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='retry-fixed-live-trace.json',help='JSON filename within the follow-up evidence directory')
parser.add_argument('--from-time',type=float,default=0)
parser.add_argument('--to-time',type=float,default=float('inf'))
parser.add_argument('--connection',help='Exact existing connection ID, including a closed session for retrospective review')
args=parser.parse_args()
assert Path(args.output).name==args.output and args.output.endswith('.json'),'Evidence filename must be a local JSON basename'
root=Path(__file__).resolve().parents[1]
connections=json.load(urllib.request.urlopen('http://127.0.0.1:8865/api/connections',timeout=10))
active=[c for c in connections if c['selected_character_id'] and (c['id']==args.connection if args.connection else c['phase']=='joined')]
assert len(active)==1,'One selected active local client is required'
connection=active[0]
db=sqlite3.connect((root/'data/lab.sqlite').as_uri()+'?mode=ro',uri=True)
rows=[]
for identifier,observed,detail in db.execute("SELECT id,ts,detail FROM events WHERE kind='movement' AND json_extract(detail,'$.connection_id')=? ORDER BY id",(connection['id'],)):
    if args.from_time<=observed<=args.to_time:
        result=json.loads(detail)['result']; rows.append({'id':identifier,'observed_at':observed,**result})
db.close()
new=[m for m in rows if m['kind']=='new']
summary={'connection_id':connection['id'],'moves':len(rows),'new_moves':len(new),'discarded_intervals':sum('discarded_time' in m for m in rows),'resolution_moves':sum(m.get('time_resolution_active',False) for m in new),'responses':{v:sum(m.get('response')==v for m in new) for v in ('ack','correction','deferred')},'max_prediction_error_cm':max((m.get('prediction_error_cm',0) for m in new),default=None),'errors_above_10cm':sum(m.get('prediction_error_cm',0)>10 for m in new),'moving_new_moves':sum(sum(x*x for x in m['acceleration'])>0 for m in new)}
for field in ('simulation_ms','packet_lock_wait_ms','packet_processing_elapsed_ms'):
    values=sorted(m[field] for m in new if field in m)
    if values:summary[field]={'p50':values[len(values)//2],'p95':values[min(len(values)-1,int(len(values)*.95))],'max':values[-1]}
run=root/'runs/character-movement-followup-20261007';(run/args.output).write_text(json.dumps({'connection':connection,'summary':summary,'moves':rows},indent=2))
print(json.dumps(summary))
