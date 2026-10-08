#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <string>
#include "protocol.h"
// Force the fixture to import every target symbol without issuing desktop mutations.
static void* imported[]={reinterpret_cast<void*>(&GetCursorPos),reinterpret_cast<void*>(&SetCursorPos),reinterpret_cast<void*>(&GetForegroundWindow),reinterpret_cast<void*>(&GetActiveWindow),reinterpret_cast<void*>(&GetFocus),reinterpret_cast<void*>(&SetFocus),reinterpret_cast<void*>(&SetActiveWindow),reinterpret_cast<void*>(&SetForegroundWindow),reinterpret_cast<void*>(&AllowSetForegroundWindow),reinterpret_cast<void*>(&GetKeyState),reinterpret_cast<void*>(&GetAsyncKeyState),reinterpret_cast<void*>(&GetCapture),reinterpret_cast<void*>(&SetCapture),reinterpret_cast<void*>(&ReleaseCapture),reinterpret_cast<void*>(&ClipCursor),reinterpret_cast<void*>(&GetClipCursor),reinterpret_cast<void*>(&SetCursor),reinterpret_cast<void*>(&ShowCursor),reinterpret_cast<void*>(&WindowFromPoint),reinterpret_cast<void*>(&SendInput),reinterpret_cast<void*>(&ShowWindow),reinterpret_cast<void*>(&SetWindowPos),reinterpret_cast<void*>(&SetWindowPlacement)};
static Response command(uint32_t op,int x=0,int y=0){
    WCHAR pipe[128]{};swprintf_s(pipe,L"\\\\.\\pipe\\ashes-lab-input-%lu",GetCurrentProcessId());
    Request q{MAGIC,VERSION,op,x,y,0};Response response{};DWORD bytes=0;
    for(int i=0;i<300;i++){
        if(CallNamedPipeW(pipe,&q,sizeof(q),&response,sizeof(response),&bytes,100)&&bytes==sizeof(response))return response;
        Sleep(10);
    }
    printf("Pipe command failed %lu\n",GetLastError());ExitProcess(30);
}
int wmain(int argc,wchar_t** argv){
    if(argc!=2)return 2;
    size_t used=0;for(auto p:imported)if(p)used++;printf("Fixture imports: %zu\n",used);
    WNDCLASSW wc{};wc.lpfnWndProc=DefWindowProcW;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"AshesLabInputFixture";
    if(!RegisterClassW(&wc))return 3;
    HWND hwnd=CreateWindowExW(0,wc.lpszClassName,L"Hidden input fixture",WS_OVERLAPPEDWINDOW,100,100,320,240,nullptr,nullptr,wc.hInstance,nullptr);
    if(!hwnd)return 4;
    auto user=GetModuleHandleW(L"user32.dll");
    auto realCursor=reinterpret_cast<decltype(&GetCursorPos)>(GetProcAddress(user,"GetCursorPos"));
    auto realForeground=reinterpret_cast<decltype(&GetForegroundWindow)>(GetProcAddress(user,"GetForegroundWindow"));
    POINT before{};realCursor(&before);auto foreground=realForeground();
    if(!LoadLibraryW(argv[1])){printf("LoadLibrary failed %lu\n",GetLastError());return 5;}
    auto status=command(STATUS);if(status.status||status.active||status.hooks)return 6;
    auto activated=command(ACTIVATE);if(activated.status||!activated.active||activated.hooks!=23||activated.hwnd!=uint64_t(hwnd))return 7;
    auto moved=command(CURSOR,37,41);if(moved.status)return 8;
    POINT virtualPoint{};if(!GetCursorPos(&virtualPoint)||virtualPoint.x!=moved.x||virtualPoint.y!=moved.y)return 9;
    if(GetForegroundWindow()!=hwnd||GetFocus()!=hwnd)return 10;
    if(command(KEY,'W',1).status||!(GetKeyState('W')&0x8000))return 11;
    if(command(KEY,VK_MENU,1).status!=ERROR_INVALID_PARAMETER)return 12;
    if(command(99).status!=ERROR_INVALID_FUNCTION)return 13;
    if(command(CURSOR,-1,0).status!=ERROR_INVALID_PARAMETER)return 14;
    if(realForeground()!=foreground)return 15;
    POINT after{};realCursor(&after);
    // A person can move their mouse during this test; report coordinates without asserting immobility.
    printf("Real foreground unchanged: %s; real cursor before=(%ld,%ld) after=(%ld,%ld)\n",realForeground()==foreground?"true":"false",before.x,before.y,after.x,after.y);
    auto stopped=command(DEACTIVATE);if(stopped.active||stopped.held||GetForegroundWindow()!=realForeground())return 16;
    if(command(ACTIVATE).status||command(KEY,'W',1).status)return 19;
    Sleep(5300);
    auto expired=command(STATUS);if(expired.active||expired.held||GetForegroundWindow()!=realForeground())return 20;
    auto restored=command(RESTORE);if(restored.status||restored.hooks)return 17;
    POINT normal{},actual{};GetCursorPos(&normal);realCursor(&actual);if(normal.x!=actual.x||normal.y!=actual.y)return 18;
    printf("PASS: 23 reversible IAT hooks; virtual cursor/key/focus; fixed command validation; five-second watchdog; inactive restoration. No desktop setters invoked.\n");
    DestroyWindow(hwnd);return 0;
}
