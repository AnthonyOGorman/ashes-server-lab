#pragma once
#include <cstdint>
constexpr uint32_t MAGIC=0x414F4349,VERSION=2;
enum Command:uint32_t {STATUS=0,ACTIVATE=1,CURSOR=2,KEY=3,DEACTIVATE=4,RESTORE=5};
#pragma pack(push,1)
struct Request {uint32_t magic,version,command;int32_t x,y;uint32_t reserved;};
struct Response {uint32_t magic,status,pid,active,hooks,held;int32_t x,y;uint64_t hwnd;uint32_t foreground_pid,build_id;};
#pragma pack(pop)
static_assert(sizeof(Request)==24&&sizeof(Response)==48,"Wire sizes are fixed");
