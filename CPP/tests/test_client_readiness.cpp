#include "ashes/client.hpp"
#include <iostream>
#include <fstream>
using namespace ashes;
int main(int argc,char** argv){int checks=0;fs::path path;try{
 require(argc==2,"Workspace root required");path=fs::path(argv[1])/"runs/loading-readiness-20261008"/("client-log-test-"+random_id(8)+".log");
 ClientProcess client;client.pid=GetCurrentProcessId();client.process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,client.pid);require(client.process,"Fixture process handle required");client.log_path=path;
 auto check=[&](bool value,const char* message){checks++;require(value,message);};auto append=[&](const std::string& value){std::ofstream out(path,std::ios::app|std::ios::binary);out<<value;out.close();return client.state();};
 auto line=[](const char* timestamp,const char* category,const char* message){return std::string("{\"timestamp\":\"")+timestamp+"\",\"category\":\""+category+"\",\"message\":"+Json(message).dump()+"}\n";};
 auto state=append(line("2026-10-08T01:00:00.000Z","LogLoadingScreen","Visible for 24 seconds"));check(!state.at("gameplay_visible").get<bool>(),"Initial title loading-screen dismissal cannot unlock gameplay");
 state=append(line("2026-10-08T01:10:00.000Z","LogNet","Welcomed by server"));check(state.at("welcomed")==true&&state.at("world_loaded")==false,"Welcome starts a new loading epoch");
 state=append(line("2026-10-08T01:10:01.000Z","LogLoad","Load map complete Verra_World_Master"));check(state.at("world_loaded")==true&&state.at("world_loaded_at").get<double>()>0&&!state.at("gameplay_visible").get<bool>(),"Map completion alone does not dismiss loading");
 state=append(line("2026-10-08T01:10:02.000Z","LogLoadingScreen","Holding loading screen for an additional 22 seconds."));check(!state.at("gameplay_visible").get<bool>(),"Additional native hold keeps gameplay locked");
 state=append(line("2026-10-08T01:10:03.000Z","LogLoadingScreen","HideLoadingScreen while IsShowingInitialLoadingScreen is false."));check(!state.at("gameplay_visible").get<bool>(),"Hide request does not precede final visibility acknowledgement");
 state=append(line("2026-10-08T01:00:01.000Z","LogLoadingScreen","Visible for 24 seconds"));check(!state.at("gameplay_visible").get<bool>(),"Old-epoch visibility logs are rejected");
 state=append(line("2026-10-08T01:10:04.000Z","LogOther","Visible for 24 seconds"));check(!state.at("gameplay_visible").get<bool>(),"Unrelated visibility text cannot unlock gameplay");
 auto final=line("2026-10-08T01:10:23.000Z","LogLoadingScreen","Visible for 28 seconds");state=append(final.substr(0,final.size()-1));check(!state.at("gameplay_visible").get<bool>(),"Partial log record cannot unlock gameplay");
 state=append("\n");check(state.at("gameplay_visible")==true&&state.at("gameplay_visible_at").get<double>()>state.at("world_loaded_at").get<double>(),"Complete final visibility log releases the current world");
 state=append(line("2026-10-08T01:20:00.000Z","LogNet","Welcomed by server"));check(state.at("gameplay_visible")==false&&state.at("gameplay_visible_at")==0&&state.at("world_loaded")==false,"New travel clears both readiness gates and timestamps");
 state=append(line("2026-10-08T01:20:01.000Z","LogLoadingScreen","Visible for 24 seconds"));check(state.at("gameplay_visible")==false,"New travel cannot reuse a prior map completion");
 fs::remove(path);std::cout<<checks<<" client loading readiness checks passed\n";return 0;
 }catch(const std::exception& e){if(!path.empty())fs::remove(path);std::cerr<<"FAILED after "<<checks<<" checks: "<<e.what()<<'\n';return 1;}}
