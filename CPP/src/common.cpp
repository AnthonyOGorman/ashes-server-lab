#include "ashes/common.hpp"
#include <windows.h>
#include <bcrypt.h>
#include <openssl/evp.h>
#include <fstream>
#include <chrono>
#include <iomanip>
#include <sstream>
namespace ashes {
double wall_time(){return std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();}double mono_time(){return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();}
Bytes read_file(const fs::path& p){std::ifstream f(p,std::ios::binary);require(bool(f),"Cannot read "+p.string());return Bytes(std::istreambuf_iterator<char>(f),{});}void write_file(const fs::path& p,const std::string& s){fs::create_directories(p.parent_path());std::ofstream f(p,std::ios::binary);require(bool(f),"Cannot write "+p.string());f<<s;require(bool(f),"Write failed "+p.string());}Json read_json(const fs::path& p){auto b=read_file(p);return Json::parse(b);}
std::string hex(const Bytes& b){const char* h="0123456789abcdef";std::string r;for(auto v:b){r+=h[v>>4];r+=h[v&15];}return r;}Bytes unhex(const std::string& s){require(s.size()%2==0,"Odd hex length");Bytes b;for(size_t i=0;i<s.size();i+=2){auto c=[](char v)->int{if(v>='0'&&v<='9')return v-'0';if(v>='a'&&v<='f')return v-'a'+10;if(v>='A'&&v<='F')return v-'A'+10;throw std::runtime_error("Invalid hex");};b.push_back(uint8_t(c(s[i])*16+c(s[i+1])));}return b;}
std::string sha256(const Bytes& b){Bytes d(32);unsigned n=0;EVP_Digest(b.data(),b.size(),d.data(),&n,EVP_sha256(),nullptr);return hex(d);}std::string sha256_file(const fs::path& p){std::ifstream f(p,std::ios::binary);require(bool(f),"Cannot hash "+p.string());auto* c=EVP_MD_CTX_new();EVP_DigestInit_ex(c,EVP_sha256(),nullptr);std::array<char,65536>b;while(f){f.read(b.data(),b.size());EVP_DigestUpdate(c,b.data(),size_t(f.gcount()));}Bytes d(32);unsigned n=0;EVP_DigestFinal_ex(c,d.data(),&n);EVP_MD_CTX_free(c);return hex(d);}
Bytes random_bytes(size_t n){Bytes b(n);require(BCryptGenRandom(nullptr,b.data(),ULONG(n),BCRYPT_USE_SYSTEM_PREFERRED_RNG)==0,"Secure random failed");return b;}std::string random_id(size_t n){return hex(random_bytes(n));}std::string base64(const Bytes& b){std::string s((b.size()+2)/3*4,'\0');int n=EVP_EncodeBlock(reinterpret_cast<unsigned char*>(s.data()),b.data(),int(b.size()));s.resize(n);return s;}
}
