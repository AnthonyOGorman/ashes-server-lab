// Local EOS compatibility subset for this client's 25 delay imports.
// No network access or Epic credentials; local compatibility is not protection.
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <deque>
#include <memory>
#include <unordered_map>
#include <string>

#define API extern "C" __declspec(dllexport)
struct Credentials { int32_t ApiVersion; const char* Token; int32_t Type; };
struct LoginOptions { int32_t ApiVersion; const Credentials* CredentialsPtr; const void* UserLoginInfo; };
struct LoginCallbackInfo { int32_t ResultCode; void* ClientData; void* LocalUserId; void* ContinuanceToken; };
struct NotifyOptions { int32_t ApiVersion; };
using LoginCallback = void (*)(const LoginCallbackInfo*);
static_assert(sizeof(Credentials)==24 && offsetof(Credentials,Token)==8, "x64 credential ABI");
static_assert(sizeof(LoginOptions)==24 && offsetof(LoginOptions,CredentialsPtr)==8, "x64 login ABI");
static_assert(sizeof(LoginCallbackInfo)==32 && offsetof(LoginCallbackInfo,LocalUserId)==16, "x64 callback ABI");
struct Pending { LoginCallback callback; LoginCallbackInfo info; };
struct Context { bool logged_in=false; bool session=false; uint64_t next_notify=1; std::deque<Pending> pending; std::unordered_map<uint64_t,void*> notifications; };
struct LocalUser { std::string id; };
static LocalUser user{"eeeeeeee000000000000000000000001"};
static std::unordered_map<void*,std::unique_ptr<Context>> contexts;
static Context* context(void* handle) { auto i=contexts.find(handle); return i==contexts.end()?nullptr:i->second.get(); }

API void* LocalEOS_CreateConnect() {
    auto ptr=std::make_unique<Context>(); void* handle=ptr.get(); contexts.emplace(handle,std::move(ptr)); return handle;
}
API void LocalEOS_DestroyConnect(void* handle) { contexts.erase(handle); }
API const char* LocalEOS_GetScope() { return "local compatibility; no Epic authentication or anti-cheat protection"; }
API const char* EOS_GetVersion() { return "LocalEOSConnect-0.2"; }
API int32_t EOS_Initialize(const int32_t* options) { return options && *options==4?0:10; }
API int32_t EOS_Shutdown() { contexts.clear(); return 0; }
API int32_t EOS_Logging_SetCallback(void (*callback)(const void*)) { return callback?0:10; }
API int32_t EOS_Logging_SetLogLevel(int32_t,int32_t) { return 0; }
API const char* EOS_EResult_ToString(int32_t result) {
    switch(result) { case 0:return "EOS_Success";case 2:return "EOS_InvalidCredentials";
        case 10:return "EOS_InvalidParameters";case 16:return "EOS_NotImplemented";
        case 22:return "EOS_LimitExceeded";default:return "LocalEOS_UnmodeledResult"; }
}
API void* EOS_Platform_Create(const void* options) { return options?LocalEOS_CreateConnect():nullptr; }
API void EOS_Platform_Release(void* handle) { LocalEOS_DestroyConnect(handle); }
API void* EOS_Platform_GetConnectInterface(void* handle) { return context(handle)?handle:nullptr; }
API void* EOS_Platform_GetAntiCheatClientInterface(void* handle) { return context(handle)?handle:nullptr; }
API int32_t EOS_Platform_SetApplicationStatus(void* handle,int32_t) { return context(handle)?0:10; }
API int32_t EOS_Platform_SetNetworkStatus(void* handle,int32_t) { return context(handle)?0:10; }

// This local model has one pre-existing user, so it never emits InvalidUser or
// a continuance token. Reject CreateUser rather than inventing a valid token.
API void EOS_Connect_CreateUser(void* handle,const void*,void* data,LoginCallback callback) {
    Context* c=context(handle);if(c && callback)c->pending.push_back({callback,{10,data,nullptr,nullptr}});
}

