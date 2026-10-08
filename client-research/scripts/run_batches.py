"""Run a bounded number of sequential checkpointed Ghidra batches."""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--batches',type=int,default=1)
args=parser.parse_args()
if not 1<=args.batches<=32:parser.error('batches must be 1..32')
logs=RESEARCH/'logs';logs.mkdir(exist_ok=True)
for i in range(args.batches):
    result=subprocess.run([sys.executable,str(RESEARCH/'scripts/decompile_queue.py')],capture_output=True,text=True)
    if result.returncode:
        print(result.stderr,file=sys.stderr)
        raise SystemExit(result.returncode)
    summary=json.loads(result.stdout)
    if summary['batch_ranges']==0:break
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    manifest=f'batch_{stamp}.tsv'
    shutil.copyfile(RESEARCH/'batches/next.tsv',RESEARCH/'batches'/manifest)
    print(json.dumps({'batch':i+1,'of':args.batches,'pending':summary['status'].get('pending',0),'manifest':manifest}),flush=True)
    transcript=logs/(stamp+'.log')
    with transcript.open('w',encoding='utf-8') as out:
        subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(RESEARCH/'scripts/Run-Decompile.ps1'),'-Manifest',manifest,'-BatchName','bulk'],stdout=out,stderr=subprocess.STDOUT,check=True)
    if 'Save succeeded' not in transcript.read_text(encoding='utf-8',errors='replace'):
        raise RuntimeError(f'Ghidra did not confirm save: {transcript}')
    print(json.dumps({'batch':i+1,'saved':True,'transcript':str(transcript)}),flush=True)
result=subprocess.run([sys.executable,str(RESEARCH/'scripts/decompile_queue.py')],check=True,capture_output=True,text=True)
print(result.stdout,flush=True)
