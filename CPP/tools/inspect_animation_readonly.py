"""Diagnostics only: read current game movement properties; no game calls or writes."""
import sys,json,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/"tools"))
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader
from protocol_proof import EXPECTED_EXE,client_proof
root=pathlib.Path(__file__).resolve().parents[1]
p=json.loads((root/"data/client-inspection.json").read_text());pid=p["pid"]
pawn=next(m["actor"] for m in p["network_guid_actor_matches"] if m["actor"]["class"]=="PlayerPawn_C")
r=Reader(pid,EXPECTED_EXE)
try:
 probe=MovementProbe(r);a=int(pawn["address"],16);probe.identity(a,"PlayerCharacter")
 cm=probe.fields(a,["CharacterMovement","Mesh","StatsComponent"]);m=int(cm["CharacterMovement"]["value"]["address"],16)
 names=["MaxWalkSpeed","MaxFlySpeed","MaxAcceleration","Velocity","Acceleration","MovementMode","GravityScale","GroundFriction","BrakingDecelerationWalking","bUseMovementSpeedStat","bPredictMovement","bDeferServerMoves","MaxWalkStrafeSpeed","MaxWalkSpeedBackward","MaxRunSpeed","MaxRunStrafeSpeed","MaxRunSpeedBackward","MaxSprintSpeed","MovementState"]
 mesh=int(cm["Mesh"]["value"]["address"],16)
 animField=probe.fields(mesh,["AnimScriptInstance"])
 anim=animField["AnimScriptInstance"].get("value")
 animData={"instance":anim}
 if anim:
  animAddress=int(anim["address"],16)
  # The large player animation Blueprint has more than 512 members; retain
  # bounded validated FProperty traversal, with a diagnostic-only 2048 limit.
  import inspect,types,textwrap
  method=textwrap.dedent(inspect.getsource(type(probe.reflection).properties)).replace("len(result)<512","len(result)<2048")
  namespace=dict(type(probe.reflection).properties.__globals__);exec(method,namespace)
  probe.reflection.properties=types.MethodType(namespace["properties"],probe.reflection)
  props=probe.properties_for(animAddress)
  animNames=[n for n in props if any(t in n.lower() for t in ["speed","moving","velocity","walk","idle","locomot","accelerat","movement","run"])][:90]
  animData["fields"]=probe.fields(animAddress,animNames)
 result={"animation":animData,"proof":client_proof(pid),"pawn":pawn,"components":cm,"movement":probe.fields(m,names),"movement_class":probe.identity(m),"movement_properties":[n for n in probe.properties_for(m) if any(t in n.lower() for t in ["speed","stat","anim","predict"])]}
 (root/"logs/movement-animation-diagnostic.json").write_text(json.dumps(result,indent=2))
 print(json.dumps({"movement":{k:v.get("value",v.get("status")) for k,v in result["movement"].items()},"movement_properties":result["movement_properties"],"class":result["movement_class"]["class"],"animation":{k:v.get("value",v.get("status")) for k,v in animData.get("fields",{}).items()}}))
finally:r.close()
