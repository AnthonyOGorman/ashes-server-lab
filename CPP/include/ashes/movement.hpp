#pragma once
#include "collision.hpp"
#include "protocol.hpp"
namespace ashes {
struct GroundSpeedProfile {
 bool available=false,use_forward_stat=false,use_backward_stat=false;
 double walk_forward=0,walk_lateral=0,walk_backward=0,run_forward=0,run_lateral=0,run_backward=0;
 bool runtime_masks_verified=false;
 Json json()const;
};
struct MovementSettings {
 double speed=600;bool collision_enabled=true,gravity_enabled=true;
 Json json()const;static MovementSettings from(const Json&);
};
struct CorrectionPolicy {
 double last_sent=-1;bool allow(double now,double error,bool mode_changed,bool discarded)const{return last_sent<0||mode_changed||discarded||error>=100||now-last_sent>=.1;}
};
bool movement_matches(double error,bool mode_matches,bool speed_synced,bool discarded);
bool exceeding_movement_speed(Vec,double);
struct NativeMoveTiming {
 bool enabled=false,detection=true,resolution=true,resolving=false,force_corrections=false;
 float max_move_delta=.75f,global_multiplier=1.75f,actor_dilation=1,effective_dilation=1;
 float max_margin=.25f,min_margin=-.25f,rate=1,drift=0,reset_interval=240,last_reset_world=0;
 float processed_world=0,raw_discrepancy=0,discrepancy=0,accumulated=0,resolution_delta=0;
 float delta(float client_delta,float world_time,bool reset);
};
struct Movement {
 NativeMoveTiming timing;int max_simulation_iterations=8;double terminal_velocity=0;
 double air_control=.2,air_control_boost=2,air_control_boost_threshold=25,falling_friction=0,braking_fall=3000;
 Json falling_profile=Json::object();
 GroundSpeedProfile ground_speeds;
 MovementInput current_input{};bool input_restored=false,wants_walk=false,wants_sprint=false;
 double effective_speed=220;std::string speed_selection="scalar";
 bool native_locomotion=false;double ground_friction=10,braking_walk=8192,braking_fly=3000,braking_factor=1,braking_substep=.0166,flight_friction=.15,max_interval=.25;
 std::shared_ptr<const CollisionWorld> world;Vec position,velocity{};double speed=220,acceleration=8192,gravity=-2450,half_height=95.98999786376953,radius=21.989999771118164,step_height=45,floor_z=.6156615018844604,jump_velocity=900,floor_clearance=.02,max_step=.05,budget=.125,wall_observed=0;std::optional<double> timestamp;int mode=3;bool jump_pressed=false;
 bool collision_enabled=true,gravity_enabled=true;
 Movement(std::shared_ptr<const CollisionWorld>,Vec);void configure(const MovementSettings&);void change_altitude(double);void recover_spawn(Vec);std::optional<double> floor(double,double,double=0)const;std::optional<Json> advance(const Json&,double);std::pair<std::vector<Contact>,bool> simulate(const Json&,double);
 Vec integrate_velocity(Vec,Vec,double,double,double,bool,double=-1)const;
 double select_speed(MovementInput,bool walk)const;
 Json comparison()const;
};
}
