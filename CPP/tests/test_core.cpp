#include "ashes/protocol.hpp"
#include "ashes/movement.hpp"
#include "ashes/contracts.hpp"
#include <iostream>
using namespace ashes;
static int checks=0;static void check(bool ok,const std::string& n){checks++;require(ok,n);}int main(int argc,char** argv){try{require(argc==2,"Fixture path required");auto f=read_json(argv[1]);auto root=fs::path(argv[1]).parent_path().parent_path().parent_path();Guid g=Guid::from(f.at("guid")),p=Guid::from(f.at("pawn"));for(auto& entry:f["bits"]){std::string n=entry.at("name");Bits b;if(n=="ack")b=move_ack(12.25f);else if(n=="correction")b=move_correction(12.25f,{-680500,406500,12503.39},{220,0,900},3);else if(n=="role")b=role_content();else if(n=="begin")b=begin_play_content();else if(n=="controller_state")b=state_link(g,19);else if(n=="pawn_state")b=state_link(g,21);else if(n=="gravity")b=stat_content(g,0x5429e5e8643f0018ULL,0x3f000000);else if(n=="speed")b=stat_content(g,0x6357c09a5679ULL,0x3fd47ae1,2);else if(n=="stats_export")b=stat_export(p,g);else if(n=="info_export")b=character_export(p,g);else if(n=="name")b=character_name(g,"LabExplorer");else if(n=="character_id")b=character_id(g,"00000037000000370000003700000000");else throw std::runtime_error(n);check(hex(b.data)==entry.at("hex").get<std::string>()&&b.bits==entry.at("bits"),"Byte parity "+n);}
for(auto& entry:f["packets"]){auto decoded=decode_packet(unhex(entry.at("hex")),true);check(!decoded.contains("error"),"Captured packet decode");auto& expected=entry.at("decoded");for(auto key:{"sequence","ack","ack_history","session_id","client_id","kind"})check(decoded.at(key)==expected.at(key),"Packet field "+std::string(key));auto b=decoded.at("bunches");auto data=encode_packet(decoded.at("session_id"),decoded.at("client_id"),decoded.at("sequence"),decoded.at("ack"),decoded.at("ack_history").get<std::vector<uint32_t>>(),b);check(hex(data)==entry.at("hex").get<std::string>(),"Exact packet re-encoding");}
// Parse the input gate RPC framing independently; BoolProperty NetSerialize uses one bit.
for(bool ignore:{true,false}){
 auto packet=ignore_move_input(ignore);BitReader outer(packet.data,packet.bits);
 check(outer.read(1)==0&&outer.read(1)==1,"Input gate uses actor RPC-only content");auto count=outer.packed();check(count==outer.remaining(),"Input gate block consumes exact payload");
 BitReader field(outer.raw(count),count);check(field.bounded(1032)==34,"Input gate targets controller field34/max1032");check(field.packed()==1,"Input gate boolean is exactly one wire bit");check(field.read(1)==uint64_t(ignore)&&field.remaining()==0,"Input gate true/false have no trailing parameters");
}
// Traverse the authored packet independently: the metadata probe must contain no NodeGuid or asset properties.
{
 Guid actor{0x1111222233334444ULL,1,77},package{0x5555666677778889ULL,0,0},archetype{0x9999aaaabbbbcccdULL,0,0};Vec location{-680500,406500,12503.1};
 auto bs=node_probe_bunches(1022,actor,package,archetype,location);
 check(bs.size()==2&&bs[0].at("channel")==42&&bs[1].at("channel")==42,"Settlement probe owns a dedicated actor channel");
 check(bs[0].at("reliable_sequence")==1023&&bs[1].at("reliable_sequence")==0&&bs[0].at("open")==true&&bs[0].at("exports")==true,"Settlement probe export/body preserve reliable wrap and opening");
 auto guid_read=[](BitReader& reader){return Guid{reader.read(64),uint32_t(reader.read(32)),uint32_t(reader.read(32))};};
 std::function<Json(BitReader&,int)> reference=[&](BitReader& reader,int depth)->Json{
  require(depth<8,"Export depth bound");auto g=guid_read(reader);Json row={{"guid",g.json()}};if(g.object==0)return row;
  auto flags=reader.read(8);row["flags"]=flags;if(flags&1){row["outer"]=reference(reader,depth+1);row["path"]=reader.string();if(flags&4)row["checksum"]=reader.read(32);}return row;
 };
 BitReader ex(unhex(bs[0].at("payload_hex")),bs[0].at("payload_bits"));check(ex.read(1)==0&&ex.read(32)==2,"Settlement probe exports exactly archetype and current level");
 auto exported=reference(ex,0),level=reference(ex,0);
 check(exported.at("guid")==archetype.json()&&exported.at("path")=="Default__NodeLayoutReplicator"&&exported.at("checksum")==4242000812u&&exported.at("flags")==5,"Settlement archetype path and checksum match reviewed capture");
 check(exported.at("outer").at("guid")==package.json()&&exported.at("outer").at("path")=="/Script/GameSystemsPlugin"&&exported.at("outer").at("flags")==1,"Settlement script package uses a new authored loadable reference");
 check(level.at("path")=="PersistentLevel"&&ex.remaining()==0,"Settlement export has no unreviewed asset references");
 BitReader body(unhex(bs[1].at("payload_hex")),bs[1].at("payload_bits"));check(guid_read(body)==actor&&guid_read(body)==archetype&&guid_read(body).json()==level.at("guid"),"Settlement actor construction uses authored identities/current level");
 check(body.read(1)==1&&body.read(1)==1,"Settlement probe has a bounded packed location");auto packed=body.read(7);unsigned width=unsigned(packed&63);Vec decoded{};for(auto& v:decoded){auto raw=body.read(width);int64_t signed_value=int64_t(raw);if(raw&(1ULL<<(width-1)))signed_value-=int64_t(1ULL<<width);v=double(signed_value)/10;}
 check((packed&64)&&length(sub(location,decoded))<.001&&body.read(3)==0,"Settlement probe preserves location and default rotation/scale/velocity");
 check(body.read(1)==1&&body.read(1)==1,"Settlement probe uses a reviewed actor property content block");auto length_bits=body.packed();BitReader content(body.raw(length_bits),length_bits);
 check(length_bits==9&&content.read(1)==0&&content.packed()==0&&content.remaining()==0&&body.remaining()==0,"Settlement probe content terminates without NodeGuid or layout fields");
 bool refused=false;try{node_probe_bunches(1,archetype,package,archetype,location);}catch(const std::exception&){refused=true;}check(refused,"Settlement probe refuses a static actor identity");
 refused=false;try{node_probe_bunches(1,actor,actor,archetype,location);}catch(const std::exception&){refused=true;}check(refused,"Settlement probe refuses dynamic package export identity");
 refused=false;try{node_probe_bunches(1,actor,package,package,location);}catch(const std::exception&){refused=true;}check(refused,"Settlement probe refuses reused export identities");
}
// Review-bound first-floor packet: independently traverse every field and exact end.
{
 auto floor=winstead_floor_content();check(floor.bits==1081,"Winstead floor actor block matches reviewed total length");
 BitReader block(floor.data,floor.bits);check(block.read(1)==1&&block.read(1)==1&&block.packed()==1063,"Winstead floor actor property envelope");
 check(block.read(1)==0&&block.packed()==25&&block.read(64)==0x62d024b45678ULL&&block.packed()==0,"Winstead floor ordinary NodeGuid segment");
 check(block.bounded(16)==13&&block.packed()==962,"Winstead floor custom field13/max16 and delta length");
 check(block.read(1)==1,"Winstead floor supports standard FastArray delta structs");
 check(block.read(8)==1&&block.read(8)==0&&block.read(8)==1,"Winstead floor explicit Crossroads Kaelar Spring profile");
 check(block.read(1)==1&&block.read(8)==1,"Winstead floor empty tag bit omits count and preserves byte version");
 check(block.read(32)==1&&block.read(32)==0&&block.read(32)==0&&block.read(32)==1,"Winstead floor initial delta keys/counts");
 check(block.read(32)==1&&block.read(64)==0x62d024b45678ULL&&block.read(32)==0&&block.read(32)==14&&block.read(64)==0x5429e761b0070000ULL,"Winstead floor item belongs to exact layout prop14");
 for(int i=0;i<6;i++)check(block.read(64)==0,"Winstead floor identity quaternion XYZ and translation");
 for(int i=0;i<3;i++)check(block.read(64)==0x3ff0000000000000ULL,"Winstead floor identity scale double representation");
 check(block.remaining()==0,"Winstead floor has no additional asset, tag count, quaternion W or terminator");
 write_file(root/"runs/settlement-probe-20261008/floor-wire.json",Json{{"payload_hex",hex(floor.data)},{"payload_bits",floor.bits}}.dump(2));
}
for(uint32_t bound:{2u,3u,127u,198u,8224u})for(uint32_t value:{0u,1u,bound-1}){BitWriter w;w.bounded(value,bound);BitReader r(w.data,w.bits);check(r.bounded(bound)==value&&r.remaining()==0,"Variable bounded SerializeInt");}
Contracts contracts(root/"config/contracts.json");Json wrapper={{"message_type_name","ics_common.SessionRequest"},{"message_data",hex(contracts.encode("ics_common.SessionRequest",{{"request_type",1},{"tags",{{"hello","world"}}}}))},{"status_code",43},{"system_data",{{"tags",{{"a","b"}}}}}};auto round=contracts.decode("ics_common.MessageWrapper",contracts.encode("ics_common.MessageWrapper",wrapper));check(round==wrapper,"Installed protobuf schema roundtrip");
auto world=std::make_shared<CollisionWorld>();
Vec spawn=f.at("movement_spawn").get<Vec>();
auto plane=std::make_shared<Shape>(Json{{"triangles",std::vector<Triangle>{Triangle{{{spawn[0]-100000,spawn[1]-100000,12000},{spawn[0]+100000,spawn[1]-100000,12000},{spawn[0],spawn[1]+100000,12000}}}}}});
world->meshes.emplace_back(plane,Json::array({1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}));
Movement movement(world,spawn);movement.advance({{"timestamp",1},{"acceleration",Vec{}},{"compressed_flags",0}},1);
auto before=movement.position;double budget=movement.budget;auto discarded=movement.advance({{"timestamp",1000},{"acceleration",Vec{}},{"compressed_flags",0},{"kind","new"}},103);check(discarded&&discarded->contains("discarded_time")&&movement.position==before,"Gap discards interval preserving state");check(movement.budget<=.5&&movement.budget>=budget,"Bounded wall clock funding");
Movement rollover(world,f.at("movement_spawn").get<Vec>());rollover.advance({{"timestamp",239.99},{"acceleration",Vec{}},{"compressed_flags",0},{"kind","new"}},1);auto reset=rollover.advance({{"timestamp",.01},{"acceleration",Vec{}},{"compressed_flags",0},{"kind","new"}},1.02);check(reset&&reset->at("timestamp_reset")==true,"Native 240s clock rollover");

Movement flyer(world,f.at("movement_spawn").get<Vec>());flyer.configure(MovementSettings{1320,false,false});
auto original=flyer.position;flyer.change_altitude(1000);check(flyer.position[2]==original[2]+1000&&flyer.mode==5,"Flight altitude changes without floor snapping");
flyer.advance({{"timestamp",1},{"acceleration",Vec{8192,0,0}},{"compressed_flags",0}},1);
flyer.advance({{"timestamp",1.2},{"acceleration",Vec{8192,0,0}},{"compressed_flags",0}},1.2);
check(std::abs(flyer.velocity[0]-1320)<.001&&flyer.position[2]==original[2]+1000,"Flight speed cap and gravity disabled");
flyer.advance({{"timestamp",1.3},{"acceleration",Vec{}},{"compressed_flags",0}},1.3);check(length(flyer.velocity)<1320,"Flight input release brakes motion");
flyer.configure(MovementSettings{100,false,false});check(length(flyer.velocity)<=100.001,"Lowering speed clamps existing velocity");
flyer.advance({{"timestamp",1.4},{"acceleration",Vec{0,0,8192}},{"compressed_flags",0}},1.4);check(flyer.velocity[2]>0&&flyer.mode==5,"Flight accepts vertical input");
flyer.configure(MovementSettings{220,false,true});flyer.advance({{"timestamp",1.5},{"acceleration",Vec{}},{"compressed_flags",0}},1.5);check(flyer.velocity[2]<0&&flyer.mode==3,"Gravity restored while collision stays disabled");
bool refused=false;try{flyer.change_altitude(1000);}catch(const std::exception&){refused=true;}check(refused,"Walking refuses flight altitude control");
refused=false;try{MovementSettings::from({{"speed",10001},{"collision_enabled",true},{"gravity_enabled",true}});}catch(const std::exception&){refused=true;}check(refused,"Out-of-range movement setting refused");
refused=false;try{MovementSettings::from({{"speed",220},{"collision_enabled",1},{"gravity_enabled",true}});}catch(const std::exception&){refused=true;}check(refused,"Movement toggles require booleans");
auto obstacle=std::make_shared<CollisionWorld>();
 auto wallShape=std::make_shared<Shape>(Json{{"triangles",std::vector<Triangle>{Triangle{{{0,-10000,-10000},{0,10000,-10000},{0,0,10000}}}}}});
 obstacle->meshes.emplace_back(wallShape,Json::array({1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}));
 Movement blocked(world,f.at("movement_spawn").get<Vec>());blocked.world=obstacle;blocked.position={-100,0,0};blocked.half_height=20;blocked.radius=10;blocked.configure(MovementSettings{1320,true,false});
 blocked.advance({{"timestamp",1},{"acceleration",Vec{8192,0,0}},{"compressed_flags",0}},1);
 blocked.advance({{"timestamp",1.2},{"acceleration",Vec{8192,0,0}},{"compressed_flags",0}},1.2);
 check(blocked.position[0]<=-9.9,"Flight with collision enabled stops at wall");
 Movement unblocked(world,f.at("movement_spawn").get<Vec>());unblocked.world=obstacle;unblocked.position={-100,0,0};unblocked.configure(MovementSettings{1320,false,false});
 unblocked.advance({{"timestamp",1},{"acceleration",Vec{8192,0,0}},{"compressed_flags",0}},1);
 unblocked.advance({{"timestamp",1.2},{"acceleration",Vec{8192,0,0}},{"compressed_flags",0}},1.2);
 check(unblocked.position[0]>0,"Disabling collision lets flight cross wall");
 auto update=stat_update(g,0x6357c09a5679ULL,0x3f800000,3,2,2);BitReader statReader(update.data,update.bits);
check(statReader.read(1)==0&&statReader.read(1)==0,"Speed update retains existing subobject header");statReader.read(64);statReader.read(32);statReader.read(32);check(statReader.read(1)==1,"Speed update has component content");auto statBits=statReader.packed();BitReader fieldReader(statReader.raw(statBits),statBits);check(fieldReader.bounded(23)==6,"Speed update uses reviewed field6");auto deltaBits=fieldReader.packed();BitReader deltaReader(fieldReader.raw(deltaBits),deltaBits);check(deltaReader.read(1)==0&&deltaReader.read(32)==3&&deltaReader.read(32)==2,"Speed update advances array key and base key");check(deltaReader.read(32)==0&&deltaReader.read(32)==1&&deltaReader.read(32)==2,"Speed update changes item2 without adding another speed item");check(deltaReader.read(64)==0x6357c09a5679ULL&&deltaReader.read(32)==0x3f800000&&deltaReader.remaining()==0,"Speed update preserves record and requested multiplier");
CorrectionPolicy correctionPolicy;check(correctionPolicy.allow(1,20,false,false),"Initial correction is immediate");correctionPolicy.last_sent=1;check(!correctionPolicy.allow(1.05,20,false,false),"Small repeated errors defer correction during cadence window");check(correctionPolicy.allow(1.101,20,false,false),"Correction resumes after cadence window");check(correctionPolicy.allow(1.01,100,false,false),"Large errors correct immediately");check(correctionPolicy.allow(1.01,1,true,false),"Movement mode changes correct immediately");check(correctionPolicy.allow(1.01,1,false,true),"Discarded simulation time corrects immediately");
Movement native(world,f.at("movement_spawn").get<Vec>());native.native_locomotion=true;native.speed=600;
 auto turn=native.integrate_velocity(Vec{600,0,0},Vec{0,8192,0},.02,10,8192,false);check(turn[0]<490&&turn[1]>200,"Native ground friction follows a direction change");
 auto stop=native.integrate_velocity(Vec{600,0,0},Vec{},.02,10,8192,false);check(stop[0]<420&&stop[0]>300,"Native braking includes ground friction");
 native.speed=1320;auto coast=native.integrate_velocity(Vec{1320,0,0},Vec{},.02,.15,3000,true);check(coast[0]>1250&&coast[0]<1260,"Native flight release uses 3000 braking rather than walking acceleration");
 auto sign=native.integrate_velocity(Vec{20,0,0},Vec{},.05,10,8192,false);check(length(sign)==0,"Native braking stops without reversing direction");
 native.max_interval=.5;native.budget=.5;native.configure(MovementSettings{600,false,false});native.advance({{"timestamp",1},{"acceleration",Vec{8192,0,0}},{"compressed_flags",0}},1);auto queued=native.advance({{"timestamp",1.35},{"acceleration",Vec{8192,0,0}},{"compressed_flags",0}},1.35);check(queued&&!queued->contains("discarded_time"),"Bounded low-frame-rate interval simulates with substeps");
 auto flyCorrection=move_correction(1.f,flyer.position,Vec{},5);check(flyCorrection.bits>0,"Flying mode encodes in native correction");
Triangle wall{{{0,-100,-100},{0,100,-100},{0,0,100}}};auto hit=sweep_triangle({-50,0,0},{100,0,0},20,10,wall);check(hit&&std::abs(hit->fraction-.4)<.001,"Continuous capsule wall contact");auto limited=limit_upward_slide({10,0,10},{10,0,-10},{-.7,0,.7});check(limited[2]<=0,"Falling contact cannot boost upward");std::cout<<checks<<" C++ checks passed; protocol bytes and synthetic movement/collision checks agree\n";return 0;}catch(const std::exception& e){std::cerr<<"FAILED after "<<checks<<" checks: "<<e.what()<<'\n';return 1;}}
