#include "ashes/backend.hpp"
#include <bit>
namespace ashes {
GroundSpeedProfile read_ground_speed_profile(Reflection& f,uint64_t movement){
 f.identity(movement,"AoCCharacterMovement");
 // Exact-build sender and receiver read these same uint32 globals. Refuse
 // activation if their effective byte masks differ from the supported contract.
 for(auto [rva,mask]:std::array<std::pair<uint64_t,uint32_t>,3>{{{0xd378c7c,0x10},{0xd378c80,0x20},{0xd378c84,0x40}}})
  require((f.r.at<uint32_t>(f.r.base+rva)&255)==mask,"Current native gait masks differ from the supported movement contract");
 auto scalar=[&](const char* name,int offset){
  auto prop=f.property(movement,name,offset,4);
  require(prop.at("type")=="FloatProperty","Reviewed live directional float required");
  double value=f.r.at<float>(movement+offset);
  require(std::isfinite(value)&&value>=0&&value<=10000,"Live directional speed bounds");return value;
 };
 auto flag=[&](const char* name,int offset){
  auto prop=f.property(movement,name,offset,1);
  require(prop.at("type")=="BoolProperty","Reviewed live directional stat flag required");
  auto address=std::stoull(prop.at("address").get<std::string>(),nullptr,16);
  auto masks=f.r.read(address+0x70,4);
  require(masks[0]==1&&masks[1]==0&&masks[3]==255,"Native scalar bool layout required");
  auto value=f.r.at<uint8_t>(movement+offset);require(value<=1,"Native scalar bool value required");return value!=0;
 };
 GroundSpeedProfile p;
 p.walk_forward=scalar("MaxWalkSpeed",0x2c8);p.walk_lateral=scalar("MaxWalkStrafeSpeed",0x1020);p.walk_backward=scalar("MaxWalkSpeedBackward",0x1024);
 p.run_forward=scalar("MaxRunSpeed",0x1028);p.run_lateral=scalar("MaxRunStrafeSpeed",0x102c);p.run_backward=scalar("MaxRunSpeedBackward",0x1030);
 require(p.run_forward>0,"Positive live run-speed base required");
 p.use_forward_stat=flag("bUseMovementSpeedStat",0x1090);p.use_backward_stat=flag("bUseBackwardsMovementSpeedStat",0x10d0);
 p.runtime_masks_verified=true;p.available=true;return p;
}
Json read_falling_profile(Reflection& f,uint64_t pawn,uint64_t movement,uint64_t volume,uint64_t settings){
 auto& r=f.r;
 auto slot=[&](uint64_t object,size_t offset,uint64_t target){require(r.at<uint64_t>(r.at<uint64_t>(object)+offset)==r.base+target,"Current falling getter binding changed");};
 auto scalar=[&](uint64_t object,const char* name){auto p=f.find_property(object,name);require(p.at("type")=="FloatProperty"&&p.at("element_size")==4,"Current falling float property required");float v=r.at<float>(object+p.at("offset_in_object").get<unsigned>());require(std::isfinite(v)&&std::abs(v)<=100000,"Current falling scalar bounds");return v;};
 auto boolean=[&](uint64_t object,const char* name){auto p=f.find_property(object,name);require(p.at("type")=="BoolProperty"&&p.at("element_size")==1,"Current falling bool property required");auto a=std::stoull(p.at("address").get<std::string>(),nullptr,16);auto masks=r.read(a+0x70,4);require(masks[0]==1&&masks[3],"Current falling bool mask required");return (r.at<uint8_t>(object+p.at("offset_in_object").get<unsigned>()+masks[1])&masks[3])!=0;};
 f.identity(pawn,"Character");f.identity(movement,"AoCCharacterMovement");f.identity(volume,"PhysicsVolume");f.identity(settings,"WorldSettings");
 slot(movement,0x560,0x5ea4b00);slot(movement,0x770,0x5ea1480);slot(movement,0x588,0x3e46dd0);
 // Custom GetGravityZ reads this native cached owner before its CF0/CF8 dispatch.
 require(r.at<uint64_t>(movement+0x1300)==pawn,"Current native gravity owner must match the possessed pawn");
 slot(pawn,0xcf0,0x6b411a0);slot(pawn,0xcf8,0x6b4d430);slot(volume,0x840,0x441e300);slot(settings,0x840,0x47bad50);
 require(!boolean(volume,"bWaterVolume"),"Water falling simulation is not available");
 auto capsule=f.component(pawn,"CapsuleComponent");f.property(movement,"UpdatedComponent",0x108,8);require(r.at<uint64_t>(movement+0x108)==capsule,"Falling physics must use the current root capsule");
 auto stats=f.component(pawn,"StatsComponent");f.property(pawn,"StatsComponent",0xf60,8);require(!boolean(stats,"bIsSlowFalling"),"Slow-fall gravity requires a separate reviewed profile");
 require(r.read(r.base+0x612dae0,8)==unhex("0fb68144080000c3"),"Native slow-fall getter changed");
 auto mesh=f.component(pawn,"Mesh");auto anim_prop=f.find_property(mesh,"AnimScriptInstance");require(anim_prop.at("type")=="ObjectProperty"&&anim_prop.at("element_size")==8,"Current animation binding required");auto anim=r.at<uint64_t>(mesh+anim_prop.at("offset_in_object").get<unsigned>());
 require(anim,"Current animation instance required for gravity modifiers");f.identity(anim,"AoCAnimInstance");require(r.at<int32_t>(anim+0xc0)==0,"Active animation gravity modifiers require additional evaluation");
 require(r.read(r.base+0x43f8f87,7)==unhex("488b0582cf4509"),"PhysicsSettings class getter changed");auto cls=r.at<uint64_t>(r.base+0xd855f10);require(f.identity(cls,"Class").at("name")=="PhysicsSettings","Exact PhysicsSettings class required");auto cdo=r.at<uint64_t>(cls+0x150);require(f.identity(cdo,"PhysicsSettings").at("name")=="Default__PhysicsSettings","Exact PhysicsSettings default required");
 // WorldSettings uses its cached value when initialized, then GlobalGravityZ
 // when configured, otherwise the PhysicsSettings default. Do not invoke it.
 f.property(settings,"WorldGravityZ",0x3f0,4);f.property(settings,"GlobalGravityZ",0x3f4,4);
 auto bits=r.at<uint8_t>(settings+0x376);float world_gravity=(bits&1)?scalar(settings,"WorldGravityZ"):boolean(settings,"bGlobalGravitySet")?scalar(settings,"GlobalGravityZ"):scalar(cdo,"DefaultGravityZ");
 float character_scale=std::bit_cast<float>(read_resource_stat(f,stats,0x5429e5e8643f0018ULL,7));auto replicated=read_replicated_stat_item(f,stats,"StatRepInt32EveryoneProxy",0x5429e5e8643f0018ULL);
 require(replicated.is_object()&&replicated.at("item_id")==1&&replicated.at("value_bits")==std::bit_cast<uint32_t>(character_scale),"Native gravity cache and accepted replication must agree");
 float gravity_scale=scalar(movement,"GravityScale"),effective=(world_gravity*gravity_scale)*character_scale;
 require(world_gravity<0&&gravity_scale>0&&character_scale>0&&std::isfinite(effective)&&effective<0,"Reviewed downward finite gravity required");
 auto direction=f.find_property(movement,"GravityDirection");require(direction.at("type")=="StructProperty"&&direction.at("element_size")==24&&r.at<Vec>(movement+direction.at("offset_in_object").get<unsigned>())==Vec{0,0,-1},"Reviewed vertical gravity direction required");
 require(boolean(movement,"bApplyGravityWhileJumping"),"Gravity during jump must match reviewed falling path");require(scalar(pawn,"JumpMaxHoldTime")==0,"Variable jump hold requires separate simulation");
 auto count=f.property(pawn,"JumpMaxCount",0x53c,4);require(count.at("type")=="IntProperty"&&r.at<int32_t>(pawn+0x53c)==1,"Reviewed one-count jump required");
 Json out={{"world_gravity",world_gravity},{"movement_gravity_scale",gravity_scale},{"character_gravity_scale",character_scale},{"effective_gravity",effective},{"slow_falling",false},{"animation_modifiers",0},{"source","current native getter bindings, reflected settings and accepted stat cache"}};
 for(auto [key,name]:std::array<std::pair<const char*,const char*>,6>{{{"jump_velocity","JumpZVelocity"},{"air_control","AirControl"},{"air_control_boost","AirControlBoostMultiplier"},{"air_control_boost_threshold","AirControlBoostVelocityThreshold"},{"falling_friction","FallingLateralFriction"},{"braking_fall","BrakingDecelerationFalling"}}}){auto v=scalar(movement,name);require(v>=0,"Nonnegative native falling settings required");out[key]=v;}
 require(out.at("jump_velocity").get<float>()>0,"Positive native jump velocity required");return out;
}
Json read_replicated_stat_item(Reflection& f,uint64_t stats,const std::string& field,uint64_t record){
 auto prop=f.find_property(stats,field);require(prop.at("type")=="StructProperty"&&prop.at("element_size")==0x120,"Reviewed Int32 FastArray wrapper required");
 auto base=stats+prop.at("offset_in_object").get<unsigned>();auto data=f.r.at<uint64_t>(base+0x108);int count=f.r.at<int32_t>(base+0x110),capacity=f.r.at<int32_t>(base+0x114);
 require(count>=0&&count<=capacity&&capacity<=2048&&(!count||data),"Bounded native replicated stats required");Json found;
 for(int i=0;i<count;i++){auto item=data+size_t(i)*40;if(f.r.at<uint64_t>(item+16)!=record)continue;require(found.is_null(),"Unique replicated stat record required");found={{"item_id",f.r.at<int32_t>(item)},{"value_bits",f.r.at<uint32_t>(item+24)}};}
 return found;
}
}
