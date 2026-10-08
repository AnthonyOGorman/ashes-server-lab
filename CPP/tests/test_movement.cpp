#include "ashes/movement.hpp"
#include <bit>
#include <iostream>
#include <limits>
using namespace ashes;
static int checks=0;
static void check(bool ok,const char* name){++checks;require(ok,name);}
template<class F>static void refuses(F action,const char* name){bool rejected=false;try{action();}catch(const std::exception&){rejected=true;}check(rejected,name);}
static Json input_move(double t,int flags,Json signs=Json::array({1,0,0,0}),Vec acceleration={8192,0,0},const char* kind="new"){
 return {{"timestamp",t},{"kind",kind},{"compressed_flags",flags},{"custom_axis_sign_bits",signs},{"acceleration",acceleration}};
}
// Independently assemble the existing enclosing codec, including the extension
// after optional mode. These are synthetic protocol vectors, not live captures.
static void wire_move(BitWriter& w,float t,int flags,int signs){
 w.write(std::bit_cast<uint32_t>(t),32);
 for(auto values:{Vec{8192,0,0},Vec{10,-20,30}}){w.bounded(0,128);for(auto v:values)w.write(std::bit_cast<uint32_t>(float(v)),32);}
 w.write(0,1).write(1,1).write(16384,16).write(0,1); // yaw 90, other axes omitted
 w.write(flags!=0,1);if(flags)w.write(flags,8);
 w.write(0,2).write(1,1).write(3,8).write(signs,4);
}
int main(int argc,char** argv){try{
 require(argc==2,"CPP root required");fs::path root=argv[1];
 for(int bits=0;bits<16;++bits){
  Json signs=Json::array();for(int i=0;i<4;++i)signs.push_back((bits>>i)&1);
  auto xy=restore_movement_input(signs);
  check(xy[0]==((bits&1)?1:(bits&2)?-1:0),"Native X positive-bit precedence");
  check(xy[1]==((bits&4)?1:(bits&8)?-1:0),"Native Y positive-bit precedence");
 }
 refuses([]{restore_movement_input({1,0,0});},"Truncated direction extension refused");
 refuses([]{restore_movement_input({1,0,2,0});},"Non-bit direction extension refused");
 BitWriter payload;wire_move(payload,.04f,0x31,15);payload.write(1,1).write(0,1);
 wire_move(payload,.02f,0x10,2);payload.write(1,1);wire_move(payload,239.99f,0,8);payload.write(0,1);
 BitWriter argument;argument.write(1,1).packed(unsigned(payload.bits)).raw(payload.data,payload.bits);
 auto decoded=decode_move_argument(argument.data,argument.bits);
 check(decoded.size()==3,"Packed new/pending/old moves retained");
 check(decoded[0].at("compressed_flags")==0x31&&decoded[0].at("current_movement_input")==Json::array({1.,1.}),"Custom flags and conflicting signs survive packet decoding");
 check(decoded[0].at("acceleration")==Json(Vec{8192,0,0})&&decoded[0].at("client_location")==Json(Vec{10,-20,30}),"Baseline vectors remain separate from direction input");
 check(decoded[0].at("control_rotation")==Json(Vec{0,90,0})&&decoded[0].at("movement_mode")==3,"Optional rotation and mode preserve extension alignment");
 auto ordered=movement_processing_order(decoded);
 check(ordered[0].at("kind")=="old"&&ordered[1].at("kind")=="pending"&&ordered[2].at("kind")=="new","Container order survives timestamp rollover");
 refuses([&]{movement_processing_order(Json::array({decoded[0],decoded[0]}));},"Duplicate container kinds refused");
 auto world=std::make_shared<CollisionWorld>();
 world->load(root/"baseline/evidence/terrain_epoch18_49892/manifest.json",root/"config/frozen-collision.json");
 auto spawn=read_json(root/"tests/fixtures/parity.json").at("movement_spawn").get<Vec>();
 Movement state(world,spawn);state.native_locomotion=true;state.configure({600,false,true});
 // Deliberately distinct synthetic speeds distinguish every directional branch.
 state.ground_speeds={true,false,false,200,150,180,600,400,350};
 check(state.select_speed({1,0},false)==600,"Forward run selects run triplet");
 check(state.select_speed({1,0},true)==200,"Walk request selects walk triplet");
 check(state.select_speed({0,1},false)==400&&state.select_speed({0,-1},true)==150,"Pure lateral selects each gait's lateral field");
 check(state.select_speed({1,1},false)==600&&state.select_speed({-1,1},false)==350,"Diagonals retain forward/backward branch priority");
 auto e=movement_input_epsilon;
 check(state.select_speed({e,1},false)==400&&state.select_speed({-e,-1},false)==400,"Pure lateral X includes exact epsilon boundaries");
 check(state.select_speed({0,e},false)==600&&state.select_speed({0,-e},false)==600,"Pure lateral Y excludes exact epsilon boundaries");
 check(state.select_speed({std::nextafter(e,1.),1},false)==600,"X above epsilon leaves pure lateral branch");
 check(state.select_speed({0,std::nextafter(e,1.)},false)==400,"Y above epsilon enters pure lateral branch");
 check(state.select_speed({-std::nextafter(e,1.),0},false)==350,"Backward predicate uses strict negative threshold");
 state.ground_speeds.use_forward_stat=true;
 check(state.select_speed({1,0},true)==600&&state.select_speed({0,1},true)==150,"Forward stat branch does not replace lateral base");
 state.ground_speeds.use_forward_stat=false;state.ground_speeds.use_backward_stat=true;
 check(state.select_speed({-1,0},true)==600,"Unresolved backward stat retains explicit scalar approximation");
 state.ground_speeds.use_backward_stat=false;
 auto overspeed=state.integrate_velocity({600,0,0},{8192,0,0},.005,10,8192,false,200);
 check(overspeed[0]>500&&overspeed[0]<600,"Run-to-walk overspeed brakes gradually without immediate cap snap");
 auto release=state.integrate_velocity({600,0,0},{0,0,0},.005,10,8192,false,200);
 check(release[0]>500&&release[0]<600,"Overspeed input release preserves post-braking velocity");
 auto opposing=state.integrate_velocity({600,0,0},{-8192,0,0},.005,10,8192,false,200);
 check(opposing[0]>200&&opposing[0]<release[0],"Opposing acceleration reduces overspeed instead of clamping to nominal speed");
 auto crossing=state.integrate_velocity({210,0,0},{8192,0,0},.02,10,8192,false,200);
 check(std::abs(crossing[0]-200)<1e-8,"Braking through cap with forward acceleration stops at effective cap");
 auto tiny=state.integrate_velocity({100,0,0},{.05,0,0},.01,0,8192,false,200);
 check(tiny[0]>100,"Nonzero small baseline acceleration is not treated as released input");
 auto drag_only=state.integrate_velocity({5,0,0},{0,0,0},.02,1,0,false,200);
 check(drag_only[0]>4.8&&drag_only[0]<5,"Pure friction retains velocities below deceleration stop threshold");
 auto unforced=state.integrate_velocity({5,0,0},{0,0,0},.02,0,0,false,200);
 check(unforced[0]==5,"Zero friction and zero braking preserve released-input velocity");
 double threshold=double(float(600.f*600.f)*1.01f);
 check(!exceeding_movement_speed({std::sqrt(threshold)-1e-8,0,0},600)&&exceeding_movement_speed({std::sqrt(threshold)+1e-8,0,0},600),"Native squared-speed tolerance uses strict float-product threshold");
 check(!exceeding_movement_speed({602,0,0},600)&&exceeding_movement_speed({604,0,0},600),"Overspeed tolerance is 1.01 on squared speed");
 state.advance(input_move(1,0x10),1);
 auto walking=state.advance(input_move(1.1,0x10),1.1);
 check(walking&&state.wants_walk&&state.velocity[0]>0&&state.velocity[0]<=200.001,"Walk flag no longer stops server simulation");
 auto running=state.advance(input_move(1.2,0),1.2);
 check(running&&!state.wants_walk&&state.velocity[0]>200&&state.velocity[0]<=600.001,"Walk toggle releases back to normal running");
 auto sprint=state.advance(input_move(1.3,0x20),1.3);
 check(sprint&&state.wants_sprint&&state.effective_speed==600,"Sprint request advances without a guessed speed multiplier");
 auto combined=state.advance(input_move(1.4,0x31),1.4);
 check(combined&&state.wants_walk&&state.wants_sprint&&state.effective_speed==200,"Combined jump/walk/sprint flags accepted with walk speed priority");
 check(combined->at("comparison").at("current_movement_input")==Json::array({1.,0.})&&combined->at("simulation_dt").get<double>()>.09,"Per-move comparison preserves restored input and simulation interval");
 auto position=state.position;auto clock=state.timestamp;
 for(int flags:{2,4,8,0x40,0x80,256,-1})refuses([&]{state.advance(input_move(1.5,flags),1.5);},"Unsupported flags explicitly refused");
 check(state.position==position&&state.timestamp==clock,"Refused flags do not advance authoritative state or clock");
 auto duplicate=state.advance(input_move(1.4,0),1.5);
 check(!duplicate&&state.wants_walk&&state.timestamp==clock,"Duplicate moves do not overwrite latest gait state");
 state.configure({1320,false,false});
 state.advance(input_move(1.5,0x10,{0,0,1,0},{0,8192,0}),1.5);
 check(state.mode==5&&state.effective_speed==1320&&state.velocity[1]>0,"Flight retains its configured speed despite ground gait flags");
 Movement rollover(world,spawn);rollover.configure({600,false,false});rollover.advance(input_move(239.98,0),1);
 auto pending=rollover.advance(input_move(.01,0,{1,0,0,0},{8192,0,0},"pending"),1.03);
 check(pending&&pending->at("timestamp_reset")==true,"Pending move can cross bounded timestamp rollover");
 auto after=rollover.position;
 check(!rollover.advance(input_move(239.99,0,{1,0,0,0},{8192,0,0},"old"),1.04)&&*rollover.timestamp==.01&&rollover.position==after,"Prior-epoch old move cannot poison new epoch clock");
 auto newest=rollover.advance(input_move(.03,0),1.05);
 check(newest&&!newest->contains("discarded_time")&&*rollover.timestamp==.03,"New move continues after redundant pre-reset old move");
 auto gap=rollover.advance(input_move(5,0),1.06);
 check(gap&&gap->contains("discarded_time")&&rollover.position==newest->at("server_position").get<Vec>(),"Large new-move gap retains authoritative state and requests correction");
 check(movement_matches(10,true,true,false),"Existing 10 cm ack boundary retained");
 check(!movement_matches(std::nextafter(10.,11.),true,true,false),"Error above ack boundary requires correction");
 check(!movement_matches(0,false,true,false)&&!movement_matches(0,true,false,false)&&!movement_matches(0,true,true,true),"Mode mismatch, unsynchronized speed or discarded time cannot receive good-move ack");
 check(!movement_matches(std::numeric_limits<double>::quiet_NaN(),true,true,false),"Nonfinite error cannot acknowledge a move");
 Guid owner_guid=Guid::fresh();auto owner_stat=stat_append(owner_guid,0x5429e4778c77030cULL,std::bit_cast<uint32_t>(100.f),1,3);
 BitReader header(owner_stat.data,owner_stat.bits);check(header.read(1)==0&&header.read(1)==0,"Owner stat uses existing non-actor subobject content");
 check(header.read(64)==owner_guid.object&&header.read(32)==owner_guid.server&&header.read(32)==owner_guid.random&&header.read(1)==1,"Owner stat preserves exact component identity");
 auto content_bits=header.packed();BitReader content(header.raw(content_bits),content_bits);check(content.bounded(23)==3,"Stamina uses the verified owner-only field 3");
 auto delta_bits=content.packed();BitReader delta(content.raw(delta_bits),delta_bits);
 check(delta.read(1)==1&&delta.read(32)==1&&delta.read(32)==0&&delta.read(32)==0&&delta.read(32)==1&&delta.read(32)==1,"First owner FastArray insertion has independent keys and item identity");
 check(delta.read(64)==0x5429e4778c77030cULL&&delta.read(32)==std::bit_cast<uint32_t>(100.f)&&delta.remaining()==0,"Stamina wire record and value are exact float bits");
 refuses([&]{stat_append(owner_guid,1,0,1,5);},"Unreviewed stat replication field is refused");
 WorldProtocol login_server([](const std::string&,const Json&){});Connection local;login_server.connections["127.0.0.1:1234"]=local;
 login_server.resolve_character=[](const Json&)->Json{return {{"error","Unknown character token"}};};
 auto login_bytes=encode_control(5,{{"url","?EncryptionToken=invalid"}});
 auto login_packet=encode_packet(0,0,1,0,{0},Json::array({{{"channel",0},{"reliable",true},{"reliable_sequence",1},{"channel_name",255},{"payload_hex",hex(login_bytes)}}}));
 auto refused_login=login_server.handle(login_packet,"127.0.0.1",1234);
 check(login_server.connections.at("127.0.0.1:1234").phase=="closed"&&!refused_login.empty(),"Failed lobby identity binding closes world login with a failure response");
 WorldProtocol retry_server([](const std::string&,const Json&){});Connection retry_connection;retry_connection.phase="joined";
 auto reliable_bunch=[](int sequence){return Json::array({{{"channel",3},{"channel_name",102},{"reliable",true},{"reliable_sequence",sequence},{"payload_hex","00"},{"payload_bits",1}}});};
 retry_server.send(retry_connection,reliable_bunch(49));retry_server.send(retry_connection,reliable_bunch(50));
 retry_connection.pending_at.begin()->second=mono_time()-1.;retry_server.connections["127.0.0.1:4321"]=retry_connection;
 auto ack_only=encode_packet(0,0,1,0,{0});retry_server.handle(ack_only,"127.0.0.1",4321);
 auto& retried=retry_server.connections.at("127.0.0.1:4321");check(retried.channel_reliable.at(3)==50,"Retransmitting older HUD content cannot roll back the issued reliable sequence");
 auto following=decode_packet(retry_server.send(retried,reliable_bunch((retried.channel_reliable.at(3)+1)&1023)),true);
 check(following.at("bunches")[0].at("reliable_sequence")==51,"A new controller initialization message after retry receives a fresh sequence");
 retry_server.send(retried,reliable_bunch(1023));retry_server.send(retried,reliable_bunch(0));retry_server.send(retried,reliable_bunch(1023),false);
 check(retried.channel_reliable.at(3)==0,"Retry preserves channel sequence after native 1024 wrap");
 NativeMoveTiming native_time;native_time.processed_world=1;
 check(std::abs(native_time.delta(.07f,1.003f,false)-.07f)<1e-7f&&!native_time.resolving,"Arrival burst retains valid delta within native discrepancy margin");
 native_time.processed_world=1.003f;
 native_time.delta(.07f,1.006f,false);native_time.processed_world=1.006f;
 native_time.delta(.07f,1.009f,false);native_time.processed_world=1.009f;
 auto restricted=native_time.delta(.07f,1.012f,false);
 check(native_time.resolving&&restricted==.000001f&&native_time.discrepancy>.19f&&native_time.discrepancy<.21f,"Sustained accelerated timestamps trigger native discrepancy payback");
 auto debt=native_time.discrepancy;native_time.processed_world=1.012f;
 native_time.delta(.07f,1.2f,false);
 check(native_time.discrepancy<debt,"Resolution pays down debt against elapsed server time");
 native_time.processed_world=1.2f;native_time.delta(.07f,1.2f,false);
 check(native_time.accumulated>0,"Same-frame resolution preserves accumulated move time");
 auto reset_debt=native_time.discrepancy,reset_raw=native_time.raw_discrepancy,reset_delta=native_time.resolution_delta;
 check(native_time.delta(.05f,2.f,true)==reset_delta&&native_time.discrepancy==reset_debt&&native_time.raw_discrepancy==reset_raw,"Timestamp reset retains active native resolution delta without rerunning discrepancy detection");
 NativeMoveTiming clamp;clamp.detection=false;
 check(clamp.delta(2.f,1.f,false)==1.3125f,"Native maximum move delta is separate from simulation substep");
 Movement burst(world,spawn);burst.native_locomotion=true;burst.timing.enabled=true;burst.configure({600,false,false});
 burst.advance(input_move(1,0),1);
 auto accepted_burst=burst.advance(input_move(1.07,0),1.003);
 check(accepted_burst&&!accepted_burst->contains("discarded_time")&&burst.position[0]>spawn[0],"Native timing simulates a funded margin burst instead of dropping its entire interval");
 auto refused_clock=burst.timestamp;
 check(!burst.advance(input_move(150,0),1.004)&&burst.timestamp==refused_clock,"Native validator refuses positive jumps over half reset interval without poisoning clock");
 burst.timestamp=241.;auto skipped_reset=burst.advance(input_move(.5,0),2.);
 check(!skipped_reset&&*burst.timestamp==1.&&burst.timing.last_reset_world==2.f,"Accepted reset adjusts prediction clock even when resulting delta skips simulation");
 Movement falling(world,spawn);falling.native_locomotion=true;falling.terminal_velocity=4000;falling.configure({600,false,true});falling.velocity={0,0,-3990};
 auto fall_start=falling.position;falling.simulate(input_move(1,0,{0,0,0,0},{0,0,0}),.02);
 check(falling.velocity[2]==-4000&&std::abs(falling.position[2]-fall_start[2]+79.9)<1e-6,"Native falling reaches the live volume limit without integrating acceleration beyond it");
 fall_start=falling.position;for(int i=0;i<100;i++)falling.simulate(input_move(1,0,{0,0,0,0},{0,0,0}),.05);
 check(falling.velocity[2]==-4000&&std::abs(falling.position[2]-fall_start[2]+20000)<1e-5,"Long unsupported native falls retain bounded velocity and distance");
 falling.terminal_velocity=1234;falling.velocity={0,0,-1230};falling.simulate(input_move(1,0,{0,0,0,0},{0,0,0}),.02);
 check(falling.velocity[2]==-1234,"Fall bound follows the selected volume rather than a hardcoded default");
 Movement parabola(world,spawn);parabola.native_locomotion=true;parabola.configure({600,false,true});parabola.gravity=-1225;parabola.jump_velocity=900;parabola.velocity={0,0,900};parabola.terminal_velocity=4000;
 auto launch=parabola.position;auto idle=input_move(1,0,{0,0,0,0},{0,0,0});
 for(int i=0;i<10;++i)parabola.simulate(idle,.05);
 check(std::abs(parabola.velocity[2]-287.5)<1e-8&&std::abs(parabola.position[2]-launch[2]-296.875)<1e-8,"Accepted character gravity multiplier preserves the independent ballistic half-second position and velocity");
 for(int i=0;i<20;++i)parabola.simulate(idle,.05);
 check(std::abs(parabola.velocity[2]+937.5)<1e-8&&std::abs(parabola.position[2]-launch[2]-(-28.125))<1e-8,"Ascent through apex and descent share the same current gravity coefficient");
 Movement jump_launch(world,spawn);jump_launch.native_locomotion=true;jump_launch.gravity=-1225;jump_launch.floor_clearance=2.15;jump_launch.recover_spawn(spawn);
 auto jump_origin=jump_launch.position;auto [jump_contacts,did_jump]=jump_launch.simulate(input_move(1,1,{0,0,0,0},{0,0,0}),.02);
 check(did_jump&&jump_launch.mode==3&&std::abs(jump_launch.velocity[2]-875.5)<1e-8&&std::abs(jump_launch.position[2]-jump_origin[2]-17.755)<1e-6,"Supported stationary jump launches at native900 and applies the synchronized gravity in its first step");
 auto [held_contacts,jumped_again]=jump_launch.simulate(input_move(1,1,{0,0,0,0},{0,0,0}),.02);
 check(!jumped_again&&std::abs(jump_launch.velocity[2]-851)<1e-8,"Held jump does not relaunch a one-count no-hold airborne character");
 std::cout<<checks<<" movement compatibility checks passed (synthetic and offline; no live-client claim)\n";return 0;
 }catch(const std::exception& e){std::cerr<<"FAILED after "<<checks<<" movement checks: "<<e.what()<<'\n';return 1;}
}
