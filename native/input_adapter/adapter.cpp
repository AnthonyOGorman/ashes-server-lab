// Offline Ashes Lab input adapter. No detours, security hooks or executable file patches.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <sddl.h>
#include <atomic>
#include <vector>
#include <string>
#include <algorithm>
#include <cstdint>
#include <cwchar>
#include <cstring>
#include "protocol.h"
#include "build/build_tag.h"

static std::atomic<bool> active{false};
static std::atomic<uint64_t> cursor{0};
static std::atomic<HWND> window{nullptr}, capture{nullptr}, focus{nullptr};
static std::atomic<HCURSOR> shape{nullptr};
static std::atomic<int> visible{0};
static std::atomic<SHORT> keys[256];
static std::atomic<ULONGLONG> lastCommand{0};
static bool fixture=false;
struct Patch { void** slot; void* old; void* replacement; };
static std::vector<Patch> patches;
static bool patched=false;
static HMODULE user32=nullptr;
#define ORIGINAL(name) static decltype(&::name) original_##name=nullptr
ORIGINAL(GetCursorPos); ORIGINAL(SetCursorPos); ORIGINAL(GetForegroundWindow);
ORIGINAL(GetActiveWindow); ORIGINAL(GetFocus); ORIGINAL(SetFocus); ORIGINAL(SetActiveWindow);
ORIGINAL(SetForegroundWindow); ORIGINAL(AllowSetForegroundWindow); ORIGINAL(GetKeyState);
ORIGINAL(GetAsyncKeyState); ORIGINAL(GetCapture); ORIGINAL(SetCapture); ORIGINAL(ReleaseCapture);
ORIGINAL(ClipCursor); ORIGINAL(GetClipCursor); ORIGINAL(SetCursor); ORIGINAL(ShowCursor);
ORIGINAL(WindowFromPoint); ORIGINAL(SendInput); ORIGINAL(ShowWindow);
ORIGINAL(SetWindowPos); ORIGINAL(SetWindowPlacement);
static POINT position() { auto v=cursor.load(); return {LONG(uint32_t(v)),LONG(uint32_t(v>>32))}; }
static void position(POINT p) { cursor.store(uint32_t(p.x)|(uint64_t(uint32_t(p.y))<<32)); }
static bool ours(HWND h) { DWORD pid=0; return h && IsWindow(h) && GetWindowThreadProcessId(h,&pid) && pid==GetCurrentProcessId(); }
static bool on() { return active.load() && ours(window.load()); }
static BOOL WINAPI hook_GetCursorPos(LPPOINT p) { if(!on()) return original_GetCursorPos(p); if(!p){SetLastError(ERROR_INVALID_PARAMETER);return FALSE;} *p=position(); return TRUE; }
static BOOL WINAPI hook_SetCursorPos(int x,int y) { if(!on()) return original_SetCursorPos(x,y); position({x,y}); return TRUE; }
static HWND WINAPI hook_GetForegroundWindow() { return on()?window.load():original_GetForegroundWindow(); }
static HWND WINAPI hook_GetActiveWindow() { return on()?window.load():original_GetActiveWindow(); }
static HWND WINAPI hook_GetFocus() { return on()?focus.load():original_GetFocus(); }
static HWND WINAPI hook_SetFocus(HWND h) { if(!on()) return original_SetFocus(h); HWND old=focus.load(); if(ours(h)||!h) focus.store(h); return old; }
static HWND WINAPI hook_SetActiveWindow(HWND h) { if(!on()) return original_SetActiveWindow(h); return window.load(); }
static BOOL WINAPI hook_SetForegroundWindow(HWND h) { return on()?TRUE:original_SetForegroundWindow(h); }
static BOOL WINAPI hook_AllowSetForegroundWindow(DWORD pid) { return on()?TRUE:original_AllowSetForegroundWindow(pid); }
static SHORT WINAPI hook_GetKeyState(int key) { return on()?(key>=0&&key<256?keys[key].load():0):original_GetKeyState(key); }
static SHORT WINAPI hook_GetAsyncKeyState(int key) { return on()?(key>=0&&key<256?keys[key].load():0):original_GetAsyncKeyState(key); }
static HWND WINAPI hook_GetCapture() { return on()?capture.load():original_GetCapture(); }
static HWND WINAPI hook_SetCapture(HWND h) { if(!on()) return original_SetCapture(h); auto old=capture.load(); if(ours(h)||!h) capture.store(h); return old; }
static BOOL WINAPI hook_ReleaseCapture() { if(!on()) return original_ReleaseCapture(); capture.store(nullptr); return TRUE; }
static BOOL WINAPI hook_ClipCursor(const RECT* r) { return on()?TRUE:original_ClipCursor(r); }
static BOOL WINAPI hook_GetClipCursor(LPRECT r) { if(!on()) return original_GetClipCursor(r); if(!r)return FALSE; return GetWindowRect(window.load(),r); }
static HCURSOR WINAPI hook_SetCursor(HCURSOR c) { if(!on()) return original_SetCursor(c); return shape.exchange(c); }
static int WINAPI hook_ShowCursor(BOOL show) { if(!on()) return original_ShowCursor(show); return show?++visible:--visible; }
static HWND WINAPI hook_WindowFromPoint(POINT p) { if(!on()) return original_WindowFromPoint(p); RECT r{}; GetWindowRect(window.load(),&r); return PtInRect(&r,p)?window.load():nullptr; }
static UINT WINAPI hook_SendInput(UINT n,LPINPUT input,int size) { return on()?n:original_SendInput(n,input,size); }
static BOOL WINAPI hook_ShowWindow(HWND h,int command) { if(on() && command!=SW_HIDE && command!=SW_MINIMIZE && command!=SW_SHOWMINNOACTIVE) command=SW_SHOWNOACTIVATE; return original_ShowWindow(h,command); }
static BOOL WINAPI hook_SetWindowPos(HWND h,HWND after,int x,int y,int cx,int cy,UINT flags) { if(on())flags|=SWP_NOACTIVATE|SWP_NOZORDER; return original_SetWindowPos(h,after,x,y,cx,cy,flags); }
static BOOL WINAPI hook_SetWindowPlacement(HWND h,const WINDOWPLACEMENT* p) { if(!on()||!p)return original_SetWindowPlacement(h,p); auto copy=*p; if(copy.showCmd!=SW_HIDE&&copy.showCmd!=SW_SHOWMINNOACTIVE)copy.showCmd=SW_SHOWNOACTIVATE; return original_SetWindowPlacement(h,&copy); }
struct Hook { const char* name; void* replacement; void** original; };
#define HOOK(name) {#name,reinterpret_cast<void*>(&hook_##name),reinterpret_cast<void**>(&original_##name)}
static Hook hooks[]={HOOK(GetCursorPos),HOOK(SetCursorPos),HOOK(GetForegroundWindow),HOOK(GetActiveWindow),HOOK(GetFocus),HOOK(SetFocus),HOOK(SetActiveWindow),HOOK(SetForegroundWindow),HOOK(AllowSetForegroundWindow),HOOK(GetKeyState),HOOK(GetAsyncKeyState),HOOK(GetCapture),HOOK(SetCapture),HOOK(ReleaseCapture),HOOK(ClipCursor),HOOK(GetClipCursor),HOOK(SetCursor),HOOK(ShowCursor),HOOK(WindowFromPoint),HOOK(SendInput),HOOK(ShowWindow),HOOK(SetWindowPos),HOOK(SetWindowPlacement)};
static bool exchange(Patch& p, bool install) {
    DWORD old=0; if(!VirtualProtect(p.slot,sizeof(void*),PAGE_READWRITE,&old))return false;
    auto result=InterlockedCompareExchangePointer(p.slot,install?p.replacement:p.old,install?p.old:p.replacement);
    DWORD unused=0; VirtualProtect(p.slot,sizeof(void*),old,&unused);
    return result==(install?p.old:p.replacement);
}
static void deactivate(){ active.store(false); for(auto& k:keys)k.store(0); capture.store(nullptr); }
static bool install(){
    if(patched)return true;
    patches.clear();
    auto base=reinterpret_cast<BYTE*>(GetModuleHandleW(nullptr));
    auto dos=reinterpret_cast<IMAGE_DOS_HEADER*>(base);
    auto nt=reinterpret_cast<IMAGE_NT_HEADERS64*>(base+dos->e_lfanew);
    if(dos->e_magic!=IMAGE_DOS_SIGNATURE||nt->Signature!=IMAGE_NT_SIGNATURE||nt->OptionalHeader.Magic!=IMAGE_NT_OPTIONAL_HDR64_MAGIC)return false;
    auto& entry=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    auto imports=reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(base+entry.VirtualAddress);
    for(auto i=imports;i->Name;i++){
        if(_stricmp(reinterpret_cast<char*>(base+i->Name),"USER32.dll")!=0)continue;
        if(!i->OriginalFirstThunk)return false;
        auto names=reinterpret_cast<IMAGE_THUNK_DATA64*>(base+i->OriginalFirstThunk);
        auto slots=reinterpret_cast<IMAGE_THUNK_DATA64*>(base+i->FirstThunk);
        for(;names->u1.AddressOfData;names++,slots++){
            if(IMAGE_SNAP_BY_ORDINAL64(names->u1.Ordinal))continue;
            auto n=reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(base+names->u1.AddressOfData)->Name;
            for(auto& h:hooks)if(strcmp(reinterpret_cast<char*>(n),h.name)==0){
                auto slot=reinterpret_cast<void**>(&slots->u1.Function);
                // Refuse preexisting redirects; this adapter does not replace other hooks.
                if(*slot!=*h.original)return false;
                patches.push_back({slot,*slot,h.replacement}); break;
            }
        }
    }
    for(const char* required:{"GetCursorPos","GetForegroundWindow","SetCursorPos","ClipCursor","SetCapture","SetFocus","SetForegroundWindow","SendInput"}){
        auto found=std::find_if(patches.begin(),patches.end(),[&](Patch& p){auto it=std::find_if(std::begin(hooks),std::end(hooks),[&](Hook& h){return h.replacement==p.replacement;});return it!=std::end(hooks)&&strcmp(it->name,required)==0;});
        if(found==patches.end())return false;
    }
    size_t count=0;
    for(auto& p:patches){ if(!exchange(p,true)){for(size_t j=0;j<count;j++)exchange(patches[j],false);return false;}count++; }
    patched=true; return true;
}
static bool restore(){ deactivate(); bool ok=true; if(patched)for(auto& p:patches)ok=exchange(p,false)&&ok; if(ok){patched=false;patches.clear();} return ok; }
static BOOL CALLBACK choose(HWND h,LPARAM out){
    if(!ours(h)||(!fixture&&!IsWindowVisible(h))||IsIconic(h))return TRUE;
    RECT r{}; GetClientRect(h,&r); auto best=reinterpret_cast<std::pair<LONG,HWND>*>(out);
    LONG area=(r.right-r.left)*(r.bottom-r.top); if(area>best->first)*best={area,h}; return TRUE;
}
static bool allowedKey(int k){ return k=='W'||k=='A'||k=='S'||k=='D'||k==VK_SPACE||k==VK_ESCAPE||k==VK_RETURN||k==VK_TAB||k==VK_UP||k==VK_DOWN||k==VK_LEFT||k==VK_RIGHT||k==VK_LBUTTON; }
static Response dispatch(const Request& q){
    DWORD status=ERROR_SUCCESS;
    if(q.magic!=MAGIC||q.version!=VERSION||q.reserved)status=ERROR_INVALID_DATA;
    else if(q.command==STATUS){}
    else if(q.command==ACTIVATE){
        if(!patched && !install())status=ERROR_NOT_SUPPORTED;
        else {std::pair<LONG,HWND> best{0,nullptr};EnumWindows(choose,reinterpret_cast<LPARAM>(&best));if(!best.second)status=ERROR_INVALID_WINDOW_HANDLE;else{window.store(best.second);focus.store(best.second);POINT p{};ClientToScreen(best.second,&p);position(p);active.store(true);}}
    } else if(q.command==DEACTIVATE)deactivate();
    else if(q.command==RESTORE){if(!restore())status=ERROR_WRITE_FAULT;}
    else if(q.command==CURSOR){
        RECT r{}; auto h=window.load();
        if(!on()||IsIconic(h)||!GetClientRect(h,&r))status=ERROR_INVALID_WINDOW_HANDLE;
        else if(q.x<0||q.y<0||q.x>=r.right||q.y>=r.bottom)status=ERROR_INVALID_PARAMETER;
        else {POINT p{q.x,q.y};if(ClientToScreen(h,&p))position(p);else status=GetLastError();}
    } else if(q.command==KEY){if(!on()||!allowedKey(q.x)||(q.y!=0&&q.y!=1))status=ERROR_INVALID_PARAMETER;else keys[q.x].store(q.y?SHORT(-32768):0);}
    else status=ERROR_INVALID_FUNCTION;
    lastCommand.store(GetTickCount64());auto p=position();uint32_t count=0;for(auto& k:keys)if(k.load())count++;
    HWND foreground=original_GetForegroundWindow();DWORD fgpid=0;if(foreground)GetWindowThreadProcessId(foreground,&fgpid);
    return {MAGIC,status,GetCurrentProcessId(),active.load()?1u:0u,uint32_t(patched?patches.size():0),count,p.x,p.y,uint64_t(window.load()),fgpid,BUILD_ID};
}
static PSECURITY_DESCRIPTOR security(){
    HANDLE token=nullptr;if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token))return nullptr;
    DWORD needed=0;GetTokenInformation(token,TokenUser,nullptr,0,&needed);std::vector<BYTE> buf(needed);
    if(!GetTokenInformation(token,TokenUser,buf.data(),needed,&needed)){CloseHandle(token);return nullptr;}CloseHandle(token);
    LPWSTR sid=nullptr;if(!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(buf.data())->User.Sid,&sid))return nullptr;
    std::wstring s=L"D:P(A;;GA;;;SY)(A;;GA;;;";s+=sid;s+=L")";LocalFree(sid);
    PSECURITY_DESCRIPTOR descriptor=nullptr;
    return ConvertStringSecurityDescriptorToSecurityDescriptorW(s.c_str(),SDDL_REVISION_1,&descriptor,nullptr)?descriptor:nullptr;
}
static DWORD WINAPI worker(void*){
    WCHAR path[32768]{};GetModuleFileNameW(nullptr,path,32768);auto name=wcsrchr(path,L'\\');name=name?name+1:path;
    fixture=_wcsicmp(name,L"ashes_input_fixture.exe")==0;
    if(!fixture&&_wcsicmp(name,L"AOCClient-Win64-Shipping.exe")!=0)return 1;
    user32=GetModuleHandleW(L"user32.dll");if(!user32)return 2;
    for(auto& h:hooks){*h.original=reinterpret_cast<void*>(GetProcAddress(user32,h.name));if(!*h.original)return 3;}
    auto descriptor=security();if(!descriptor)return 4;
    SECURITY_ATTRIBUTES attributes{sizeof(attributes),descriptor,FALSE};
    WCHAR pipeName[128]{};swprintf_s(pipeName,L"\\\\.\\pipe\\ashes-lab-input-%lu",GetCurrentProcessId());
    HANDLE pipe=CreateNamedPipeW(pipeName,PIPE_ACCESS_DUPLEX|FILE_FLAG_FIRST_PIPE_INSTANCE,PIPE_TYPE_MESSAGE|PIPE_READMODE_MESSAGE|PIPE_NOWAIT|PIPE_REJECT_REMOTE_CLIENTS,1,sizeof(Response),sizeof(Request),0,&attributes);
    LocalFree(descriptor);if(pipe==INVALID_HANDLE_VALUE)return 5;
    bool connected=false;
    for(;;){
        if(active.load()&&GetTickCount64()-lastCommand.load()>5000)deactivate();
        if(!connected){if(ConnectNamedPipe(pipe,nullptr)||GetLastError()==ERROR_PIPE_CONNECTED)connected=true;}
        if(connected){Request q{};DWORD bytes=0;BOOL read=ReadFile(pipe,&q,sizeof(q),&bytes,nullptr);
            if(read&&bytes==sizeof(q)){auto response=dispatch(q);DWORD sent=0;WriteFile(pipe,&response,sizeof(response),&sent,nullptr);}
            else if(!read&&GetLastError()!=ERROR_NO_DATA){DisconnectNamedPipe(pipe);connected=false;}
            else if(read&&bytes!=0){DisconnectNamedPipe(pipe);connected=false;}
        }
        Sleep(10);
    }
}
BOOL WINAPI DllMain(HINSTANCE self,DWORD reason,LPVOID){
    if(reason==DLL_PROCESS_ATTACH){DisableThreadLibraryCalls(self);HANDLE thread=CreateThread(nullptr,0,worker,nullptr,0,nullptr);if(thread)CloseHandle(thread);else return FALSE;}
    // The loader deliberately retains this DLL until process exit. No unsafe unload.
    return TRUE;
}
