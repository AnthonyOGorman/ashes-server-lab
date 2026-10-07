#include "ashes/collision.hpp"
#include <algorithm>
#include <numeric>
#include <cstring>
namespace ashes {
static double clamp(double v){return std::clamp(v,0.,1.);}bool Bounds::overlaps(const Bounds& b)const{for(int i=0;i<3;i++)if(hi[i]<b.lo[i]||lo[i]>b.hi[i])return false;return true;}Bounds Bounds::triangle(const Triangle& t){Bounds b{t[0],t[0]};for(auto p:t)for(int i=0;i<3;i++){b.lo[i]=std::min(b.lo[i],p[i]);b.hi[i]=std::max(b.hi[i],p[i]);}return b;}

Heightfield::Heightfield(const Json& j,const fs::path& dir)
 : rows(j.at("rows")),cols(j.at("cols")),origin(j.at("origin").get<Vec>()),scale(j.at("scale").get<Vec>()),
   minimum(j.at("minimum")),quantization(j.at("quantization")),
   heights(read_file(dir/j.at("heights").get<std::string>())),materials(read_file(dir/j.at("materials").get<std::string>())) {
 require(rows>=2&&rows<=4096&&cols>=2&&cols<=4096,"Heightfield dimensions");
 require(heights.size()==size_t(rows)*cols*2&&materials.size()==size_t(rows-1)*(cols-1),"Heightfield buffer size");
 require(finite(origin)&&finite(scale)&&*std::min_element(scale.begin(),scale.end())>0&&std::isfinite(minimum)&&std::isfinite(quantization)&&quantization>=0,"Terrain transform");
 require(sha256(heights)==j.at("heights_sha256").get<std::string>()&&sha256(materials)==j.at("materials_sha256").get<std::string>(),"Terrain buffer hash mismatch");
 if(j.contains("matrix")) {
  // Offline matrices are row-major. Height samples use landscape Z / 128.
  auto m=j.at("matrix").get<std::array<double,16>>();
  for(double v:m)require(std::isfinite(v),"Finite terrain matrix");
  yaw_cos=m[0]/scale[0];yaw_sin=m[4]/scale[0];
  std::array<double,16> expected{yaw_cos*scale[0],-yaw_sin*scale[1],0,origin[0],yaw_sin*scale[0],yaw_cos*scale[1],0,origin[1],0,0,scale[2]*128,origin[2],0,0,0,1};
  require(std::abs(yaw_cos*yaw_cos+yaw_sin*yaw_sin-1)<1e-8,"Terrain yaw axes");
  for(size_t i=0;i<m.size();i++)require(std::abs(m[i]-expected[i])<=1e-7*std::max(1.,std::abs(expected[i])),"Unsupported terrain tilt or shear");
  if(j.contains("cooked_scale"))for(double v:j.at("cooked_scale"))require(std::abs(v-1)<1e-8,"Unsupported cooked heightfield scale");
 }
 bounds={origin,origin};
 for(int y:{0,int(rows)-1})for(int x:{0,int(cols)-1}) {
  auto v=point(x,y);for(int i=0;i<2;i++){bounds.lo[i]=std::min(bounds.lo[i],v[i]);bounds.hi[i]=std::max(bounds.hi[i],v[i]);}
 }
 bounds.lo[2]=origin[2]+minimum*scale[2];bounds.hi[2]=origin[2]+(minimum+65535*quantization)*scale[2];
}
double Heightfield::vertex(int x,int y)const {size_t i=2*(size_t(y)*cols+x);uint16_t n=heights[i]|heights[i+1]<<8;return origin[2]+(minimum+n*quantization)*scale[2];}
Vec Heightfield::point(int x,int y)const {double dx=x*scale[0],dy=y*scale[1];return {origin[0]+yaw_cos*dx-yaw_sin*dy,origin[1]+yaw_sin*dx+yaw_cos*dy,vertex(x,y)};}
std::array<double,2> Heightfield::grid(double x,double y)const {double dx=x-origin[0],dy=y-origin[1];return {(yaw_cos*dx+yaw_sin*dy)/scale[0],(-yaw_sin*dx+yaw_cos*dy)/scale[1]};}
std::array<int,4> Heightfield::grid_range(const Bounds& b)const {
 auto g=grid(b.lo[0],b.lo[1]);double lx=g[0],ly=g[1],hx=g[0],hy=g[1];
 for(double y:{b.lo[1],b.hi[1]})for(double x:{b.lo[0],b.hi[0]}){g=grid(x,y);lx=std::min(lx,g[0]);ly=std::min(ly,g[1]);hx=std::max(hx,g[0]);hy=std::max(hy,g[1]);}
 // Clamp before conversion, including queries far beyond the terrain extent.
 return {int(std::clamp(std::floor(lx),0.,double(cols-1))),int(std::clamp(std::floor(ly),0.,double(rows-1))),int(std::clamp(std::floor(hx),-1.,double(cols-1))),int(std::clamp(std::floor(hy),-1.,double(rows-1)))};
}
std::optional<Ground> Heightfield::ground(double x,double y)const {
 require(std::isfinite(x)&&std::isfinite(y),"Finite terrain query");
 if(x<bounds.lo[0]||x>bounds.hi[0]||y<bounds.lo[1]||y>bounds.hi[1])return {};
 auto g=grid(x,y);double gx=g[0],gy=g[1];if(gx<0||gy<0||gx>=cols-1||gy>=rows-1)return {};
 int ix=int(std::floor(gx)),iy=int(std::floor(gy));if(materials[size_t(iy)*(cols-1)+ix]==255)return {};
 double fx=gx-ix,fy=gy-iy,h00=vertex(ix,iy),h10=vertex(ix+1,iy),h01=vertex(ix,iy+1),h11=vertex(ix+1,iy+1),dx,dy;
 if(fx>=fy){dx=h10-h00;dy=h11-h10;}else{dx=h11-h01;dy=h01-h00;}
 double nx=-dx/scale[0],ny=-dy/scale[1];Vec n{yaw_cos*nx-yaw_sin*ny,yaw_sin*nx+yaw_cos*ny,1};
 return Ground{h00+fx*dx+fy*dy,mul(n,1/length(n)),false};
}
void Heightfield::triangles(const Bounds& b,const std::function<void(const Triangle&)>& f)const {
 if(!bounds.overlaps(b))return;auto r=grid_range(b);int hx=std::min(r[2],int(cols)-2),hy=std::min(r[3],int(rows)-2);
 for(int y=r[1];y<=hy;y++)for(int x=r[0];x<=hx;x++) {
  if(materials[size_t(y)*(cols-1)+x]==255)continue;
  Triangle a{point(x,y),point(x+1,y),point(x+1,y+1)},c{point(x,y),point(x+1,y+1),point(x,y+1)};
  if(Bounds::triangle(a).overlaps(b))f(a);if(Bounds::triangle(c).overlaps(b))f(c);
 }
}
Shape::Shape(const Json& j):faces(j.at("triangles").get<std::vector<Triangle>>()),closed(j.value("closed",false)),kind(j.value("kind","triangle")) {index(500000);}
Shape::Shape(const Json& j,const fs::path& dir):kind("terrain_mesh") {
 size_t vertices=j.at("vertex_count"),triangles=j.at("triangle_count");
 require(vertices>0&&vertices<=1000000&&triangles>0&&triangles<=1000000,"Terrain mesh buffer budget");
 auto buffer=[&](const std::string& key,size_t size){auto& record=j.at("buffers").at(key);auto bytes=read_file(dir/record.at("file").get<std::string>());require(bytes.size()==size&&bytes.size()==record.at("bytes").get<size_t>(),"Terrain mesh buffer size");require(sha256(bytes)==record.at("sha256").get<std::string>(),"Terrain mesh buffer hash mismatch");return bytes;};
 auto vb=buffer("vertices",vertices*12),ib=buffer("triangles",triangles*12);
 auto m=j.at("matrix").get<std::array<double,16>>();for(double v:m)require(std::isfinite(v),"Finite terrain mesh matrix");
 require(std::abs(m[12])+std::abs(m[13])+std::abs(m[14])<1e-10&&std::abs(m[15]-1)<1e-10,"Affine terrain mesh matrix");
 // Bake the row-major transform, including nonuniform scale. Mesh Z is already / 128.
 Vec a{m[0],m[4],m[8]},b{m[1],m[5],m[9]},c{m[2],m[6],m[10]};require(dot(cross(a,b),c)>1e-10,"Terrain mesh orientation");
 std::vector<Vec> points;points.reserve(vertices);
 for(size_t i=0;i<vertices;i++){float raw[3];std::memcpy(raw,vb.data()+12*i,12);Vec p{raw[0],raw[1],raw[2]};require(finite(p),"Finite terrain mesh vertex");points.push_back({m[0]*p[0]+m[1]*p[1]+m[2]*p[2]+m[3],m[4]*p[0]+m[5]*p[1]+m[6]*p[2]+m[7],m[8]*p[0]+m[9]*p[1]+m[10]*p[2]+m[11]});}
 faces.reserve(triangles);
 for(size_t i=0;i<triangles;i++){int32_t ids[3];std::memcpy(ids,ib.data()+12*i,12);Triangle face;for(int k=0;k<3;k++){require(ids[k]>=0&&size_t(ids[k])<vertices,"Terrain mesh face index");face[k]=points[size_t(ids[k])];}faces.push_back(face);}
 index(1000000);
}
void Shape::index(size_t budget) {
 require(!faces.empty()&&faces.size()<=budget,"Shape face budget");bounds=Bounds::triangle(faces.front());face_bounds.reserve(faces.size());
 for(auto& t:faces){for(auto p:t)require(finite(p),"Nonfinite face");require(length(cross(sub(t[1],t[0]),sub(t[2],t[0])))>1e-9,"Degenerate face");auto b=Bounds::triangle(t);face_bounds.push_back(b);for(int i=0;i<3;i++){bounds.lo[i]=std::min(bounds.lo[i],b.lo[i]);bounds.hi[i]=std::max(bounds.hi[i],b.hi[i]);}}
 std::vector<size_t> v(faces.size());std::iota(v.begin(),v.end(),0);build(std::move(v));
}
int Shape::build(std::vector<size_t> ids){Node node;node.bounds=face_bounds[ids.front()];for(auto j:ids)for(int i=0;i<3;i++){node.bounds.lo[i]=std::min(node.bounds.lo[i],face_bounds[j].lo[i]);node.bounds.hi[i]=std::max(node.bounds.hi[i],face_bounds[j].hi[i]);}int index=int(tree.size());tree.push_back(node);if(ids.size()<=8){tree[index].indices=std::move(ids);return index;}int axis=0;for(int i=1;i<3;i++)if(node.bounds.hi[i]-node.bounds.lo[i]>node.bounds.hi[axis]-node.bounds.lo[axis])axis=i;std::sort(ids.begin(),ids.end(),[&](size_t a,size_t b){return face_bounds[a].lo[axis]+face_bounds[a].hi[axis]<face_bounds[b].lo[axis]+face_bounds[b].hi[axis];});auto mid=ids.begin()+ids.size()/2;std::vector<size_t> a(ids.begin(),mid),b(mid,ids.end());int left=build(std::move(a)),right=build(std::move(b));tree[index].left=left;tree[index].right=right;return index;}
void Shape::query(const Bounds& b,const std::function<void(const Triangle&)>& f)const{std::vector<int> stack{0};while(!stack.empty()){auto& n=tree[stack.back()];stack.pop_back();if(!n.bounds.overlaps(b))continue;if(n.left>=0){stack.push_back(n.right);stack.push_back(n.left);}else for(auto i:n.indices)if(face_bounds[i].overlaps(b))f(faces[i]);}}
Placement::Placement(std::shared_ptr<const Shape> s,const Json& j):source(std::move(s)),matrix(j.get<std::array<double,16>>()){for(double v:matrix)require(std::isfinite(v),"Finite instance transform");require(std::abs(matrix[3])+std::abs(matrix[7])+std::abs(matrix[11])<1e-10&&std::abs(matrix[15]-1)<1e-10,"Affine instance transform");for(int i=0;i<3;i++)axes[i]={matrix[i*4],matrix[i*4+1],matrix[i*4+2]};scale_squared=dot(axes[0],axes[0]);scale=std::sqrt(scale_squared);require(scale>1e-8,"Instance scale");for(auto a:axes)require(std::abs(length(a)-scale)<scale*1e-8,"Uniform instance scale");require(std::abs(dot(axes[0],axes[1]))<scale_squared*1e-8&&std::abs(dot(axes[0],axes[2]))<scale_squared*1e-8&&std::abs(dot(axes[1],axes[2]))<scale_squared*1e-8&&dot(cross(axes[0],axes[1]),axes[2])>0,"Right-handed orthogonal instance axes");bounds={point(source->bounds.lo),point(source->bounds.lo)};for(int n=0;n<8;n++){Vec v;for(int i=0;i<3;i++)v[i]=(n&(1<<i))?source->bounds.hi[i]:source->bounds.lo[i];v=point(v);for(int i=0;i<3;i++){bounds.lo[i]=std::min(bounds.lo[i],v[i]);bounds.hi[i]=std::max(bounds.hi[i],v[i]);}}}
Vec Placement::point(Vec p)const{Vec v{matrix[12],matrix[13],matrix[14]};for(int j=0;j<3;j++)v=add(v,mul(axes[j],p[j]));return v;}Vec Placement::inverse(Vec p)const{p=sub(p,{matrix[12],matrix[13],matrix[14]});return {dot(p,axes[0])/scale_squared,dot(p,axes[1])/scale_squared,dot(p,axes[2])/scale_squared};}
void Placement::triangles(const Bounds& b,const std::function<void(const Triangle&)>& f)const{if(!bounds.overlaps(b))return;Bounds local{inverse(b.lo),inverse(b.lo)};for(int n=0;n<8;n++){Vec p;for(int i=0;i<3;i++)p[i]=(n&(1<<i))?b.hi[i]:b.lo[i];p=inverse(p);for(int i=0;i<3;i++){local.lo[i]=std::min(local.lo[i],p[i]);local.hi[i]=std::max(local.hi[i],p[i]);}}source->query(local,[&](const Triangle& t){Triangle world{point(t[0]),point(t[1]),point(t[2])};if(Bounds::triangle(world).overlaps(b))f(world);});}
static std::optional<Ground> ground_face(const Triangle& t,double x,double y,double maximum,double floor_z){auto [a,b,c]=t;Vec n=cross(sub(b,a),sub(c,a));n=mul(n,1/length(n));if(n[2]<floor_z)return {};double d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);if(std::abs(d)<1e-12)return {};double u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/d,v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/d;if(std::min({u,v,1-u-v})< -1e-8)return {};double height=u*a[2]+v*b[2]+(1-u-v)*c[2];if(height>maximum+.001)return {};return Ground{height,n,true};}
std::optional<Ground> Placement::ground(double x,double y,double maximum,double floor_z)const{std::optional<Ground> best;triangles({{x,y,bounds.lo[2]},{x,y,maximum+.001}},[&](auto& t){auto hit=ground_face(t,x,y,maximum,floor_z);if(hit&&(!best||hit->height>best->height))best=hit;});return best;}

