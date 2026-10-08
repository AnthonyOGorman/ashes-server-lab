#include "ashes/backend.hpp"
#include <algorithm>
#include <numbers>
namespace ashes {
namespace {
constexpr auto package = "/Game/ENV/Nodes/Nodes_Master/Node_Sublevels/Landscape_Platforms/Layout_Flat_D/Landscape_Flat_D_Master_01";
constexpr auto candidate_hash = "5256a4abeb79200551495e72f990929de125b8f4b4d37faa080dd37360bb8efc";
constexpr Vec origin{-644519.105296,376773.237813,12012.231952};
uint64_t addr(const Json& j){return std::stoull(j.at("address").get<std::string>(),nullptr,16);}
bool read_bool(Reflection& f,uint64_t object,const char* name,int offset,int mask){
 auto p=f.property(object,name,offset,1);require(p.at("type")=="BoolProperty","Exact reflected streaming bool required");
 auto layout=f.r.read(addr(p)+0x70,4);require(layout==Bytes{1,0,uint8_t(mask),uint8_t(mask)},"Reviewed streaming bool mask required");
 return (f.r.at<uint8_t>(object+offset)&mask)!=0;
}
Json verify_floor(Backend& owner,const Json& body,Connection& c){
 require(c.phase=="joined"&&c.stages.contains("NodeLayoutWinsteadFloor")&&c.actors.contains("node_probe"),"Received-floor stage and current connection required");
 require(owner.players.contains(c.id),"Current initialized player required");auto player=owner.players.at(c.id);
 require(player->mode==1&&length(player->velocity)==0,"Grounded idle player required for collision admission");
 require(owner.attached.at("pid")==body.at("pid")&&owner.attached.at("process_created_filetime")==body.at("created_filetime"),"Exact inspected client lifetime required");
 ProcessReader r(body.at("pid"),owner.config.at("client_exe").get<std::string>(),owner.config.at("client_sha256"));
 require(r.created==body.at("created_filetime"),"Client lifetime changed");auto snapshot=read_json(owner.root/"data/client-inspection.json");verify_evidence(r.proof(),snapshot);
 require(snapshot.at("errors").empty(),"Clean fresh native inspection required");Reflection f(r);Json match;
 for(auto& m:snapshot.at("network_guid_actor_matches"))if(m.at("guid")==c.actors.at("node_probe").json()){require(match.is_null(),"Unique accepted settlement actor required");match=m;}
 require(!match.is_null(),"Settlement actor not accepted");auto actor=addr(match.at("actor"));auto ai=f.identity(actor,"NodeLayoutReplicator");
 require(ai.at("class")=="NodeLayoutReplicator"&&ai.at("object_index")==match.at("weak_object_index")&&ai.at("serial")==match.at("weak_object_serial"),"Current settlement weak identity required");
 uint64_t driver=0;for(auto& d:snapshot.at("net_drivers"))if(d.at("guid_cache")==match.at("guid_cache")){require(!driver,"Unique accepted driver required");driver=addr(d);}
 require(driver&&f.guid_accepted(driver,c.actors.at("node_probe"),actor),"Current driver GUID acceptance required");
 auto node=f.property(actor,"NodeGuid",0x500,8),layout=f.property(actor,"LayoutAssetSetGuids",0x370,0x190);
 require(node.at("type")=="Int64Property"&&layout.at("type")=="StructProperty","Reviewed floor replication layout required");
 require(r.at<uint64_t>(actor+0x500)==0x62d024b45678ULL&&r.at<uint8_t>(actor+0x508)==1,"Received initialized Winstead node required");
 require(r.read(actor+0x488,3)==Bytes{1,0,1}&&r.at<uint8_t>(actor+0x4b0)==1,"Received floor metadata required");
 auto items=r.at<uint64_t>(actor+0x478);int count=r.at<int32_t>(actor+0x480),capacity=r.at<int32_t>(actor+0x484);
 require(items&&count==1&&capacity>=count&&capacity<=4096,"Exactly one received floor item required");
 require(r.at<int32_t>(items)==1&&r.at<int32_t>(items+8)==1&&r.at<uint64_t>(items+0x10)==0x62d024b45678ULL&&r.at<int32_t>(items+0x18)==0&&r.at<int32_t>(items+0x1c)==14&&r.at<uint64_t>(items+0x20)==0x5429e761b0070000ULL,"Received floor compound identity required");
 require(r.at<std::array<double,4>>(items+0x30)==std::array<double,4>{0,0,0,1}&&r.at<Vec>(items+0x50)==Vec{0,0,0}&&r.at<Vec>(items+0x70)==Vec{1,1,1},"Received identity instance transform required");
 auto level=std::stoull(ai.at("outer_address").get<std::string>(),nullptr,16);f.identity(level,"Level");f.property(level,"OwningWorld",0xe0,8);
 auto world=r.at<uint64_t>(level+0xe0);require(f.identity(world,"World").at("name")=="Verra_World_Master","Accepted Verra world required");
 f.property(world,"PersistentLevel",0x50,8);f.property(world,"NetDriver",0x58,8);require(r.at<uint64_t>(world+0x50)==level&&r.at<uint64_t>(world+0x58)==driver,"Current persistent level/driver binding required");
 auto streams=f.property(world,"StreamingLevels",0xb0,16);require(streams.at("type")=="ArrayProperty","Reflected world streaming array required");
 auto data=r.at<uint64_t>(world+0xb0);int n=r.at<int32_t>(world+0xb8),cap=r.at<int32_t>(world+0xbc);require(data&&n>0&&n<=cap&&cap<=8192,"Bounded current streaming array required");
 Json placement;for(int i=0;i<n;i++){
  auto stream=r.at<uint64_t>(data+size_t(i)*8);if(!stream)continue;auto si=f.identity(stream,"LevelStreaming");
  f.property(stream,"PackageNameToLoad",0x7c,8);if(f.name(r.at<uint32_t>(stream+0x7c),r.at<uint32_t>(stream+0x80))!=package)continue;
  require(placement.is_null()&&si.at("class")=="LevelStreamingDynamic"&&si.at("outer_address")==f.object(world).at("address"),"Unique exact dynamic floor in current world required");
  auto soft=f.property(stream,"WorldAsset",0x48,40);require(soft.at("type")=="SoftObjectProperty","Exact reflected world soft asset required");
  auto soft_package=f.name(r.at<uint32_t>(stream+0x50),r.at<uint32_t>(stream+0x54)),soft_asset=f.name(r.at<uint32_t>(stream+0x58),r.at<uint32_t>(stream+0x5c));
  require(soft_package.starts_with(std::string(package)+"_")&&soft_asset=="Landscape_Flat_D_Master_01","Native source asset/instance package binding required");
  auto transform=f.property(stream,"LevelTransform",0xb0,96);require(transform.at("type")=="StructProperty","Reflected loaded transform required");
  auto q=r.at<std::array<double,4>>(stream+0xb0);auto t=r.at<Vec>(stream+0xd0),s=r.at<Vec>(stream+0xf0);
  double a=-40.79154*std::numbers::pi/360.;std::array<double,4> expected{0,0,std::sin(a),std::cos(a)};
  double direct=0,opposite=0;for(int k=0;k<4;k++){direct=std::max(direct,std::abs(q[k]-expected[k]));opposite=std::max(opposite,std::abs(q[k]+expected[k]));}
  require(std::min(direct,opposite)<1e-8&&finite(t)&&finite(s),"Exact native floor yaw required");for(int k=0;k<3;k++)require(std::abs(t[k]-origin[k])<1e-5&&std::abs(s[k]-1)<1e-10,"Exact native floor origin/unit scale required");
  require(read_bool(f,stream,"bShouldBeLoaded",0x118,0x10)&&read_bool(f,stream,"bShouldBeVisible",0x118,8)&&r.at<uint8_t>(stream+0x138)==6,"Fully visible native streaming state required");
  f.property(stream,"LoadedLevel",0x1a8,8);auto loaded=r.at<uint64_t>(stream+0x1a8);auto li=f.identity(loaded,"Level");
  auto loaded_world=f.identity(std::stoull(li.at("outer_address").get<std::string>(),nullptr,16),"World");auto loaded_package=f.identity(std::stoull(loaded_world.at("outer_address").get<std::string>(),nullptr,16),"Package");require(loaded_world.at("name")==soft_asset&&loaded_package.at("name")==soft_package,"Actual loaded world/package identity required");
  require(read_bool(f,loaded,"bIsVisible",0x260,0x20),"Actual loaded level visibility required");f.property(loaded,"OwningWorld",0xe0,8);require(r.at<uint64_t>(loaded+0xe0)==world,"Loaded floor owning world required");
  placement={{"stream",si},{"loaded_level",li},{"origin",t},{"quaternion",q},{"scale",s},{"package",package}};
 }
 require(!placement.is_null(),"Exact floor has not loaded");require(r.at<uint64_t>(actor+0x478)==items&&r.at<int32_t>(actor+0x480)==count&&r.at<uint64_t>(world+0xb0)==data&&r.at<int32_t>(world+0xb8)==n,"Native arrays changed during floor verification");r.verify_alive();
 return {{"client_proof",r.proof()},{"actor_guid",c.actors.at("node_probe").json()},{"actor",ai},{"placement",placement}};
}
}
Json admit_winstead_collision(Backend& owner,const Json& body){
 auto connection=[&]() -> Connection& {std::string id=body.at("connection_id");auto it=std::find_if(owner.protocol.connections.begin(),owner.protocol.connections.end(),[&](auto& entry){return entry.second.id==id;});require(it!=owner.protocol.connections.end(),"Current floor connection required");return it->second;};
 std::shared_ptr<Movement> player;std::shared_ptr<const CollisionWorld> previous;Vec position;Json proof;
 {std::lock_guard lock(owner.mutex);auto& c=connection();require(!c.stages.contains("WinsteadCollisionAdmitted"),"Floor collision already admitted");proof=verify_floor(owner,body,c);player=owner.players.at(c.id);previous=player->world;position=player->position;}
 // Build a private per-player world outside the movement lock; base geometry remains reusable for clients without this floor.
 auto cache=prepare_winstead_collision(owner,previous);
 {std::lock_guard lock(owner.mutex);auto& c=connection();require(!c.stages.contains("WinsteadCollisionAdmitted")&&owner.players.at(c.id)==player&&player->world==previous&&player->position==position,"Player/collision state changed during admission");auto final=verify_floor(owner,body,c);require(final.at("actor")==proof.at("actor")&&final.at("placement")==proof.at("placement"),"Native floor identity changed during collision preparation");player->world=cache;c.stages.insert("WinsteadCollisionAdmitted");proof=final;owner.event("winstead_collision_admitted",{{"connection_id",c.id},{"tiles_added",256},{"scope","accepted player only"},{"candidate_sha256",candidate_hash},{"proof",proof},{"state_preserved",true}});}
 return {{"ok",true},{"message","Verified Winstead collision admitted for the current player"},{"tiles_added",256},{"proof",proof}};
}
std::shared_ptr<CollisionWorld> prepare_winstead_collision(Backend& owner,std::shared_ptr<const CollisionWorld> previous){
 auto path=owner.root/"runs/settlement-probe-20261008/terrain-candidate/decoded-world/manifest.json";require(sha256_file(path)==candidate_hash,"Reviewed Winstead candidate manifest changed");
 {std::lock_guard lock(owner.mutex);if(owner.winstead_base.lock()==previous&&owner.winstead_geometry)return owner.winstead_geometry;}
 auto manifest=read_json(path);
 require(manifest.at("schema")=="ashes-offline-landscape-v1"&&manifest.at("status")=="decoded"&&manifest.at("failures").empty()&&manifest.at("tiles").size()==256&&manifest.at("collision_admission").at("status")=="verified"&&manifest.at("collision_admission").at("exe_sha256")==owner.config.at("client_sha256"),"Exact verified platform candidate required");
 auto cache=std::make_shared<CollisionWorld>(*previous);for(auto& tile:manifest.at("tiles")){require(tile.at("package")==package&&tile.at("collision_query_enabled")==true&&tile.at("collision_profile")=="BlockAll","Only reviewed query-enabled platform tiles admitted");cache->tiles.emplace_back(tile,path.parent_path());}
 {std::lock_guard lock(owner.mutex);owner.winstead_base=previous;owner.winstead_geometry=cache;}
 return cache;
}
}
