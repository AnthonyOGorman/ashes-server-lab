#pragma once
#include "common.hpp"
#include <map>
#include <functional>
#include <bitset>
#include <set>
namespace ashes {
struct BitWriter {Bytes data;size_t bits=0;BitWriter& write(uint64_t,size_t);BitWriter& raw(const Bytes&,size_t);BitWriter& raw(const Bytes& b){return raw(b,b.size()*8);}BitWriter& packed(uint32_t);BitWriter& bounded(uint32_t,uint64_t);BitWriter& string(const std::string&);Bytes finish(int=0);};
struct BitReader {Bytes data;size_t limit,pos=0;BitReader(const Bytes&,size_t);BitReader(const Bytes& b):BitReader(b,b.size()*8){}size_t remaining()const{return limit-pos;}uint64_t read(size_t);Bytes raw(size_t);uint32_t packed();uint32_t bounded(uint64_t);std::string string();};
struct Bits {Bytes data;size_t bits;};
using MovementInput=std::array<double,2>;
constexpr double movement_input_epsilon=double(.0001f);
MovementInput restore_movement_input(const Json& sign_bits);
Json movement_processing_order(const Json& moves);
struct Guid {uint64_t object=0;uint32_t server=0,random=0;void write(BitWriter&)const;Json json()const;static Guid from(const Json&);static Guid fresh();bool operator==(const Guid&)const=default;};
Json decode_packet(const Bytes&,bool server=false,unsigned payload_max=8224);Bytes encode_packet(int,int,int,int,const std::vector<uint32_t>&,const Json& bunches=Json::array(),std::optional<uint64_t> info={});Bytes encode_handshake(const Json&,int,double,const Bytes&);Bytes encode_control(int,const Json& values=Json::object());
Bits actor_rpc(int,int,const Bits&);Json decode_actor_rpc(const Bytes&,size_t,int);Json decode_move_argument(const Bytes&,size_t);Bits move_ack(float);Bits move_correction(float,Vec,Vec,int);Bits role_content();Bits begin_play_content();Bits state_link(Guid,int);Bits subobject_empty(Guid);Bits stat_content(Guid,uint64_t,uint32_t,int=1);Bits stat_append(Guid,uint64_t,uint32_t,int,int);Bits stat_update(Guid,uint64_t,uint32_t,int,int,int);Bits stat_export(Guid,Guid);Bits character_export(Guid,Guid);Bits character_name(Guid,const std::string&);Bits character_id(Guid,const std::string&);Json controller_bunches(int,Guid);Json scene_bunches(int,const std::string&,Guid,Vec);Json hud_bunches(int,int,int);Bits object_argument(Guid);
struct Connection {Bytes cookie;int session=0,client=0,out_seq=0,in_seq=0,out_reliable=0,in_reliable=0;std::bitset<256> history;std::string phase="connected",id=random_id(12);double last_seen=mono_time(),handshake_time=0;std::optional<uint64_t> info;std::string selected_character_id,selected_character_name;std::map<int,int> channel_reliable;std::map<std::string,Guid> actors;std::map<int,Json> pending;std::map<int,double> pending_at;std::set<std::string> stages;std::string initialization_status="Waiting for world load",initialization_error;bool initialization_failed=false;double initialization_started=0;double speed_synced=0,speed_sync_sent=0;uint32_t speed_sync_bits=0;int stats_array_key=2;std::string speed_sync_status="Waiting for character";bool possession=false;int ack_field=-1,controller_max=0;};
Json node_probe_bunches(int initial,Guid actor,Guid package,Guid archetype,Vec location);
Bits winstead_floor_content();
Bits ignore_move_input(bool ignore);
using Event=std::function<void(const std::string&,const Json&)>;
struct WorldProtocol {Bytes secret=random_bytes(32);std::map<std::string,Connection> connections;Event event;std::function<Json(const Json&)> resolve_character;explicit WorldProtocol(Event e):event(std::move(e)){}Bytes cookie(const std::string&,uint16_t,double)const;std::vector<Bytes> handle(const Bytes&,const std::string&,uint16_t);Bytes send(Connection&,const Json& bunches=Json::array(),bool track_reliable=true);std::vector<Bytes> bootstrap(Connection&,Vec);};
}
