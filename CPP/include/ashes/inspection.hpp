#pragma once
#include "common.hpp"
#include <windows.h>
#include <map>
#include <cstring>
namespace ashes {
struct Guid;
Json refresh_actor_matches(struct ProcessReader&,const Json&,const std::map<std::string,Guid>&);
struct ProcessReader {HANDLE handle=nullptr;uint32_t pid;uint64_t created=0,base=0;size_t image_size=0,bytes_read=0,read_calls=0,budget=256*1024*1024;fs::path exe;std::string hash;bool hash_from_cache=false;Json hash_file_identity;ProcessReader(uint32_t,const fs::path&,const std::string&);~ProcessReader();Bytes read(uint64_t,size_t);template<class T>T at(uint64_t address){auto b=read(address,sizeof(T));T value;std::memcpy(&value,b.data(),sizeof(T));return value;}Json proof()const;void verify_alive()const;};
struct Reflection {ProcessReader& r;uint64_t name_pool=0,chunks=0;unsigned blocks_offset=0,count=0,num_chunks=0;std::map<uint64_t,Json> objects_cache,ancestry_cache,property_cache;std::map<uint32_t,std::string> names_cache;explicit Reflection(ProcessReader&);std::string name(uint32_t,uint32_t=0);Json object(uint64_t);Json ancestry(uint64_t);Json identity(uint64_t,const std::string& expected="");Json properties(uint64_t);Json property(uint64_t,const std::string&,int,int);Json find_property(uint64_t,const std::string&);Json network_cache(uint64_t,uint64_t);Json scalar_handle(uint64_t,uint64_t,const std::string&,int);uint64_t component(uint64_t,const std::string&);bool guid_accepted(uint64_t,const Guid&,uint64_t);Json inspect_players();};
Json inspect_client(uint32_t,const fs::path&,const std::string&);Json verify_evidence(const Json&,const Json&,double maximum_age=15);
}