void CollisionWorld::load(const fs::path& manifest,const fs::path& cache,const fs::path& terrain_mesh_manifest) {
 auto m=read_json(manifest);bool offline=m.value("schema","")=="ashes-offline-landscape-v1";
 if(offline){require(m.at("status")=="decoded"&&m.at("failures").empty(),"Complete offline terrain manifest required");require(m.at("collision_admission").at("status")=="verified","Verified terrain collision flags required");}
 std::vector<Heightfield> new_tiles;new_tiles.reserve(m.at("tiles").size());
 for(auto& t:m.at("tiles")){if(offline){require(t.at("collision_query_enabled").is_boolean(),"Terrain collision flag required");if(!t.at("collision_query_enabled").get<bool>())continue;}new_tiles.emplace_back(t,manifest.parent_path());}
 auto c=read_json(cache);require(c.at("schema")=="ashes-frozen-collision-v1","Collision schema");
 std::map<std::string,std::shared_ptr<const Shape>> sources;size_t stored=0,instances=0,terrain_count=0,terrain_faces=0;
 for(auto it=c.at("sources").begin();it!=c.at("sources").end();++it){auto s=std::make_shared<Shape>(it.value());stored+=s->faces.size();require(stored<=500000,"Resident static face budget");sources[it.key()]=s;}
 std::vector<Placement> new_meshes;
 for(auto& i:c.at("instances")){auto s=sources.at(i.at("source"));new_meshes.emplace_back(s,i.at("matrix"));instances+=s->faces.size();}
 if(!terrain_mesh_manifest.empty()) {
  auto tm=read_json(terrain_mesh_manifest);require(tm.at("schema")=="ashes-offline-landscape-mesh-v1"&&tm.at("status")=="decoded","Decoded terrain mesh manifest required");require(tm.at("collision_admission").at("status")=="verified","Verified terrain mesh collision flags required");
  for(auto& record:tm.at("meshes")) {
   require(record.at("cls")=="LandscapeMeshCollisionComponent","Landscape collision mesh required");
   require(record.at("collision_query_enabled").is_boolean(),"Terrain mesh collision flag required");if(!record.at("collision_query_enabled").get<bool>())continue;
   auto s=std::make_shared<Shape>(record,terrain_mesh_manifest.parent_path());terrain_count++;terrain_faces+=s->faces.size();stored+=s->faces.size();instances+=s->faces.size();
   require(terrain_faces<=1000000,"Resident terrain face budget");new_meshes.emplace_back(s,Json::array({1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}));
  }
 }
 auto new_unsupported=c.at("unsupported");
 // Publish only after every buffer, transform and BVH has validated.
 tiles=std::move(new_tiles);meshes=std::move(new_meshes);stored_faces=stored;instance_faces=instances;unsupported=std::move(new_unsupported);offline_terrain=offline;terrain_meshes=terrain_count;terrain_mesh_faces=terrain_faces;
}
std::optional<Ground> CollisionWorld::ground(double x,double y,double max,double floor_z)const {std::optional<Ground> hit;for(auto& tile:tiles){if(x<tile.bounds.lo[0]||x>tile.bounds.hi[0]||y<tile.bounds.lo[1]||y>tile.bounds.hi[1])continue;auto g=tile.ground(x,y);if(g&&g->height<=max+.001&&(!hit||g->height>hit->height))hit=g;}for(auto& mesh:meshes){auto g=mesh.ground(x,y,max,floor_z);if(g&&(!hit||g->height>hit->height))hit=g;}return hit;}
void CollisionWorld::triangles(const Bounds& b,const std::function<void(const Triangle&)>& f)const {for(auto& t:tiles)t.triangles(b,f);for(auto& m:meshes)m.triangles(b,f);}
Json CollisionWorld::statistics()const {size_t rotated=0;for(auto& t:tiles)if(std::abs(t.yaw_sin)>1e-8||std::abs(t.yaw_cos-1)>1e-8)rotated++;return {{"tiles",tiles.size()},{"rotated_tiles",rotated},{"terrain_meshes",terrain_meshes},{"terrain_mesh_faces",terrain_mesh_faces},{"offline_terrain",offline_terrain},{"colliders",meshes.size()},{"stored_faces",stored_faces},{"instance_faces",instance_faces},{"unsupported",unsupported.size()},{"coverage",offline_terrain?"archived Verra landscape terrain; static props require a separate local cache":"frozen admitted static geometry; incomplete world collision"}};}
Json CollisionWorld::geometry(Vec origin,double radius,int stride,const std::string& detail)const{require(finite(origin)&&radius>=100&&radius<=100000&&stride>=1&&stride<=64,"Geometry query bounds");std::vector<float> terrain,collision;size_t terrain_segments=0,collision_segments=0,sampled=0;bool tc=false,mc=false;auto line=[&](const Vec& a,const Vec& b,std::vector<float>& out,size_t& count,size_t limit,bool& clipped){if(count>=limit){clipped=true;return;}for(auto p:{a,b})for(int i=0;i<3;i++)out.push_back(float((p[i]-origin[i])/100));count++;};Bounds area{{origin[0]-radius,origin[1]-radius,-1e10},{origin[0]+radius,origin[1]+radius,1e10}};for(auto& t:tiles){if(!t.bounds.overlaps(area))continue;auto r=t.grid_range(area);int lx=r[0],ly=r[1],hx=r[2],hy=r[3];for(int y=ly;y<hy;y+=stride)for(int x=lx;x<hx;x+=stride){int xx=std::min(x+stride,hx),yy=std::min(y+stride,hy);bool solid=true;for(int a=y;a<yy&&solid;a++)for(int b=x;b<xx;b++)if(t.materials[size_t(a)*(t.cols-1)+b]==255){solid=false;break;}if(!solid)continue;line(t.point(x,y),t.point(xx,y),terrain,terrain_segments,150000,tc);line(t.point(x,y),t.point(x,yy),terrain,terrain_segments,150000,tc);}}

Json bounds=Json::array();for(auto& m:meshes)if(m.bounds.overlaps(area)){bounds.push_back({{"minimum",m.bounds.lo},{"maximum",m.bounds.hi}});if(detail=="bounds")continue;size_t every=detail=="full"?1:std::max(size_t(1),m.source->faces.size()/200);sampled++;size_t n=0;m.triangles(area,[&](auto& t){if(n++%every)return;for(int i=0;i<3;i++)line(t[i],t[(i+1)%3],collision,collision_segments,200000,mc);});}auto encode=[](const std::vector<float>& v){Bytes b(v.size()*4);if(!v.empty())std::memcpy(b.data(),v.data(),b.size());return base64(b);};return {{"origin",origin},{"terrain",encode(terrain)},{"collision",encode(collision)},{"bounds",bounds},{"segments",{{"terrain",terrain_segments},{"collision",collision_segments}}},{"collision_detail",detail},{"sampled_meshes",sampled},{"terrain_stride",stride},{"clipped",{{"terrain",tc},{"collision",mc}}}};}
Vec closest_point_triangle(Vec p,const Triangle& t){auto [a,b,c]=t;auto ab=sub(b,a),ac=sub(c,a),ap=sub(p,a);double d1=dot(ab,ap),d2=dot(ac,ap);if(d1<=0&&d2<=0)return a;auto bp=sub(p,b);double d3=dot(ab,bp),d4=dot(ac,bp);if(d3>=0&&d4<=d3)return b;double vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0)return add(a,mul(ab,d1/(d1-d3)));auto cp=sub(p,c);double d5=dot(ab,cp),d6=dot(ac,cp);if(d6>=0&&d5<=d6)return c;double vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0)return add(a,mul(ac,d2/(d2-d6)));double va=d3*d6-d5*d4;if(va<=0&&d4-d3>=0&&d5-d6>=0)return add(b,mul(sub(c,b),(d4-d3)/((d4-d3)+(d5-d6))));double den=va+vb+vc;require(std::abs(den)>=1e-20,"Degenerate triangle");return add(a,add(mul(ab,vb/den),mul(ac,vc/den)));}
std::pair<Vec,Vec> closest_segments(Vec p1,Vec q1,Vec p2,Vec q2){auto d1=sub(q1,p1),d2=sub(q2,p2),r=sub(p1,p2);double a=dot(d1,d1),e=dot(d2,d2),f=dot(d2,r),s,t;if(a<=1e-20&&e<=1e-20)return {p1,p2};if(a<=1e-20){s=0;t=clamp(f/e);}else{double c=dot(d1,r);if(e<=1e-20){s=clamp(-c/a);t=0;}else{double b=dot(d1,d2),den=a*e-b*b;s=den>1e-20?clamp((b*f-c*e)/den):0;t=(b*s+f)/e;if(t<0){t=0;s=clamp(-c/a);}else if(t>1){t=1;s=clamp((b-c)/a);}}}return {add(p1,mul(d1,s)),add(p2,mul(d2,t))};}
std::tuple<double,Vec,Vec> segment_triangle_distance(Vec start,Vec end,const Triangle& t){auto [a,b,c]=t;auto normal=cross(sub(b,a),sub(c,a));require(length(normal)>=1e-10,"Degenerate triangle");auto direction=sub(end,start);double den=dot(normal,direction);if(std::abs(den)>1e-16){double f=dot(normal,sub(a,start))/den;if(f>=0&&f<=1){auto p=add(start,mul(direction,f)),q=closest_point_triangle(p,t);if(length(sub(p,q))<1e-8)return {0,p,q};}}std::vector<std::pair<Vec,Vec>> pairs{{start,closest_point_triangle(start,t)},{end,closest_point_triangle(end,t)}};for(int i=0;i<3;i++)pairs.push_back(closest_segments(start,end,t[i],t[(i+1)%3]));auto best=*std::min_element(pairs.begin(),pairs.end(),[](auto& x,auto& y){return dot(sub(x.first,x.second),sub(x.first,x.second))<dot(sub(y.first,y.second),sub(y.first,y.second));});return {length(sub(best.first,best.second)),best.first,best.second};}
std::optional<Contact> sweep_triangle(Vec p,Vec delta,double hh,double radius,const Triangle& tri){double speed=length(delta);if(speed<1e-12)return {};require(radius>0&&radius<=hh,"Capsule dimensions");double segment=hh-radius,t=0,gap=0;Vec normal{},q{};for(int i=0;i<256;i++){auto centre=add(p,mul(delta,t));auto [distance,a,b]=segment_triangle_distance(add(centre,{0,0,-segment}),add(centre,{0,0,segment}),tri);q=b;gap=distance-radius;if(distance>1e-12)normal=mul(sub(a,b),1/distance);else{normal=cross(sub(tri[1],tri[0]),sub(tri[2],tri[0]));normal=mul(normal,1/length(normal));if(dot(normal,delta)>0)normal=mul(normal,-1);}if(gap<=.001){if(t==0&&dot(delta,normal)>=-1e-9)return {};return Contact{t,normal,q,gap,false};}t+=gap/speed;if(t>1)return {};}return Contact{std::min(t,1.),normal,q,gap,true};}
Json Contact::json()const{Json j={{"fraction",fraction},{"normal",normal},{"point",point},{"separation",separation}};if(iteration_limit)j["iteration_limit"]=true;return j;}Vec limit_upward_slide(Vec slide,Vec attempted,Vec normal){double limit=std::max(0.,attempted[2]);if(slide[2]<=limit+1e-9)return slide;auto retained=mul(slide,limit/slide[2]);Vec remainder{slide[0]-retained[0],slide[1]-retained[1],0};double n=std::hypot(normal[0],normal[1]);if(n>1e-10){Vec h{normal[0]/n,normal[1]/n,0};remainder=sub(remainder,mul(h,std::min(0.,dot(remainder,h))));}return add(retained,remainder);}
std::pair<Vec,std::vector<Contact>> move_capsule(Vec p,Vec delta,double hh,double radius,const CollisionWorld& world,bool grounded,double floor_z,bool limit){Vec remaining=delta;std::vector<Contact> hits;for(int iteration=0;iteration<4;iteration++){if(dot(remaining,remaining)<1e-12)break;Vec end=add(p,remaining);Bounds bounds;for(int i=0;i<3;i++){double r=i<2?radius:hh;bounds.lo[i]=std::min(p[i],end[i])-r;bounds.hi[i]=std::max(p[i],end[i])+r;}std::optional<Contact> hit;world.triangles(bounds,[&](auto& t){auto h=sweep_triangle(p,remaining,hh,radius,t);if(h&&(!hit||h->fraction<hit->fraction))hit=h;});if(!hit)return {add(p,remaining),hits};if(grounded&&hit->normal[2]>=0&&hit->normal[2]<floor_z){double n=std::hypot(hit->normal[0],hit->normal[1]);if(n>1e-10)hit->normal={hit->normal[0]/n,hit->normal[1]/n,0};}p=add(p,mul(remaining,hit->fraction));hits.push_back(*hit);remaining=mul(remaining,1-hit->fraction);auto attempted=remaining;remaining=sub(remaining,mul(hit->normal,std::min(0.,dot(remaining,hit->normal))));if(limit)remaining=limit_upward_slide(remaining,attempted,hit->normal);}return {p,hits};}
}
