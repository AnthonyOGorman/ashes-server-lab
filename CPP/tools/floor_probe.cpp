#include "ashes/movement.hpp"
#include <iostream>
using namespace ashes;
int main(int argc,char** argv){try{
 require(argc==3||argc==4,"CPP root, movement trace and optional isolated candidate manifest required");fs::path root=argv[1];auto config=read_json(root/"config/backend.json");
 auto world=std::make_shared<CollisionWorld>();world->load(root/config.at("terrain_manifest").get<std::string>(),root/config.at("collision_cache").get<std::string>(),root/config.at("terrain_mesh_manifest").get<std::string>());
 if(argc==4){fs::path candidate_path=argv[3];auto candidate=read_json(candidate_path);require(candidate.at("schema")=="ashes-offline-landscape-v1"&&candidate.at("status")=="decoded"&&candidate.at("failures").empty()&&candidate.at("collision_admission").at("status")=="verified","Complete admitted isolated candidate required");for(auto& tile:candidate.at("tiles")){require(tile.at("collision_query_enabled")==true&&tile.at("collision_profile")=="BlockAll","Verified candidate query collision required");world->tiles.emplace_back(tile,candidate_path.parent_path());}}
 auto trace=read_json(argv[2]);Movement movement(world,config.at("spawn").get<Vec>());movement.floor_clearance=2.15;Json rows=Json::array();
 for(auto& row:trace.at("moves")){
  movement.position=row.at("position_before").get<Vec>();Json result={{"event_id",row.at("id")},{"position",movement.position}};
  auto floor=movement.floor(movement.position[0],movement.position[1]);result["floor"]=floor?Json(*floor):Json();
  movement.native_locomotion=true;auto native_floor=movement.floor(movement.position[0],movement.position[1]);auto native_step_floor=movement.floor(movement.position[0],movement.position[1],movement.step_height);result["native_floor"]=native_floor?Json(*native_floor):Json();result["native_step_floor"]=native_step_floor?Json(*native_step_floor):Json();movement.native_locomotion=false;
  double maximum=movement.position[2]-movement.half_height+2.5;Json samples=Json::array();
  for(auto offset:{Vec{},Vec{movement.radius,0,0},Vec{-movement.radius,0,0},Vec{0,movement.radius,0},Vec{0,-movement.radius,0}}){
   double x=movement.position[0]+offset[0],y=movement.position[1]+offset[1];auto bounded=world->ground(x,y,maximum,movement.floor_z),unbounded=world->ground(x,y,1e10,movement.floor_z);
   samples.push_back({{"offset",offset},{"maximum",maximum},{"bounded",bounded?Json{{"height",bounded->height},{"normal",bounded->normal},{"mesh",bounded->mesh}}:Json()},{"unbounded",unbounded?Json{{"height",unbounded->height},{"normal",unbounded->normal},{"mesh",unbounded->mesh}}:Json()}});
  }result["samples"]=samples;rows.push_back(result);
 }std::cout<<Json{{"rows",rows},{"read_only",true}}.dump(2)<<'\n';return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
