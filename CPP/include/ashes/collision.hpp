#pragma once
#include "common.hpp"
#include <memory>
#include <functional>
namespace ashes {
using Triangle=std::array<Vec,3>;
struct Bounds {Vec lo,hi;bool overlaps(const Bounds&)const;static Bounds triangle(const Triangle&);};
struct Ground {double height;Vec normal;bool mesh=false;};
struct Heightfield {unsigned rows,cols;Vec origin,scale;double minimum,quantization,yaw_cos=1,yaw_sin=0;Bounds bounds;Bytes heights,materials;explicit Heightfield(const Json&,const fs::path&);double vertex(int,int)const;Vec point(int,int)const;std::array<double,2> grid(double,double)const;std::array<int,4> grid_range(const Bounds&)const;std::optional<Ground> ground(double,double)const;void triangles(const Bounds&,const std::function<void(const Triangle&)>&)const;};
struct Shape {std::vector<Triangle> faces;std::vector<Bounds> face_bounds;struct Node{Bounds bounds;int left=-1,right=-1;std::vector<size_t> indices;};std::vector<Node> tree;Bounds bounds;bool closed=false;std::string kind;explicit Shape(const Json&);Shape(const Json&,const fs::path&);void index(size_t);int build(std::vector<size_t>);void query(const Bounds&,const std::function<void(const Triangle&)>&)const;};
struct Placement {std::shared_ptr<const Shape> source;std::array<double,16> matrix;std::array<Vec,3> axes;double scale_squared,scale;Bounds bounds;Placement(std::shared_ptr<const Shape>,const Json&);Vec point(Vec)const;Vec inverse(Vec)const;void triangles(const Bounds&,const std::function<void(const Triangle&)>&)const;std::optional<Ground> ground(double,double,double,double)const;};
struct CollisionWorld {std::vector<Heightfield> tiles;std::vector<Placement> meshes;Json unsupported=Json::array();size_t stored_faces=0,instance_faces=0,terrain_meshes=0,terrain_mesh_faces=0;bool offline_terrain=false;void load(const fs::path&,const fs::path&,const fs::path& terrain_mesh_manifest={});std::optional<Ground> ground(double,double,double,double)const;void triangles(const Bounds&,const std::function<void(const Triangle&)>&)const;Json statistics()const;Json geometry(Vec,double,int,const std::string&)const;};
struct Contact {double fraction;Vec normal,point;double separation;bool iteration_limit=false;Json json()const;};
Vec closest_point_triangle(Vec,const Triangle&);std::pair<Vec,Vec> closest_segments(Vec,Vec,Vec,Vec);std::tuple<double,Vec,Vec> segment_triangle_distance(Vec,Vec,const Triangle&);std::optional<Contact> sweep_triangle(Vec,Vec,double,double,const Triangle&);Vec limit_upward_slide(Vec,Vec,Vec);std::pair<Vec,std::vector<Contact>> move_capsule(Vec,Vec,double,double,const CollisionWorld&,bool,double,bool);
}
