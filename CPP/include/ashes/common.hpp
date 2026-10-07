#pragma once
#include <nlohmann/json.hpp>
#include <array>
#include <vector>
#include <string>
#include <filesystem>
#include <stdexcept>
#include <cmath>
#include <optional>
namespace ashes {
using Json=nlohmann::json;using Bytes=std::vector<uint8_t>;using Vec=std::array<double,3>;namespace fs=std::filesystem;
double wall_time();double mono_time();Bytes read_file(const fs::path&);void write_file(const fs::path&,const std::string&);Json read_json(const fs::path&);std::string hex(const Bytes&);Bytes unhex(const std::string&);std::string sha256(const Bytes&);std::string sha256_file(const fs::path&);Bytes random_bytes(size_t);std::string random_id(size_t=16);std::string base64(const Bytes&);
inline void require(bool ok,const std::string& s){if(!ok)throw std::runtime_error(s);}
inline Vec add(Vec a,Vec b){for(int i=0;i<3;i++)a[i]+=b[i];return a;}inline Vec sub(Vec a,Vec b){for(int i=0;i<3;i++)a[i]-=b[i];return a;}inline Vec mul(Vec a,double s){for(auto& v:a)v*=s;return a;}inline double dot(Vec a,Vec b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}inline double length(Vec a){return std::sqrt(dot(a,a));}inline Vec cross(Vec a,Vec b){return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}inline bool finite(Vec a){return std::isfinite(a[0])&&std::isfinite(a[1])&&std::isfinite(a[2]);}
}
