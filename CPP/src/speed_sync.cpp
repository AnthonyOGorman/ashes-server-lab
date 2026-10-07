#include "ashes/backend.hpp"
#include <bit>
#include <algorithm>
namespace ashes {
namespace {
uint64_t address(const Json& j){return std::stoull(j.at("address").get<std::string>(),nullptr,16);}
Json actor_for(const Json& snapshot,Guid guid,const std::string& cls){
 Json found;for(auto& row:snapshot.at("network_guid_actor_matches"))if(row.at("guid")==guid.json()){
 require(found.is_null(),"Unique accepted speed-sync actor required");require(row.at("actor").at("class")==cls,"Speed-sync actor class changed");found=row;
 }require(!found.is_null(),"Accepted speed-sync actor missing");return found;
}
float scalar(Reflection& f,uint64_t object,const std::string& name){auto prop=f.find_property(object,name);require(prop.at("type")=="FloatProperty"&&prop.at("element_size")==4,"Current float movement property required");float v=f.r.at<float>(object+prop.at("offset_in_object").get<unsigned>());require(std::isfinite(v)&&v>0&&v<=10000,"Current movement speed bounds");return v;}
}
void Backend::synchronize_movement_speed(){
 Connection connection;double target_speed=0;uint32_t pid=0;
 {
 std::lock_guard lock(mutex);if(!world.running||!client_process.process)return;
 for(auto& [peer,c]:protocol.connections)if(c.possession&&c.stages.contains("ActivateMovement")&&players.contains(c.id)&&c.speed_synced!=players.at(c.id)->speed){
 if(c.speed_sync_sent&&mono_time()-c.speed_sync_sent<.75)continue;connection=c;target_speed=players.at(c.id)->speed;pid=client_process.pid;break;
 }
 }if(!pid)return;
 try{
 ProcessReader r(pid,config.at("client_exe").get<std::string>(),config.at("client_sha256"));Reflection f(r);
 auto snapshot=read_json(root/"data/client-inspection.json");auto prior=snapshot.at("client_proof"),current=r.proof();
 for(auto key:{"pid","exe","sha256","process_created_filetime"})require(prior.at(key)==current.at(key),"Speed-sync client lifetime changed");
 auto pawn=actor_for(snapshot,connection.actors.at("pawn"),"PlayerPawn_C"),pc=actor_for(snapshot,connection.actors.at("controller"),"AoCPlayerControllerBP_C");
 for(auto row:{pawn,pc}){auto live=f.identity(address(row.at("actor")));require(live.at("object_index")==row.at("weak_object_index")&&live.at("serial")==row.at("weak_object_serial"),"Speed-sync current actor weak identity changed");}
 uint64_t player=address(pawn.at("actor")),controller=address(pc.at("actor")),driver=0;
 require(pawn.at("guid_cache")==pc.at("guid_cache"),"Speed-sync shared GUID cache required");
 for(auto& d:snapshot.at("net_drivers"))if(d.at("guid_cache")==pawn.at("guid_cache")){require(!driver,"Unique current owning driver required");driver=address(d);}
 require(driver&&f.guid_accepted(driver,connection.actors.at("pawn"),player)&&f.guid_accepted(driver,connection.actors.at("controller"),controller),"Current actor GUID acceptance required");
 f.property(controller,"Pawn",0x3a8,8);f.property(controller,"AcknowledgedPawn",0x428,8);f.property(player,"Controller",0x398,8);
 require(r.at<uint64_t>(controller+0x3a8)==player&&r.at<uint64_t>(controller+0x428)==player&&r.at<uint64_t>(player+0x398)==controller,"Current mutual possession required for speed update");
 auto movement=f.component(player,"CharacterMovement");f.identity(movement,"AoCCharacterMovement");
 // Normal forward input reaches MaxRunSpeed * MoveSpeedMult in this client;
 // the live capture independently measured 600 * 1.66 = 996 cm/s.
 double base=scalar(f,movement,"MaxRunSpeed");
 float multiplier=float(target_speed/base);require(std::isfinite(multiplier)&&multiplier>0&&multiplier<=1000,"Speed multiplier bounds");uint32_t desired=std::bit_cast<uint32_t>(multiplier);
 uint64_t stats=f.component(player,"StatsComponent");f.identity(stats,"AoCStatsComponent");
 require(connection.actors.contains("stats_component")&&f.guid_accepted(driver,connection.actors.at("stats_component"),stats),"Current accepted stats component required");
 f.property(stats,"StatRepInt32EveryoneProxy",0xbf0,0x120);auto cache=f.network_cache(f.object(stats).at("class_address"),driver);
 require(cache.at("maximum")==23&&std::count_if(cache.at("fields").begin(),cache.at("fields").end(),[](auto& v){return v.at("index")==6&&v.at("name")=="StatRepInt32EveryoneProxy";})==1,"Reviewed speed stat field required");
 require(r.at<uint64_t>(stats+0xd08)>0&&r.at<uint8_t>(stats+0xcf0)==1,"Initialized stats receive delegate required");
 uint64_t data=r.at<uint64_t>(stats+0xcf8);int count=r.at<int32_t>(stats+0xd00),capacity=r.at<int32_t>(stats+0xd04);
 require(count==2&&count<=capacity&&capacity<=2048,"Exactly initialized gravity and speed items required");
 require(r.at<int32_t>(data)==1&&r.at<uint64_t>(data+16)==0x5429e5e8643f0018ULL,"Accepted gravity item identity required");
 require(r.at<int32_t>(data+40)==2&&r.at<uint64_t>(data+56)==0x6357c09a5679ULL,"Accepted speed item identity required");
 uint32_t actual=r.at<uint32_t>(data+64);r.verify_alive();
 std::lock_guard lock(mutex);for(auto& [peer,c]:protocol.connections)if(c.id==connection.id&&c.actors==connection.actors&&players.contains(c.id)&&players.at(c.id)->speed==target_speed){
 if(actual==desired){c.speed_synced=target_speed;c.speed_sync_status="Client speed synchronized";event("movement_speed_verified",{{"connection_id",c.id},{"speed_cm_s",target_speed},{"base_run_speed",base},{"client_multiplier",multiplier},{"pid",pid}});}
 else if(!c.speed_sync_sent||c.speed_sync_bits!=desired){
 require(c.stats_array_key<0x7ffffffe,"Stat key exhausted");auto delta=stat_update(c.actors.at("stats_component"),0x6357c09a5679ULL,desired,c.stats_array_key+1,c.stats_array_key,2);
 send_world(c,Json::array({{{"channel",9},{"channel_name",102},{"reliable",true},{"reliable_sequence",(c.channel_reliable.at(9)+1)&1023},{"payload_hex",hex(delta.data)},{"payload_bits",delta.bits}}}));++c.stats_array_key;c.speed_sync_bits=desired;c.speed_sync_sent=mono_time();c.speed_sync_status="Waiting for client speed readback";
 }else{c.speed_sync_status="Waiting for client speed readback";c.speed_sync_sent=mono_time();}
 }
 }catch(const std::exception& error){std::lock_guard lock(mutex);for(auto& [peer,c]:protocol.connections)if(c.id==connection.id){std::string status="Speed synchronization blocked: "+std::string(error.what());if(c.speed_sync_status!=status)event("movement_speed_refused",{{"connection_id",c.id},{"reason",error.what()}});c.speed_sync_status=status;c.speed_sync_sent=mono_time();}}
}
}
