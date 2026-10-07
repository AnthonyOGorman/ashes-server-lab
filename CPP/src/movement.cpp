#include "ashes/movement.hpp"
namespace ashes {
Vec Movement::integrate_velocity(Vec v,Vec input,double dt,double friction,double braking,bool fluid)const{
 require(finite(v)&&finite(input)&&dt>0&&dt<=.5&&friction>=0&&braking>=0,"Native velocity integration bounds");
 double initial_speed=length(v);
 if(length(input)<=.1||initial_speed>speed+1e-6){
  Vec initial=v,reverse=initial_speed?mul(v,-braking/initial_speed):Vec{};
  double remaining=dt,drag=friction*braking_factor,substep=std::clamp(braking_substep,1./75,1./20);
  while(remaining>1e-6){double step=remaining>substep&&drag>0?std::min(substep,remaining*.5):remaining;remaining-=step;v=add(v,mul(add(mul(v,-drag),reverse),step));if(dot(v,initial)<=0){v={};break;}}
  if(length(v)<=10)v={};
  if(initial_speed>speed&&length(v)<speed&&dot(input,initial)>0)v=mul(initial,speed/initial_speed);
 }else{
  Vec direction=mul(input,1/length(input));v=sub(v,mul(sub(v,mul(direction,initial_speed)),std::min(dt*friction,1.)));
 }
 if(fluid)v=mul(v,std::max(0.,1-friction*dt));
 v=add(v,mul(input,dt));double final_speed=length(v);if(final_speed>speed)v=mul(v,speed/final_speed);
 return v;
}
Json MovementSettings::json()const{return {{"speed",speed},{"collision_enabled",collision_enabled},{"gravity_enabled",gravity_enabled}};}
MovementSettings MovementSettings::from(const Json& j){
 require(j.is_object()&&j.contains("speed")&&j.at("speed").is_number()&&j.contains("collision_enabled")&&j.at("collision_enabled").is_boolean()&&j.contains("gravity_enabled")&&j.at("gravity_enabled").is_boolean(),"Speed and both movement toggles required");
 MovementSettings s;s.speed=j.at("speed").get<double>();s.collision_enabled=j.at("collision_enabled");s.gravity_enabled=j.at("gravity_enabled");require(std::isfinite(s.speed)&&s.speed>=10&&s.speed<=10000,"Movement speed must be between 10 and 10000 cm/s");return s;
}
void Movement::configure(const MovementSettings& settings){
 speed=settings.speed;collision_enabled=settings.collision_enabled;
 if(gravity_enabled!=settings.gravity_enabled)velocity[2]=0;
 gravity_enabled=settings.gravity_enabled;velocity=mul(velocity,std::min(1.,speed/std::max(length(velocity),1e-9)));
 mode=gravity_enabled?3:5;jump_pressed=false;
}
void Movement::change_altitude(double delta){
 require(!gravity_enabled&&std::isfinite(delta)&&std::abs(delta)<=10000,"Altitude controls require flight; maximum step is 100 metres");
 Vec target=add(position,Vec{0,0,delta});
 if(collision_enabled)target=move_capsule(position,Vec{0,0,delta},half_height,radius,*world,false,floor_z,false).first;
 position=target;velocity[2]=0;mode=5;
}

Movement::Movement(std::shared_ptr<const CollisionWorld> w,Vec p):world(std::move(w)),position(p){require(finite(p)&&floor(p[0],p[1]).has_value(),"Terrain-supported spawn required");}
std::optional<double> Movement::floor(double x,double y,double step)const{double maximum=position[2]-half_height+2.5+step;auto hit=world->ground(x,y,maximum,floor_z);if(!hit||hit->normal[2]<floor_z)return {};if(!hit->mesh){for(auto v:{Vec{radius,0,0},Vec{-radius,0,0},Vec{0,radius,0},Vec{0,-radius,0}})if(!world->ground(x+v[0],y+v[1],maximum,floor_z))return {};return hit->height+half_height+radius*(1/hit->normal[2]-1)+floor_clearance;}double estimate=hit->height+half_height+radius*(1/hit->normal[2]-1)+floor_clearance,padding=std::max(2.,radius),travel=padding+radius*(1/floor_z-1)+floor_clearance+2.5;Vec start{x,y,estimate+padding},delta{0,0,-travel};Bounds b{{x-radius,y-radius,start[2]-travel-half_height},{x+radius,y+radius,start[2]+half_height}};std::optional<double> result;for(auto& mesh:world->meshes)mesh.triangles(b,[&](const Triangle& t){auto n=cross(sub(t[1],t[0]),sub(t[2],t[0]));double len=length(n);if(len<1e-9||n[2]/len<floor_z)return;auto h=sweep_triangle(start,delta,half_height,radius,t);if(h&&h->normal[2]>=floor_z&&!h->iteration_limit){double value=start[2]-travel*h->fraction+floor_clearance;if(!result||value>*result)result=value;}});return result;}
std::optional<Json> Movement::advance(const Json& m,double now){double t=m.at("timestamp");Vec a=m.at("acceleration").get<Vec>();int flags=m.at("compressed_flags");require(std::isfinite(t)&&t>=0&&finite(a)&&std::isfinite(now),"Finite nonnegative move time and input required");require((flags==0||flags==1)&&(gravity_enabled?std::abs(a[2])<=.1:true)&&length(a)<=acceleration+.3,"Locomotion input bounds");if(!timestamp){timestamp=t;wall_observed=now;return {};}double dt=t-*timestamp;bool reset=false;double wrapped=t+240-*timestamp;if(dt<0&&m.value("kind","new")=="new"&&*timestamp>=239.5&&*timestamp<=240.25&&t<=120&&wrapped>0&&wrapped<=std::max(.25,now-wall_observed+.125)){dt=wrapped;reset=true;}if(dt<=0)return {};budget=std::min(.5,budget+std::max(0.,now-wall_observed));wall_observed=std::max(wall_observed,now);if(dt>max_interval||dt>budget){timestamp=t;return Json{{"timestamp",t},{"server_position",position},{"server_velocity",velocity},{"movement_mode",mode},{"delta",Vec{}},{"discarded_time",dt},{"time_budget",budget},{"timestamp_reset",reset}};}budget=std::max(0.,budget-dt);Vec old=position;Json hits=Json::array();bool jumped=false;int steps=native_locomotion&&!gravity_enabled?1:std::max(1,int(std::ceil(dt/max_step-1e-10)));for(int i=0;i<steps;i++){auto [contacts,jump]=simulate(m,dt/steps);jumped|=jump;for(auto h:contacts){auto j=h.json();j["simulation_step"]=i;hits.push_back(j);}}timestamp=t;return Json{{"timestamp",t},{"server_position",position},{"server_velocity",velocity},{"movement_mode",mode},{"delta",sub(position,old)},{"jump_started",jumped},{"timestamp_reset",reset},{"collision_hits",hits}};}
std::pair<std::vector<Contact>,bool> Movement::simulate(const Json& m,double dt){Vec a=m.at("acceleration").get<Vec>(),old=position;double vx=velocity[0],vy=velocity[1],vz=velocity[2];
if(!gravity_enabled){
 bool pressed=(m.at("compressed_flags").get<int>()&1);jump_pressed=pressed;
 Vec input=a;if(pressed&&!native_locomotion)input[2]=acceleration;
 Vec v=velocity;
 if(native_locomotion)v=integrate_velocity(v,input,dt,flight_friction,braking_fly,true);
 else if(length(input)>.1){v=add(v,mul(input,dt));double s=length(v);if(s>speed)v=mul(v,speed/s);}
 else{double s=length(v);v=mul(v,s?std::max(0.,1-acceleration*dt/s):0);}
 Vec target=add(old,mul(v,dt));std::vector<Contact> hits;
 if(collision_enabled){auto result=move_capsule(old,sub(target,old),half_height,radius,*world,false,floor_z,false);target=result.first;hits=std::move(result.second);for(auto& h:hits)v=sub(v,mul(h.normal,std::min(0.,dot(v,h.normal))));}
 position=target;velocity=v;mode=5;return {hits,false};
}
auto old_floor=collision_enabled?floor(old[0],old[1]):std::nullopt;bool grounded=old_floor&&std::abs(old[2]-*old_floor)<=2.5&&vz<=0,pressed=(m.at("compressed_flags").get<int>()&1),jumped=pressed&&!jump_pressed&&grounded;jump_pressed=pressed;if(jumped){vz=jump_velocity;grounded=false;}if(native_locomotion&&grounded){auto planar=integrate_velocity(Vec{vx,vy,0},Vec{a[0],a[1],0},dt,ground_friction,braking_walk,false);vx=planar[0];vy=planar[1];}else if(std::hypot(a[0],a[1])>.1){vx+=a[0]*dt;vy+=a[1]*dt;double s=std::hypot(vx,vy);if(s>speed){vx*=speed/s;vy*=speed/s;}}else if(grounded){double s=std::hypot(vx,vy),f=s?std::max(0.,1-acceleration*dt/s):0;vx*=f;vy*=f;}double x=old[0]+vx*dt,y=old[1]+vy*dt,z;auto ground=collision_enabled?floor(x,y,grounded?step_height:0):std::nullopt;if(grounded&&ground&&*ground-*old_floor>step_height){x=old[0];y=old[1];vx=vy=0;ground=old_floor;}if(grounded&&ground&&std::abs(*ground-*old_floor)<=step_height){z=*ground;vz=0;mode=1;}else{z=old[2]+vz*dt+.5*gravity*dt*dt;vz+=gravity*dt;mode=3;if(ground&&z<=*ground&&old[2]>=*ground-2.5){z=*ground;vz=0;mode=1;}}Vec target{x,y,z};std::vector<Contact> hits;if(collision_enabled){auto result=move_capsule(old,sub(target,old),half_height,radius,*world,grounded,floor_z,!grounded);target=result.first;hits=std::move(result.second);}Vec v{vx,vy,vz};for(auto h:hits){auto attempted=v;v=sub(v,mul(h.normal,std::min(0.,dot(v,h.normal))));if(!grounded)v=limit_upward_slide(v,attempted,h.normal);if(h.normal[2]>=floor_z&&v[2]<=.1)mode=1;}if(grounded)v[2]=std::min(0.,v[2]);if(mode==1)v[2]=0;auto support=collision_enabled?floor(target[0],target[1]):std::nullopt;if(mode==1&&support&&std::abs(target[2]-*support)<=.01&&std::abs(v[2])<=1e-7){target[2]=*support;v[2]=0;}position=target;velocity=v;return {hits,jumped};}
}
