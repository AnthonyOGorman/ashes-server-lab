#include "ashes/inspection.hpp"
#include <iostream>
int main(int argc,char** argv){try{ashes::require(argc>=3,"Usage: ashes_inspect PID config/backend.json [output.json]");auto config=ashes::read_json(argv[2]);auto result=ashes::inspect_client(uint32_t(std::stoul(argv[1])),config.at("client_exe").get<std::string>(),config.at("client_sha256"));if(argc>3)ashes::write_file(argv[3],result.dump(2));else std::cout<<result.dump(2)<<'\n';return 0;}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
