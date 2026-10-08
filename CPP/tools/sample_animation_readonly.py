import sys,json,pathlib,time,math
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/"tools"))
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader
from protocol_proof import EXPECTED_EXE,client_proof
root=pathlib.Path(__file__).resolve().parents[1];d=json.loads((root/"logs/movement-animation-diagnostic.json").read_text());pid=d["proof"]["pid"]
r=Reader(pid,EXPECTED_EXE)
try:
 probe=MovementProbe(r);m=int(d["movement_class"]["address"],16);a=int(d["pawn"]["address"],16)
 probe.identity(m);probe.identity(a,"PlayerCharacter")
 anim=int(d["animation"]["instance"]["address"],16);probe.identity(anim)
 samples=[]
 for i in range(100):
  movement=probe.fields(m,["Velocity","Acceleration","MovementMode"]);pawn=probe.fields(a,["ALSSpeed","Gait"])
  state={"time":time.time(),"movement":{k:v.get("value") for k,v in movement.items()},"pawn":{k:v.get("value") for k,v in pawn.items()},"animation":{}}
  for k,v in d["animation"]["fields"].items():
   if "__CustomProperty" in k:state["animation"][k]=probe.decode(anim,v["metadata"]).get("value")
  samples.append(state);time.sleep(.1)
 (root/"logs/movement-animation-samples.json").write_text(json.dumps(samples,indent=2))
 speeds=[math.hypot(*s["movement"]["Velocity"][:2]) for s in samples];moving=[s for s,v in zip(samples,speeds) if v>1]
 print(json.dumps({"samples":len(samples),"moving_samples":len(moving),"min_speed":min(speeds),"max_speed":max(speeds),"example":moving[:2],"mode_counts":{mode:sum(s["movement"]["MovementMode"]==mode for s in samples) for mode in [1,3,5]}}))
finally:r.close()
