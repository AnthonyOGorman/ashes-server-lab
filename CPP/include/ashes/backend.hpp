#pragma once
#include <winsock2.h>
#include "protocol.hpp"
#include "contracts.hpp"
#include "movement.hpp"
#include "inspection.hpp"
#include "client.hpp"
#include <atomic>
#include <thread>
#include <mutex>
#include <sqlite3.h>
namespace ashes {
struct Backend;
struct Service {std::string name,error;int port;std::atomic<bool> running=false;SOCKET listener=INVALID_SOCKET;std::thread thread;std::mutex sockets_mutex;std::vector<SOCKET> clients;std::vector<std::thread> workers;Service(std::string,int);~Service();void start_tcp(const std::function<void(SOCKET)>&);void start_udp(const std::function<Bytes(const Bytes&,const sockaddr_in&,SOCKET)>&);void stop();Json state()const;};
struct Store {sqlite3* db=nullptr;std::recursive_mutex mutex;explicit Store(const fs::path&);~Store();void execute(const std::string&);Json query(const std::string&);void packet(const std::string&,const std::string&,const Bytes&,const Json&);void event(const std::string&,const Json&);};
struct Lobby {Backend& owner;Contracts& c;Json characters=Json::array();std::map<std::string,std::pair<std::string,double>> tokens;Lobby(Backend&,Contracts&);std::vector<Json> process(const Json&,Json&);void serve(SOCKET);void save();};
struct Backend {fs::path root;Json config;Contracts contracts;Store store;std::recursive_mutex mutex;WorldProtocol protocol;MovementSettings movement_settings;std::shared_ptr<CollisionWorld> geometry;Lobby lobby;Service world,lobby_service,tether,http;ClientProcess client_process;std::map<std::string,std::shared_ptr<Movement>> players;std::map<std::string,std::vector<Vec>> trails;std::map<std::string,CorrectionPolicy> corrections;Json service_logs=Json::object(),attached=Json::object();std::string geometry_error;std::atomic<bool> stopping=false;std::thread initialization_thread;Backend(fs::path,Json);~Backend();void event(const std::string&,const Json&);void record(const std::string&,const std::string&,const Bytes&,const Json&);void start_service(const std::string&);void stop_service(const std::string&);void serve_http(SOCKET);void world_packet(const Bytes&,const sockaddr_in&,SOCKET);void tether_packet(const Bytes&,const sockaddr_in&,SOCKET);Json state();Json world_view();Json control(const Json&);void stage(const Json&);void inspect(uint32_t);void send_world(Connection&,const Json&);void initialize_clients();void synchronize_movement_speed();};
void send_all(SOCKET,const uint8_t*,size_t);inline void send_all(SOCKET s,const Bytes& b){send_all(s,b.data(),b.size());}
}
