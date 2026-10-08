#include "ashes/movement.hpp"
#include <iostream>
#include <chrono>
#include <algorithm>
using namespace ashes;
static size_t checks=0;
static void check(bool ok,const std::string& name){checks++;require(ok,name);}
static Vec transform(const std::array<double,16>& m,Vec p){return {m[0]*p[0]+m[1]*p[1]+m[2]*p[2]+m[3],m[4]*p[0]+m[5]*p[1]+m[6]*p[2]+m[7],m[8]*p[0]+m[9]*p[1]+m[10]*p[2]+m[11]};}
int main(int argc,char** argv){try{
 require(argc==2,"CPP root required");fs::path root=argv[1];auto began=std::chrono::steady_clock::now();
 auto dir=root/"data/terrain-offline/decoded",manifest=dir/"manifest.json";
 auto records=read_json(manifest);CollisionWorld world;
 world.load(manifest,root/"config/empty-collision.json",root/"data/terrain-offline/decoded-mesh/manifest.json");
 check(world.tiles.size()==2669,"All archived Verra heightfields loaded");
 check(world.terrain_meshes==1&&world.terrain_mesh_faces==518866,"Warped landscape mesh loaded");
 check(world.statistics().at("rotated_tiles")==82,"All rotated Verra heightfields loaded");
 size_t solid_samples=0,hole_samples=0;
 for(size_t i=0;i<world.tiles.size();i++) {
  auto& tile=world.tiles[i];auto& record=records.at("tiles").at(i);auto matrix=record.at("matrix").get<std::array<double,16>>();
  // Compare world placements against the export's independent full affine matrix.
  for(auto xy:{std::array<int,2>{0,0},std::array<int,2>{int(tile.cols)-1,int(tile.rows)-1}}) {
   double local_z=(tile.vertex(xy[0],xy[1])-tile.origin[2])/tile.scale[2]/128;
   check(length(sub(tile.point(xy[0],xy[1]),transform(matrix,{double(xy[0]),double(xy[1]),local_z})))<1e-6,"Heightfield affine placement");
  }
  auto solid=std::find_if(tile.materials.begin(),tile.materials.end(),[](uint8_t v){return v!=255;});
  if(solid!=tile.materials.end()) {
   size_t cell=size_t(solid-tile.materials.begin());int x=int(cell%(tile.cols-1)),y=int(cell/(tile.cols-1));
   auto a=tile.point(x,y),b=tile.point(x+1,y),c=tile.point(x+1,y+1);auto p=mul(add(add(a,b),c),1./3);
   auto ground=tile.ground(p[0],p[1]);auto normal=cross(sub(b,a),sub(c,a));normal=mul(normal,1/length(normal));
   check(ground&&std::abs(ground->height-p[2])<1e-6&&length(sub(ground->normal,normal))<1e-6,"Rotated terrain triangle interpolation and normal");
   size_t triangles=0;tile.triangles({{p[0]-.001,p[1]-.001,p[2]-.001},{p[0]+.001,p[1]+.001,p[2]+.001}},[&](const Triangle&){triangles++;});
   check(triangles>=1,"Terrain bounds query finds the sampled surface");solid_samples++;
  }
  auto hole=std::find(tile.materials.begin(),tile.materials.end(),uint8_t(255));
  if(hole!=tile.materials.end()) {
   size_t cell=size_t(hole-tile.materials.begin());int x=int(cell%(tile.cols-1)),y=int(cell/(tile.cols-1));
   auto p=mul(add(add(tile.point(x,y),tile.point(x+1,y)),tile.point(x+1,y+1)),1./3);
   check(!tile.ground(p[0],p[1]),"Terrain hole has no floor");size_t triangles=0;
   tile.triangles({{p[0]-.001,p[1]-.001,-1e10},{p[0]+.001,p[1]+.001,1e10}},[&](const Triangle&){triangles++;});
   check(triangles==0,"Terrain hole has no sweep geometry");hole_samples++;
  }
 }
 // Native references are compared at interior cells, including ground normals.
 auto native=root/"baseline/evidence/terrain_epoch18_49892/manifest.json";auto references=fs::exists(native)?read_json(native):Json{{"tiles",Json::array()}};size_t native_matches=0;
 for(auto& record:references.at("tiles")) {
  Heightfield previous(record,native.parent_path());const Heightfield* match=nullptr;
  for(size_t i=0;i<world.tiles.size();i++)if(records["tiles"][i]["heights_sha256"]==record["heights_sha256"]&&world.tiles[i].origin==previous.origin)match=&world.tiles[i];
  check(match!=nullptr,"Native reference tile admitted");
  for(int y=1;y<int(previous.rows)-1;y+=37)for(int x=1;x<int(previous.cols)-1;x+=41) {
   auto p=previous.point(x,y);p[0]+=17;p[1]+=29;auto before=previous.ground(p[0],p[1]),after=match->ground(p[0],p[1]);
   check(bool(before)==bool(after),"Native reference hole parity");if(before)check(std::abs(before->height-after->height)<1e-9&&length(sub(before->normal,after->normal))<1e-9,"Native reference surface parity");
  }native_matches++;
 }
 auto& terrain=world.meshes.back();check(terrain.source->kind=="terrain_mesh","Terrain mesh admitted independently of props");
 for(size_t i=0;i<terrain.source->faces.size();i+=5003) {
  auto tri=terrain.source->faces[i];auto p=mul(add(add(tri[0],tri[1]),tri[2]),1./3);auto g=terrain.ground(p[0],p[1],p[2]+1,.001);
  check(g&&std::abs(g->height-p[2])<.001,"Warped terrain mesh floor");
  auto hit=sweep_triangle(add(p,{0,0,100}),{0,0,-200},2,1,tri);
  check(hit&&hit->fraction>0&&hit->fraction<.5&&!hit->iteration_limit,"Warped terrain mesh capsule sweep");
 }
 auto spawn=read_json(root/"config/backend.json").at("spawn").get<Vec>();auto ground=world.ground(spawn[0],spawn[1],spawn[2],.7);check(ground.has_value(),"Full terrain cache supports configured spawn");
 // Reproduce the first floor-loss from the DLL test. A capsule can stand on
 // the solid side of this hole; requiring four side rays invents a fall.
 auto shared_world=std::shared_ptr<const CollisionWorld>(&world,[](const CollisionWorld*){});
 Movement edge(shared_world,spawn);edge.floor_clearance=2.15;edge.position={-677963.7692651711,406500.,12491.03};
 check(!edge.floor(edge.position[0],edge.position[1]),"Historical four-ray fixture rejects the partially supported edge");
 edge.native_locomotion=true;auto edge_floor=edge.floor(edge.position[0],edge.position[1]);
 check(edge_floor&&std::abs(*edge_floor-12491.03)<.05,"Native capsule sweep finds the independently observed supported edge height");
 check(!world.ground(-677963.7692651711,406478.,1e10,edge.floor_z),"Regression edge retains the genuine adjacent terrain hole");
 edge.position={-678008.4286889993,406500.,12495.78222607955};edge.configure({600,true,true});edge.velocity={600,0,0};
 edge.advance({{"timestamp",1.},{"acceleration",Vec{8192,0,0}},{"compressed_flags",0},{"custom_axis_sign_bits",{1,0,0,0}}},1.);
 auto crossed=edge.advance({{"timestamp",1.074432373046875},{"acceleration",Vec{8192,0,0}},{"compressed_flags",0},{"custom_axis_sign_bits",{1,0,0,0}}},1.074432373046875);
 check(crossed&&edge.mode==1&&std::abs(edge.position[1]-406500.)<1e-6&&std::abs(edge.position[2]-12491.03)<.05,"Recorded W interval stays supported without a falling correction or lateral slide");
 edge.position={-580538.,406498.,-32226684.};edge.velocity={600,0,-4000};auto clock=edge.timestamp;edge.recover_spawn(spawn);
 check(edge.mode==1&&edge.velocity==Vec{}&&edge.timestamp==clock&&std::abs(edge.position[0]-spawn[0])<1e-6,"Supported recovery restores position and stops velocity while preserving the move clock");
 auto recovered=edge.position;bool unsafe_recovery=false;try{edge.recover_spawn({1e9,1e9,0});}catch(const std::exception&){unsafe_recovery=true;}
 check(unsafe_recovery&&edge.position==recovered,"Unsupported recovery cannot change authoritative state");
 // An upper overlapping landscape cannot hijack a floor query below its surface.
 auto top=world.tiles.front().point(3,3);check(!world.tiles.front().ground(top[0]+1e9,top[1]),"Far outside terrain query is empty");
 CollisionWorld layered;layered.tiles.push_back(world.tiles.front());check(!layered.ground(top[0],top[1],top[2]-1,.7),"Floor query excludes terrain above the requested ceiling");
 auto drawing=world.geometry(spawn,20000,8,"lightweight");check(drawing.at("segments").at("terrain").get<size_t>()>0,"Full terrain geometry viewer produces lines");
 bool refused=false;auto invalid=records["tiles"][0];invalid["matrix"][2]=10;
 try{Heightfield bad(invalid,dir);}catch(const std::exception&){refused=true;}check(refused,"Unsupported terrain tilt fails closed");
 invalid=records["tiles"][0];invalid["heights_sha256"]=std::string(64,'0');refused=false;
 try{Heightfield bad(invalid,dir);}catch(const std::exception&){refused=true;}check(refused,"Changed terrain buffer fails closed");
 auto bad_manifest=dir/("test-invalid-"+random_id()+".json");
 auto small=Json{{"schema","ashes-offline-landscape-v1"},{"status","decoded"},{"failures",Json::array()},{"collision_admission",records.at("collision_admission")},{"tiles",Json::array({invalid})}};
 write_file(bad_manifest,small.dump());auto before=world.statistics();refused=false;
 try{world.load(bad_manifest,root/"config/empty-collision.json");}catch(const std::exception&){refused=true;}fs::remove(bad_manifest);
 check(refused&&world.statistics()==before,"Failed geometry reload preserves the admitted world");
 auto disabled=records["tiles"][0];disabled["collision_query_enabled"]=false;small["tiles"]=Json::array({disabled});write_file(bad_manifest,small.dump());
 CollisionWorld filtered;filtered.load(bad_manifest,root/"config/empty-collision.json");fs::remove(bad_manifest);check(filtered.tiles.empty(),"Disabled archived terrain is excluded from collision");
 auto query_start=std::chrono::steady_clock::now();
 for(int i=0;i<10000;i++)world.ground(spawn[0]+i%100,spawn[1]+i%50,spawn[2],.7);
 double query_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-query_start).count()/10000;
 auto report=world.statistics();report["checks"]=checks;report["solid_tile_samples"]=solid_samples;report["hole_tile_samples"]=hole_samples;report["native_reference_matches"]=native_matches;report["load_and_test_seconds"]=std::chrono::duration<double>(std::chrono::steady_clock::now()-began).count();report["status"]="passed";
 report["average_ground_query_ms"]=query_ms;write_file(root/"data/terrain-offline/native-loader-verification.json",report.dump(2));std::cout<<report.dump(2)<<'\n';return 0;
 }catch(const std::exception& e){std::cerr<<"Terrain validation failed after "<<checks<<" checks: "<<e.what()<<'\n';return 1;}}
