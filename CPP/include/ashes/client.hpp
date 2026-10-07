#pragma once
#include "common.hpp"
#include <windows.h>

namespace ashes {
std::wstring quote_windows_argument(const std::wstring& value);

struct ClientProcess {
    HANDLE process = nullptr;
    DWORD pid = 0;
    Json launch = Json::object();
    fs::path log_path;
    uint64_t log_offset = 0;
    double world_loaded_at = 0;
    std::string log_pending;
    bool authenticated = false, lobby_ready = false, welcomed = false, world_loaded = false;
    ~ClientProcess();
    Json start(const fs::path& root, const Json& config);
    Json state();
};
}
