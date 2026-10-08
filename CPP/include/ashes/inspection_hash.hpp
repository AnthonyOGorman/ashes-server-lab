#pragma once
#include "common.hpp"
namespace ashes {
struct VerifiedExecutableHash {std::string hash;bool cached=false;Json file_identity;};
VerifiedExecutableHash verified_executable_hash(const fs::path&,uint32_t,uint64_t,const std::string&);
}