API void EOS_Connect_Login(void* handle,const LoginOptions* options,void* data,LoginCallback callback) {
    Context* c=context(handle); if(!c || !callback) return;
    int32_t result=10; // EOS_InvalidParameters
    if(options && options->ApiVersion==2 && options->CredentialsPtr && !options->UserLoginInfo) {
        const Credentials& creds=*options->CredentialsPtr;
        if(creds.ApiVersion==1 && creds.Type==9 && creds.Token) {
            // A fixed marker, not an external authentication token.
            result=std::strcmp(creds.Token,"lab-local-account")==0?0:2;
        }
    }
    c->pending.push_back({callback,{result,data,result==0?&user:nullptr,nullptr}});
}
API void EOS_Platform_Tick(void* handle) {
    Context* c=context(handle); if(!c) return;
    // Detach this tick's queue; work queued by callbacks waits until next tick.
    std::deque<Pending> pending; pending.swap(c->pending);
    for(const auto& item:pending) {
        c=context(handle); if(!c) break;
        if(item.info.ResultCode==0) c->logged_in=true;
        item.callback(&item.info);
    }
}
API int32_t EOS_Connect_GetLoginStatus(void* handle,void* id) { Context* c=context(handle); return c && c->logged_in && id==&user?2:0; }
API int32_t EOS_Connect_GetLoggedInUsersCount(void* handle) { Context* c=context(handle); return c && c->logged_in?1:0; }
API void* EOS_Connect_GetLoggedInUserByIndex(void* handle,int32_t index) { Context* c=context(handle); return c && c->logged_in && index==0?&user:nullptr; }
API uint64_t EOS_Connect_AddNotifyAuthExpiration(void* handle,const NotifyOptions* options,void* data,void (*callback)(const void*)) {
    Context* c=context(handle); if(!c || !options || options->ApiVersion!=1 || !callback) return 0;
    uint64_t id=c->next_notify++; c->notifications.emplace(id,data); return id;
}
API void EOS_Connect_RemoveNotifyAuthExpiration(void* handle,uint64_t id) { Context* c=context(handle); if(c) c->notifications.erase(id); }
// Notification registration models local API lifecycle, not integrity verdicts.
API uint64_t EOS_AntiCheatClient_AddNotifyMessageToServer(void* handle,const NotifyOptions* options,void* data,void (*callback)(const void*)) {
    return EOS_Connect_AddNotifyAuthExpiration(handle,options,data,callback);
}
API uint64_t EOS_AntiCheatClient_AddNotifyClientIntegrityViolated(void* handle,const NotifyOptions* options,void* data,void (*callback)(const void*)) {
    return EOS_Connect_AddNotifyAuthExpiration(handle,options,data,callback);
}
API void EOS_AntiCheatClient_RemoveNotifyMessageToServer(void* handle,uint64_t id) { EOS_Connect_RemoveNotifyAuthExpiration(handle,id); }
API void EOS_AntiCheatClient_RemoveNotifyClientIntegrityViolated(void* handle,uint64_t id) { EOS_Connect_RemoveNotifyAuthExpiration(handle,id); }
API int32_t EOS_AntiCheatClient_BeginSession(void* handle,const void* options) {
    Context* c=context(handle);if(!c || !options || !c->logged_in)return 10;
    c->session=true;return 0;
}
API int32_t EOS_AntiCheatClient_EndSession(void* handle,const void* options) {
    Context* c=context(handle);if(!c || !options)return 10;c->session=false;return 0;
}
API int32_t EOS_AntiCheatClient_ReceiveMessageFromServer(void*,const void*) {
    // No protection protocol is implemented. Never accept opaque EAC messages.
    return 16;
}
API int32_t EOS_ProductUserId_IsValid(void* id) { return id==&user; }
API void* EOS_ProductUserId_FromString(const char* text) { return text && user.id==text?&user:nullptr; }
API int32_t EOS_ProductUserId_ToString(void* id,char* buffer,int32_t* length) {
    if(id!=&user || !length) return 10;
    const int32_t required=33; int32_t capacity=*length; *length=required;
    if(!buffer || capacity<required) return 22; // EOS_LimitExceeded
    std::memcpy(buffer,user.id.c_str(),required); return 0;
}
