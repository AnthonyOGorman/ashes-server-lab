#pragma once
#include "collision.hpp"
namespace ashes {
struct MovementSettings {
 double speed=600;bool collision_enabled=true,gravity_enabled=true;
 Json json()const;static MovementSettings from(const Json&);
};
struct CorrectionPolicy {
 double last_sent=-1;bool allow(double now,double error,bool mode_changed,bool discarded)const{return last_sent<0||mode_changed||discarded||error>=100||now-last_sent>=.1;}
};
struct Movement {
 bool native_locomotion=false;double ground_friction=10,braking_walk=8192,braking_fly=3000,braking_factor=1,braking_substep=.0166,flight_friction=.15,max_interval=.25;
 std::shared_ptr<const CollisionWorld> world;Vec position,velocity{};double speed=220,acceleration=8192,gravity=-2450,half_height=95.98999786376953,radius=21.989999771118164,step_height=45,floor_z=.6156615018844604,jump_velocity=900,floor_clearance=.02,max_step=.05,budget=.125,wall_observed=0;std::optional<double> timestamp;int mode=3;bool jump_pressed=false;
 bool collision_enabled=true,gravity_enabled=true;
 Movement(std::shared_ptr<const CollisionWorld>,Vec);void configure(const MovementSettings&);void change_altitude(double);std::optional<double> floor(double,double,double=0)const;std::optional<Json> advance(const Json&,double);std::pair<std::vector<Contact>,bool> simulate(const Json&,double);
 Vec integrate_velocity(Vec,Vec,double,double,double,bool)const;
};
}
