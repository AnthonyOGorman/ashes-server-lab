#include "ashes/movement.hpp"
namespace ashes {
float NativeMoveTiming::delta(float client_delta,float world_time,bool reset){
 float capped=std::min(client_delta,std::max(global_multiplier,1.f)*max_move_delta*effective_dilation);
 if(!detection||processed_world==0||reset)return resolving?resolution_delta:capped;
 float server_delta=(world_time-processed_world)*actor_dilation;
 float error=client_delta-server_delta,candidate=discrepancy+error;
 raw_discrepancy+=error;float adjusted=candidate;
 if(drift>0)adjusted=candidate>0?std::max(candidate-drift*server_delta,0.f):std::min(candidate+drift*server_delta,0.f);
 adjusted=std::max(adjusted,min_margin);
 float effective_error=candidate==0?error:(adjusted/candidate)*error;
 if(!resolving||discrepancy<=0){resolving=false;if(adjusted<=max_margin)discrepancy=adjusted;else{resolving=resolution;discrepancy=resolution?adjusted-effective_error:0;}}
 if(!resolving)return capped;
 float carry;if(server_delta>0){carry=accumulated;accumulated=0;}else{accumulated+=capped;carry=accumulated;}
 float available=std::max(std::min(capped+carry,server_delta),0.f);
 float payback=std::min(std::clamp(rate,0.f,1.f)*available,discrepancy);
 float result=std::max(available-payback,.000001f);
 discrepancy-=available-result;resolution_delta=result;return result;
}
bool exceeding_movement_speed(Vec velocity,double max_speed){
 require(finite(velocity)&&std::isfinite(max_speed),"Finite overspeed inputs required");
 // Native leaf 0x3e4ebe0 multiplies in float before its double comparison.
 float limit=float(std::max(0.,max_speed));float squared=limit*limit;
 float threshold=squared*1.01f;return dot(velocity,velocity)>double(threshold);
}
Vec Movement::integrate_velocity(Vec v,Vec input,double dt,double friction,double braking,bool fluid,double max_speed)const{
 double limit=max_speed>=0?max_speed:speed;
 require(finite(v)&&finite(input)&&std::isfinite(dt)&&dt>0&&dt<=2&&std::isfinite(limit)&&limit>=0&&std::isfinite(friction)&&friction>=0&&std::isfinite(braking)&&braking>=0,"Native velocity integration bounds");
 double initial_speed=length(v);
 bool has_input=dot(input,input)>0,exceeding=exceeding_movement_speed(v,limit);
 if(!has_input||exceeding){
  Vec initial=v,reverse=initial_speed?mul(v,-braking/initial_speed):Vec{};
  double remaining=dt,drag=friction*braking_factor,substep=std::clamp(braking_substep,1./75,1./20);
  while(remaining>1e-6){double step=remaining>substep&&drag>0?std::min(substep,remaining*.5):remaining;remaining-=step;v=add(v,mul(add(mul(v,-drag),reverse),step));if(dot(v,initial)<=0){v={};break;}}
  // Native braking 0x5e95e40 applies the 10 cm/s stop threshold only
  // with nonzero deceleration; pure drag must retain small velocities.
  if(braking>0&&length(v)<=10)v={};
  if(exceeding&&length(v)<limit&&dot(input,initial)>0)v=mul(initial,limit/initial_speed);
 }else{
  Vec direction=mul(input,1/length(input));v=sub(v,mul(sub(v,mul(direction,initial_speed)),std::min(dt*friction,1.)));
 }
 if(fluid)v=mul(v,std::max(0.,1-friction*dt));
 if(has_input){
  // AoC CalcVelocity 0x5e9aa10 (0x5e9b311): braking/drag may leave
  // overspeed. Acceleration must not increase that speed or snap it to the cap.
  double acceleration_cap=double(float(exceeding_movement_speed(v,limit)?length(v):limit));
  v=add(v,mul(input,dt));double final_speed=length(v);
  if(final_speed>acceleration_cap)v=mul(v,acceleration_cap/final_speed);
 }
 return v;
}
Json MovementSettings::json()const{return {{"speed",speed},{"collision_enabled",collision_enabled},{"gravity_enabled",gravity_enabled}};}
MovementSettings MovementSettings::from(const Json& j){
 require(j.is_object()&&j.contains("speed")&&j.at("speed").is_number()&&j.contains("collision_enabled")&&j.at("collision_enabled").is_boolean()&&j.contains("gravity_enabled")&&j.at("gravity_enabled").is_boolean(),"Speed and both movement toggles required");
 MovementSettings s;s.speed=j.at("speed").get<double>();s.collision_enabled=j.at("collision_enabled");s.gravity_enabled=j.at("gravity_enabled");require(std::isfinite(s.speed)&&s.speed>=10&&s.speed<=10000,"Movement speed must be between 10 and 10000 cm/s");return s;
}
void Movement::configure(const MovementSettings& settings){
 speed=settings.speed;effective_speed=speed;collision_enabled=settings.collision_enabled;
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
void Movement::recover_spawn(Vec spawn){
 require(finite(spawn),"Finite recovery spawn required");
 auto probe=*this;probe.position=spawn;auto support=probe.floor(spawn[0],spawn[1]);
 require(support&&std::abs(*support-spawn[2])<=step_height,"Recovery spawn must have nearby admitted capsule support");
 position={spawn[0],spawn[1],*support};velocity={};mode=gravity_enabled?1:5;jump_pressed=false;
}
std::optional<double> Movement::floor(double x,double y,double step)const{double maximum=position[2]-half_height+2.5+step;auto hit=world->ground(x,y,maximum,floor_z);if(!hit||hit->normal[2]<floor_z)return {};if(!hit->mesh&&!native_locomotion){for(auto v:{Vec{radius,0,0},Vec{-radius,0,0},Vec{0,radius,0},Vec{0,-radius,0}})if(!world->ground(x+v[0],y+v[1],maximum,floor_z))return {};return hit->height+half_height+radius*(1/hit->normal[2]-1)+floor_clearance;}double estimate=hit->height+half_height+radius*(1/hit->normal[2]-1)+floor_clearance,padding=std::max(2.,radius),travel=padding+radius*(1/floor_z-1)+floor_clearance+2.5;Vec start{x,y,estimate+padding},delta{0,0,-travel};Bounds b{{x-radius,y-radius,start[2]-travel-half_height},{x+radius,y+radius,start[2]+half_height}};std::optional<double> result;auto sweep_floor=[&](const Triangle& t){auto n=cross(sub(t[1],t[0]),sub(t[2],t[0]));double len=length(n);if(len<1e-9||n[2]/len<floor_z)return;auto h=sweep_triangle(start,delta,half_height,radius,t);if(h&&h->normal[2]>=floor_z&&!h->iteration_limit){double value=start[2]-travel*h->fraction+floor_clearance;if(!result||value>*result)result=value;}};if(native_locomotion)world->triangles(b,sweep_floor);else for(auto& mesh:world->meshes)mesh.triangles(b,sweep_floor);return result;}
bool movement_matches(double error,bool mode_matches,bool speed_synced,bool discarded){
 return std::isfinite(error)&&error>=0&&error<=10&&mode_matches&&speed_synced&&!discarded;
}
Json GroundSpeedProfile::json()const{
 return {{"available",available},{"use_forward_stat",use_forward_stat},{"use_backward_stat",use_backward_stat},{"runtime_masks_verified",runtime_masks_verified},
 {"walk",{walk_forward,walk_lateral,walk_backward}},{"run",{run_forward,run_lateral,run_backward}}};
}
double Movement::select_speed(MovementInput input,bool walk)const{
 if(!native_locomotion||!gravity_enabled||!ground_speeds.available)return speed;
 auto& p=ground_speeds;require(p.run_forward>0,"Positive live run-speed base required");
 bool lateral=std::abs(input[0])<=movement_input_epsilon&&std::abs(input[1])>movement_input_epsilon;
 double base;
 if(lateral)base=walk?p.walk_lateral:p.run_lateral;
 else if(input[0]<-movement_input_epsilon){
  // Backward stat identifiers/consumers are unresolved; retain the previous scalar
  // model on that branch and flag the approximation in comparison telemetry.
  if(p.use_backward_stat)return speed;
  base=walk?p.walk_backward:p.run_backward;
 }else{
  if(p.use_forward_stat)return speed; // both walk/run select the same forward stat
  base=walk?p.walk_forward:p.run_forward;
 }
 return speed*base/p.run_forward;
}
Json Movement::comparison()const{
 return {{"current_movement_input",current_input},{"custom_input_restored",input_restored},
 {"walk_requested",wants_walk},{"sprint_requested",wants_sprint},{"sprint_speed_resolved",false},
 {"effective_max_speed",effective_speed},{"speed_selection",speed_selection},{"falling_profile",falling_profile}};
}
std::optional<Json> Movement::advance(const Json& m,double now){
 double t=m.at("timestamp");Vec a=m.at("acceleration").get<Vec>();require(m.at("compressed_flags").is_number_integer(),"Integer compressed movement flags required");int flags=m.at("compressed_flags");
 require(std::isfinite(t)&&t>=0&&finite(a)&&std::isfinite(now),"Finite nonnegative move time and input required");
 require(flags>=0&&flags<=255,"Compressed flags must be a byte");
 require(!(flags&0x40),"Mantle requested: server mantle simulation is unsupported");
 require(!(flags&0x02),"Crouch requested: server crouch capsule simulation is unsupported");
 require(!(flags&~0x31),"Unreviewed reserved/custom compressed movement flags");
 require((gravity_enabled?std::abs(a[2])<=.1:true)&&length(a)<=acceleration+.3,"Locomotion input bounds");
 bool has_input=m.contains("custom_axis_sign_bits");
 MovementInput input=has_input?restore_movement_input(m.at("custom_axis_sign_bits")):MovementInput{};
 auto restore=[&]{
  current_input=input;input_restored=has_input;wants_walk=(flags&0x10)!=0;wants_sprint=(flags&0x20)!=0;
  effective_speed=has_input?select_speed(input,wants_walk):speed;
  speed_selection=!native_locomotion||!gravity_enabled?"scalar_mode":!has_input?"missing_custom_input":!ground_speeds.available?"missing_live_profile":
   input[0]<-movement_input_epsilon&&ground_speeds.use_backward_stat?"unresolved_backward_stat":
   std::abs(input[0])<=movement_input_epsilon&&std::abs(input[1])>movement_input_epsilon?"live_lateral":
   ground_speeds.use_forward_stat?"synchronized_forward_stat":"live_directional_base";
 };
 if(timing.enabled)require(std::isfinite(float(t))&&float(t)>0,"Native finite positive float timestamp required");
 if(!timestamp){restore();timestamp=t;wall_observed=now;if(timing.enabled)timing.processed_world=float(now);return {};}
 double dt=t-*timestamp;bool reset=false;auto kind=m.value("kind","new");
 if(timing.enabled){
  float client_delta=float(t)-float(*timestamp),world_time=float(now);
  if(std::abs(client_delta)>timing.reset_interval*.5f){
   if(client_delta>=0||(timing.last_reset_world!=0&&world_time-timing.last_reset_world<timing.reset_interval*.5f))return {};
   *timestamp=double(float(*timestamp)-timing.reset_interval);timing.last_reset_world=world_time;
   client_delta=float(t)-float(*timestamp);reset=true;
  }
  if(client_delta<.000001f)return {};
  double native_dt=timing.delta(client_delta,world_time,reset);if(native_dt<=0)return {};
  timing.processed_world=world_time;
  Vec old=position,old_velocity=velocity;restore();Json hits=Json::array();bool jumped=false;int steps=0;
  float remaining=float(native_dt);
  while(remaining>=.000001f){++steps;float step=remaining;if(gravity_enabled&&remaining>float(max_step)&&steps<max_simulation_iterations)step=std::min(float(max_step),remaining*.5f);step=std::max(step,.000001f);remaining-=step;
   auto [contacts,jump]=simulate(m,step);jumped|=jump;for(auto h:contacts){auto row=h.json();row["simulation_step"]=steps-1;hits.push_back(row);}
  }
  timestamp=t;wall_observed=now;Json result={{"timestamp",t},{"kind",kind},{"compressed_flags",flags},{"acceleration",a},{"simulation_dt",native_dt},{"client_dt",client_delta},{"timestamp_reset",reset},{"position_before",old},{"velocity_before",old_velocity},{"server_position",position},{"server_velocity",velocity},{"movement_mode",mode},{"delta",sub(position,old)},{"jump_started",jumped},{"collision_hits",hits},{"simulation_steps",steps},{"comparison",comparison()},{"time_discrepancy_s",timing.discrepancy},{"raw_time_discrepancy_s",timing.raw_discrepancy},{"time_resolution_active",timing.resolving},{"force_correction",timing.resolving&&timing.force_corrections},{"server_world_time",world_time}};
  for(auto key:{"custom_axis_sign_bits","client_location","control_rotation","movement_mode"})if(m.contains(key))result[std::string("reported_")+key]=m.at(key);
  return result;
 }
 double wrapped=t+240-*timestamp;
 if(dt<0&&kind!="old"&&*timestamp>=239.5&&*timestamp<=240.25&&t<=120&&wrapped>0&&wrapped<=std::max(.25,now-wall_observed+.125)){dt=wrapped;reset=true;}
 if(dt<=0)return {};
 // Redundant moves from a prior epoch or large gap must not replace the latest
 // clock. A new move remains responsible for gap-discard/correction handling.
 if(kind!="new"&&dt>max_interval)return {};
 budget=std::min(.5,budget+std::max(0.,now-wall_observed));wall_observed=std::max(wall_observed,now);
 Vec old=position,old_velocity=velocity;restore();
 Json result={{"timestamp",t},{"kind",kind},{"compressed_flags",flags},{"acceleration",a},{"simulation_dt",dt},
 {"position_before",old},{"velocity_before",old_velocity},{"timestamp_reset",reset},{"comparison",comparison()}};
 for(auto key:{"custom_axis_sign_bits","client_location","control_rotation","movement_mode"})if(m.contains(key))result[std::string("reported_")+key]=m.at(key);
 if(dt>max_interval||dt>budget){
  timestamp=t;result.update({{"server_position",position},{"server_velocity",velocity},{"movement_mode",mode},{"delta",Vec{}},
  {"discarded_time",dt},{"time_budget",budget},{"simulation_steps",0}});return result;
 }
 budget=std::max(0.,budget-dt);Json hits=Json::array();bool jumped=false;
 int steps=native_locomotion&&!gravity_enabled?1:std::max(1,int(std::ceil(dt/max_step-1e-10)));
 for(int i=0;i<steps;i++){auto [contacts,jump]=simulate(m,dt/steps);jumped|=jump;for(auto h:contacts){auto j=h.json();j["simulation_step"]=i;hits.push_back(j);}}
 timestamp=t;result.update({{"server_position",position},{"server_velocity",velocity},{"movement_mode",mode},{"delta",sub(position,old)},
 {"jump_started",jumped},{"collision_hits",hits},{"simulation_steps",steps},{"time_budget",budget}});return result;
}
std::pair<std::vector<Contact>,bool> Movement::simulate(const Json& m,double dt){Vec a=m.at("acceleration").get<Vec>(),old=position;double vx=velocity[0],vy=velocity[1],vz=velocity[2],max_speed=effective_speed;
if(!gravity_enabled){
 bool pressed=(m.at("compressed_flags").get<int>()&1);jump_pressed=pressed;
 Vec input=a;if(pressed&&!native_locomotion)input[2]=acceleration;
 Vec v=velocity;
 if(native_locomotion)v=integrate_velocity(v,input,dt,flight_friction,braking_fly,true,effective_speed);
 else if(length(input)>.1){v=add(v,mul(input,dt));double s=length(v);if(s>max_speed)v=mul(v,max_speed/s);}
 else{double s=length(v);v=mul(v,s?std::max(0.,1-acceleration*dt/s):0);}
 Vec target=add(old,mul(v,dt));std::vector<Contact> hits;
 if(collision_enabled){auto result=move_capsule(old,sub(target,old),half_height,radius,*world,false,floor_z,false);target=result.first;hits=std::move(result.second);for(auto& h:hits)v=sub(v,mul(h.normal,std::min(0.,dot(v,h.normal))));}
 position=target;velocity=v;mode=5;return {hits,false};
}
auto old_floor=collision_enabled?floor(old[0],old[1]):std::nullopt;bool grounded=old_floor&&std::abs(old[2]-*old_floor)<=2.5&&vz<=0,pressed=(m.at("compressed_flags").get<int>()&1),jumped=pressed&&!jump_pressed&&grounded;jump_pressed=pressed;if(jumped){vz=jump_velocity;grounded=false;}if(native_locomotion&&grounded){auto planar=integrate_velocity(Vec{vx,vy,0},Vec{a[0],a[1],0},dt,ground_friction,braking_walk,false,effective_speed);vx=planar[0];vy=planar[1];}else if(std::hypot(a[0],a[1])>.1){vx+=a[0]*dt;vy+=a[1]*dt;double s=std::hypot(vx,vy);if(s>max_speed){vx*=max_speed/s;vy*=max_speed/s;}}else if(grounded){double s=std::hypot(vx,vy),f=s?std::max(0.,1-acceleration*dt/s):0;vx*=f;vy*=f;}double x=old[0]+vx*dt,y=old[1]+vy*dt,z;auto ground=collision_enabled?floor(x,y,grounded?step_height:0):std::nullopt;if(grounded&&ground&&*ground-*old_floor>step_height){x=old[0];y=old[1];vx=vy=0;ground=old_floor;}if(grounded&&ground&&std::abs(*ground-*old_floor)<=step_height){z=*ground;vz=0;mode=1;}else{double next_vz=vz+gravity*dt;if(native_locomotion&&terminal_velocity>0)next_vz=std::max(next_vz,-terminal_velocity);z=old[2]+.5*(vz+next_vz)*dt;vz=next_vz;mode=3;if(ground&&z<=*ground&&old[2]>=*ground-2.5){z=*ground;vz=0;mode=1;}}Vec target{x,y,z};std::vector<Contact> hits;if(collision_enabled){auto result=move_capsule(old,sub(target,old),half_height,radius,*world,grounded,floor_z,!grounded);target=result.first;hits=std::move(result.second);}Vec v{vx,vy,vz};for(auto h:hits){auto attempted=v;v=sub(v,mul(h.normal,std::min(0.,dot(v,h.normal))));if(!grounded)v=limit_upward_slide(v,attempted,h.normal);if(h.normal[2]>=floor_z&&v[2]<=.1)mode=1;}if(grounded)v[2]=std::min(0.,v[2]);if(mode==1)v[2]=0;auto support=collision_enabled?floor(target[0],target[1]):std::nullopt;if(mode==1&&support&&std::abs(target[2]-*support)<=.01&&std::abs(v[2])<=1e-7){target[2]=*support;v[2]=0;}position=target;velocity=v;return {hits,jumped};}
}
