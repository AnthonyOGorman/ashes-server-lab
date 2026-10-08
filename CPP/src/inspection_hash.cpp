#include "ashes/inspection_hash.hpp"
#include <windows.h>
#include <mutex>
#include <map>
#include <algorithm>
#include <cwctype>
namespace ashes {
namespace {
struct FileIdentity {
 DWORD volume,index_high,index_low;uint64_t size,write;
 bool operator==(const FileIdentity&)const=default;
 Json json()const{return {{"volume",volume},{"index_high",index_high},{"index_low",index_low},{"size",size},{"last_write_filetime",write}};}
};
FileIdentity file_identity(const fs::path& path){
 HANDLE file=CreateFileW(path.c_str(),FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
 require(file!=INVALID_HANDLE_VALUE,"Cannot read executable file identity");BY_HANDLE_FILE_INFORMATION info{};bool ok=GetFileInformationByHandle(file,&info)!=0;CloseHandle(file);
 require(ok&&!(info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY),"Executable file identity unavailable");
 return {info.dwVolumeSerialNumber,info.nFileIndexHigh,info.nFileIndexLow,(uint64_t(info.nFileSizeHigh)<<32)|info.nFileSizeLow,(uint64_t(info.ftLastWriteTime.dwHighDateTime)<<32)|info.ftLastWriteTime.dwLowDateTime};
}
struct Entry {FileIdentity identity;std::string hash;};
std::mutex cache_mutex;
std::map<std::tuple<uint32_t,uint64_t,std::wstring>,Entry> cache;
}
VerifiedExecutableHash verified_executable_hash(const fs::path& path,uint32_t pid,uint64_t lifetime,const std::string& expected){
 require(pid>0&&lifetime>0,"Exact process lifetime required for executable verification");
 auto canonical=fs::weakly_canonical(path).wstring();std::transform(canonical.begin(),canonical.end(),canonical.begin(),[](wchar_t c){return std::towlower(c);});
 auto key=std::tuple{pid,lifetime,canonical};std::lock_guard lock(cache_mutex);auto before=file_identity(path);auto found=cache.find(key);
 if(found!=cache.end()&&found->second.identity==before){require(found->second.hash==expected,"Game executable hash mismatch");return {found->second.hash,true,before.json()};}
 auto hash=sha256_file(path);auto after=file_identity(path);require(before==after,"Executable changed during hash verification");require(hash==expected,"Game executable hash mismatch");
 if(cache.size()>=32)cache.erase(cache.begin());cache.insert_or_assign(key,Entry{after,hash});return {hash,false,after.json()};
}
}
