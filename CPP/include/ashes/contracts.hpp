#pragma once
#include "common.hpp"
namespace ashes {
struct Contracts {Json schema;explicit Contracts(const fs::path& p):schema(read_json(p)){}Bytes encode(const std::string&,const Json&)const;Json decode(const std::string&,const Bytes&)const;};
}
