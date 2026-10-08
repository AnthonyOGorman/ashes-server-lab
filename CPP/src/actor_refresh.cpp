#include "ashes/inspection.hpp"
#include "ashes/protocol.hpp"
#include <set>
#include <sstream>
namespace ashes {
namespace {
uint64_t address(const Json& j){return std::stoull(j.at("address").get<std::string>(),nullptr,16);}
std::string hex_address(uint64_t value){std::ostringstream s;s<<"0x"<<std::hex<<value;return s.str();}
}
Json refresh_actor_matches(ProcessReader& r,const Json& previous,const std::map<std::string,Guid>& actors){
 verify_evidence(r.proof(),previous);Reflection f(r);Json snapshot=previous,matches=Json::array();
 const std::map<std::string,std::string> classes{{"controller","AoCPlayerControllerBP_C"},{"pawn","PlayerPawn_C"},{"game_state","AoCGameStateBP_C"},{"player_state","AoCPlayerStateBP_C"},{"node_probe","NodeLayoutReplicator"}};
 std::set<std::string> found;
 for(auto& source:previous.at("net_drivers")){
  auto driver=address(source);auto identity=f.identity(driver,"NetDriver");require(identity.at("object_index")==source.at("object_index")&&identity.at("serial")==source.at("serial"),"Actor refresh driver lifetime changed");
  f.property(driver,"ServerConnection",0x138,8);auto connection=r.at<uint64_t>(driver+0x138);require(connection,"Actor refresh current client connection required");auto connection_id=f.identity(connection,"NetConnection");
  require(connection_id.at("object_index")==source.at("server_connection").at("object_index")&&connection_id.at("serial")==source.at("server_connection").at("serial"),"Actor refresh server connection changed");
  f.property(connection,"PackageMap",0x88,8);auto package=r.at<uint64_t>(connection+0x88);f.identity(package,"PackageMapClient");auto cache=r.at<uint64_t>(package+0x338);require(hex_address(cache)==source.at("guid_cache").get<std::string>(),"Actor refresh current GUID cache changed");
  auto entries=r.at<uint64_t>(cache+0x10);int count=r.at<int32_t>(cache+0x18),capacity=r.at<int32_t>(cache+0x1c);require(count>=0&&count<=capacity&&capacity<=100000,"Actor refresh GUID map bounds");
  for(int first=0;first<count;first+=16000){int n=std::min(16000,count-first);auto data=r.read(entries+size_t(first)*80,size_t(n)*80);
   for(int i=0;i<n;i++){auto row=data.data()+size_t(i)*80;Guid guid;std::memcpy(&guid.object,row,8);std::memcpy(&guid.server,row+8,4);std::memcpy(&guid.random,row+12,4);
    auto target=std::find_if(classes.begin(),classes.end(),[&](const auto& item){auto it=actors.find(item.first);return it!=actors.end()&&it->second==guid;});if(target==classes.end())continue;
    require(found.insert(target->first).second,"Unique current authored actor GUID required");int32_t index,serial;std::memcpy(&index,row+16,4);std::memcpy(&serial,row+20,4);if(index<0||serial<=0)continue;require(unsigned(index)<f.count,"Accepted actor weak identity bounds");
    auto chunk=r.at<uint64_t>(f.chunks+8*(unsigned(index)/65536));auto pointer=r.at<uint64_t>(chunk+size_t(unsigned(index)%65536)*24);auto actor=f.identity(pointer,target->second);
    require(actor.at("class")==target->second&&actor.at("object_index")==index&&actor.at("serial")==serial,"Actor refresh weak identity/class mismatch");require(f.guid_accepted(driver,guid,pointer),"Current accepted actor GUID changed");
    auto object_field=[&](const char* name){auto p=f.find_property(pointer,name);require(p.at("type")=="ObjectProperty"&&p.at("element_size")==8,"Current actor object link required");return f.identity(r.at<uint64_t>(pointer+p.at("offset_in_object").get<unsigned>()));};
    if(target->first=="controller"){actor["pawn"]=object_field("Pawn");actor["acknowledged_pawn"]=object_field("AcknowledgedPawn");actor["player_state"]=object_field("PlayerState");actor["hud"]=object_field("MyHUD");}
    if(target->first=="pawn"){
     actor["controller"]=object_field("Controller");actor["player_state"]=object_field("PlayerState");actor["root_component"]=object_field("RootComponent");
     if(!actor["root_component"].is_null()){auto root=address(actor["root_component"]);f.property(root,"RelativeLocation",0x190,24);actor["position"]=r.at<Vec>(root+0x190);}
     f.property(pointer,"Role",0x1f8,1);f.property(pointer,"RemoteRole",0x180,1);actor["network_roles"]={{"Role",r.at<uint8_t>(pointer+0x1f8)},{"RemoteRole",r.at<uint8_t>(pointer+0x180)}};
    }
    const std::map<std::string,std::string> arrays{{"controller","controllers"},{"pawn","pawns"},{"game_state","game_states"},{"player_state","player_states"},{"node_probe","settlement_replicators"}};
    auto& values=snapshot.at(arrays.at(target->first));auto existing=std::find_if(values.begin(),values.end(),[&](const Json& item){return item.at("object_index")==index;});if(existing==values.end())values.push_back(actor);else *existing=actor;
    matches.push_back({{"guid",guid.json()},{"guid_hex",hex(Bytes(row,row+16))},{"guid_cache",source.at("guid_cache")},{"weak_object_index",index},{"weak_object_serial",serial},{"actor",actor}});
   }
  }
  require(r.at<uint64_t>(cache+0x10)==entries&&r.at<int32_t>(cache+0x18)==count&&r.at<int32_t>(cache+0x1c)==capacity&&r.at<uint64_t>(driver+0x138)==connection&&r.at<uint64_t>(package+0x338)==cache,"Actor refresh native map changed during observation");
 }
 snapshot["network_guid_actor_matches"]=matches;
 snapshot["full_inspection_observed_at"]=previous.value("full_inspection_observed_at",previous.at("client_proof").at("observed_at").get<double>());
 snapshot["actor_guid_refresh"]={{"method","current driver GUID map; every authored actor revalidated by weak identity and GUID"},{"actors_found",found.size()},{"bytes_read",r.bytes_read},{"observed_at",wall_time()}};
 snapshot["client_proof"]=r.proof();return snapshot;
}
}
