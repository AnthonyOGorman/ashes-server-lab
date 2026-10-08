#include "ashes/inspection_hash.hpp"
#include <windows.h>
#include <iostream>
#include <chrono>
using namespace ashes;
int main(int argc,char** argv){try{
 require(argc==2,"CPP root required");auto root=fs::weakly_canonical(argv[1]);require(fs::exists(root/"src/inspection.cpp"),"Verified test workspace required");
 auto parent=root/"runs/loading-readiness-20261008";fs::create_directories(parent);
 auto dir=parent/("hash-fixture-"+std::to_string(GetCurrentProcessId())+"-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));require(fs::create_directory(dir),"Fresh owned fixture directory required");
 auto file=dir/"fixture.bin",backup=dir/"original.bin";write_file(file,std::string("abc"));
 const std::string abc="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";int checks=0;
 auto check=[&](bool condition){require(condition,"Executable hash cache check failed");checks++;};
 auto rejected=[&](uint32_t pid,uint64_t life,const std::string& expected){try{verified_executable_hash(file,pid,life,expected);return false;}catch(const std::exception&){return true;}};
 auto stamp=[&](uint64_t value){HANDLE h=CreateFileW(file.c_str(),FILE_WRITE_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);require(h!=INVALID_HANDLE_VALUE,"Fixture timestamp handle");FILETIME ft{DWORD(value),DWORD(value>>32)};bool ok=SetFileTime(h,nullptr,nullptr,&ft)!=0;CloseHandle(h);require(ok,"Fixture timestamp update");};
 auto first=verified_executable_hash(file,123,456,abc);check(!first.cached&&first.hash==abc);
 auto second=verified_executable_hash(file,123,456,abc);check(second.cached&&second.file_identity==first.file_identity);
 check(rejected(123,456,std::string(64,'0')));
 check(!verified_executable_hash(file,123,457,abc).cached);
 write_file(file,std::string("abd"));stamp(first.file_identity.at("last_write_filetime").get<uint64_t>()+10000);
 check(rejected(123,456,abc));auto abd=sha256(Bytes{'a','b','d'});auto changed=verified_executable_hash(file,123,456,abd);check(!changed.cached&&changed.hash==abd);
 check(verified_executable_hash(file,123,456,abd).cached);
 fs::rename(file,backup);write_file(file,std::string("abd"));stamp(changed.file_identity.at("last_write_filetime"));
 auto replaced=verified_executable_hash(file,123,456,abd);check(!replaced.cached&&replaced.file_identity!=changed.file_identity);
 write_file(file,std::string("longer payload"));check(rejected(123,456,abd));
 check(rejected(0,456,abd));check(rejected(123,0,abd));
 fs::remove(file);fs::remove(backup);fs::remove(dir);
 std::cout<<checks<<" executable identity cache checks passed (pins, lifetime, timestamp, replacement, length)\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
