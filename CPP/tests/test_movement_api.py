"""Exercise movement controls on an idle local C++ backend; restores walking settings."""
import json, pathlib, urllib.request, urllib.error
base="http://127.0.0.1:8865"
def get(): return json.load(urllib.request.urlopen(base+"/api/state",timeout=10))
def post(body):
    return json.load(urllib.request.urlopen(urllib.request.Request(base+"/api/control",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"}),timeout=10))
original=get()["movement_settings"]
checks=[]
def check(value,name):
    assert value,name
    checks.append(name)
def rejected(body):
    try: post(body)
    except urllib.error.HTTPError as e: return e.code==400
    return False
walking={"speed":600,"collision_enabled":True,"gravity_enabled":True}
fly={"speed":1320,"collision_enabled":False,"gravity_enabled":False}
try:
    check(get()["backend"]=="C++","Native C++ backend")
    check(post({"action":"movement_settings","settings":fly})["movement_settings"]==fly,"Fly preset API accepted")
    check(get()["movement_settings"]==fly,"State publishes current flight settings")
    saved=json.loads((pathlib.Path(__file__).resolve().parents[1]/"data/movement-settings.json").read_text())
    check(saved==fly,"Movement settings persisted")
    check(rejected({"action":"movement_settings","settings":dict(fly,speed=10001)}),"Invalid speed rejected")
    check(get()["movement_settings"]==fly,"Rejected settings leave live state unchanged")
    check(rejected({"action":"movement_settings","settings":dict(fly,collision_enabled=1)}),"Invalid collision type rejected")
    check(rejected({"action":"flight_altitude","delta":1000}),"Altitude refuses absent player")
    check(rejected({"action":"recover_spawn","connection_id":"missing","pid":0,"created_filetime":0}),"Spawn recovery refuses an absent exact client and connection")
    check(rejected({"action":"admit_winstead_collision","connection_id":"missing","pid":0,"created_filetime":0}),"Platform collision refuses an absent exact client and connection")
finally:
    post({"action":"movement_settings","settings":walking})
check(get()["movement_settings"]==walking,"Walking preset restores defaults")
post({"action":"movement_settings","settings":original})
result={"passed":len(checks),"checks":checks}
(pathlib.Path(__file__).resolve().parents[1]/"logs/movement-api-results.json").write_text(json.dumps(result,indent=2))
print(json.dumps(result))
