#include "ashes/client.hpp"
#include <tlhelp32.h>
#include <fstream>
#include <limits>
#include <cstdio>

namespace ashes {
namespace {
double log_timestamp(const std::string& line){
    SYSTEMTIME stamp{};int year,month,day,hour,minute;double seconds;
    if(std::sscanf(line.c_str(),"{\"timestamp\":\"%d-%d-%dT%d:%d:%lf",&year,&month,&day,&hour,&minute,&seconds)!=6||!std::isfinite(seconds)||seconds<0||seconds>=60)return 0;
    stamp.wYear=WORD(year);stamp.wMonth=WORD(month);stamp.wDay=WORD(day);stamp.wHour=WORD(hour);stamp.wMinute=WORD(minute);stamp.wSecond=WORD(seconds);stamp.wMilliseconds=WORD(std::min(int((seconds-std::floor(seconds))*1000+.5),999));FILETIME file;
    if(!SystemTimeToFileTime(&stamp,&file))return 0;
    return double((uint64_t(file.dwHighDateTime)<<32)|file.dwLowDateTime)/10000000.-11644473600.;
}
struct Handle {
    HANDLE value;
    explicit Handle(HANDLE h) : value(h) {}
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
};
DWORD existing_client(const fs::path& executable) {
    Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0));
    require(snapshot.value != INVALID_HANDLE_VALUE, "Cannot check running game processes");
    PROCESSENTRY32W entry{};
    entry.dwSize = sizeof(entry);
    for (BOOL found = Process32FirstW(snapshot.value, &entry); found; found = Process32NextW(snapshot.value, &entry)) {
        if (_wcsicmp(entry.szExeFile, executable.filename().c_str()) != 0) continue;
        Handle candidate(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, entry.th32ProcessID));
        require(candidate.value != nullptr, "Cannot verify an existing game process; close it before launching another client");
        wchar_t path[32768];
        DWORD length = 32768;
        require(QueryFullProcessImageNameW(candidate.value, 0, path, &length), "Cannot verify existing game path");
        if (_wcsicmp(fs::weakly_canonical(fs::path(path)).c_str(), executable.c_str()) == 0) return entry.th32ProcessID;
    }
    return 0;
}
}

std::wstring quote_windows_argument(const std::wstring& value) {
    std::wstring result = L"\"";
    size_t slashes = 0;
    for (wchar_t c : value) {
        if (c == L'\\') { ++slashes; continue; }
        result.append(c == L'"' ? slashes * 2 + 1 : slashes, L'\\');
        result += c;
        slashes = 0;
    }
    result.append(slashes * 2, L'\\');
    return result + L'"';
}

ClientProcess::~ClientProcess() { if (process) CloseHandle(process); }
Json ClientProcess::start(const fs::path& root, const Json& config) {
    if (process) {
        DWORD code = 0;
        require(GetExitCodeProcess(process, &code), "Cannot query launched game process");
        if (code == STILL_ACTIVE) return {{"ok", true}, {"pid", pid}, {"message", "Client already running; use its game window"}};
        CloseHandle(process);
        process = nullptr;
    }
    Handle gate(CreateMutexW(nullptr, FALSE, L"Local\\AshesCppClientLauncher"));
    require(gate.value != nullptr, "Cannot create client launch lock");
    DWORD acquired = WaitForSingleObject(gate.value, 0);
    require(acquired == WAIT_OBJECT_0 || acquired == WAIT_ABANDONED, "A client launch is already in progress");
    struct Release { HANDLE handle; ~Release() { ReleaseMutex(handle); } } release{gate.value};
    auto executable = fs::weakly_canonical(config.at("client_exe").get<std::string>());
    auto already = existing_client(executable);
    require(already == 0, "Game client PID " + std::to_string(already) + " is already running. Close it before launching a client connected to this lab.");
    require(sha256_file(executable) == config.at("client_sha256").get<std::string>(), "Installed game executable hash mismatch");
    require(sha256_file(config.at("sdk_path").get<std::string>()) == config.at("sdk_sha256").get<std::string>(), "Installed local EOS SDK hash mismatch");
    const auto override = fs::absolute(root / "config/WindowsEngine.ini");
    require(fs::is_regular_file(override), "Client launch configuration is missing");
    auto run = fs::absolute(root / "runs" / random_id(8));
    fs::create_directories(run);
    const auto profile = fs::absolute(root / "client-profile");
    fs::create_directories(profile);
    log_path = run / "game.log";
    std::vector<std::wstring> arguments{
        executable.wstring(), L"-LauncherTetherPort=" + std::to_wstring(config.at("tether_port").get<int>()),
        L"-windowed", L"-ResX=1280", L"-ResY=720", L"-WinX=100", L"-WinY=100", L"-ForceRes",
        L"-log", L"-stdout", L"-FullStdOutLogOutput", L"-UserDir=" + profile.wstring(),
        L"-abslog=" + log_path.wstring(), L"-iniFile=" + override.wstring(),
        L"-LogCmds=LogNet Verbose,LogNetTraffic Verbose,LogNetPackageMap Verbose,LogCore Warning"
    };
    std::wstring command;
    Json args = Json::array();
    for (const auto& arg : arguments) {
        if (!command.empty()) command += L' ';
        command += quote_windows_argument(arg);
        args.push_back(fs::path(arg).string());
    }
    launch = {{"args", args}, {"mode", "local_lobby"}, {"client_sha256", config.at("client_sha256")},
        {"run_directory", run.string()}, {"game_log", log_path.string()}, {"started_at", wall_time()}};
    write_file(run / "launch.json", launch.dump(2));
    SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    Handle output(CreateFileW((run / "stdout.log").c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, &security, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr));
    Handle input(CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &security, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    require(output.value != INVALID_HANDLE_VALUE && input.value != INVALID_HANDLE_VALUE, "Cannot create client log handles");
    SIZE_T bytes = 0;
    InitializeProcThreadAttributeList(nullptr, 1, 0, &bytes);
    std::vector<uint8_t> storage(bytes);
    auto attributes = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(storage.data());
    require(InitializeProcThreadAttributeList(attributes, 1, 0, &bytes), "Cannot initialize launch handle list");
    struct DeleteAttributes { LPPROC_THREAD_ATTRIBUTE_LIST list; ~DeleteAttributes() { DeleteProcThreadAttributeList(list); } } cleanup{attributes};
    HANDLE inherited[] = {output.value, input.value};
    require(UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherited, sizeof(inherited), nullptr, nullptr), "Cannot isolate client log handles");
    STARTUPINFOEXW startup{};
    startup.StartupInfo.cb = sizeof(startup);
    wchar_t desktop[] = L"winsta0\\default";
    startup.StartupInfo.lpDesktop = desktop;
    startup.StartupInfo.dwFlags = STARTF_USESHOWWINDOW | STARTF_USESTDHANDLES;
    startup.StartupInfo.wShowWindow = SW_SHOWNORMAL;
    startup.StartupInfo.hStdOutput = startup.StartupInfo.hStdError = output.value;
    startup.StartupInfo.hStdInput = input.value;
    startup.lpAttributeList = attributes;
    PROCESS_INFORMATION child{};
    BOOL created = CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr, TRUE,
        EXTENDED_STARTUPINFO_PRESENT | CREATE_NEW_PROCESS_GROUP, nullptr, run.c_str(), &startup.StartupInfo, &child);
    DWORD launch_error = created ? ERROR_SUCCESS : GetLastError();
    require(created, "Windows could not launch the game: " + std::to_string(launch_error));
    CloseHandle(child.hThread);
    process = child.hProcess;
    pid = child.dwProcessId;
    log_offset = 0;
    world_loaded_at = gameplay_visible_at = 0;
    log_pending.clear();
    authenticated = lobby_ready = welcomed = world_loaded = gameplay_visible = false;
    launch["pid"] = pid;
    write_file(run / "launch.json", launch.dump(2));
    return {{"ok", true}, {"pid", pid}, {"message", "Client started with the local connection."}};
}

Json ClientProcess::state() {
    if (!process) return {{"running", false}, {"status", "Ready to start"}};
    DWORD code = 0;
    require(GetExitCodeProcess(process, &code), "Cannot query game process status");
    std::ifstream stream(log_path, std::ios::binary);
    if (stream) {
        stream.seekg(0, std::ios::end);
        auto size = stream.tellg();
        if (size >= 0 && uint64_t(size) < log_offset) { log_offset = 0; log_pending.clear(); }
        stream.seekg(std::streamoff(log_offset));
        std::array<char, 65536> buffer{};
        stream.read(buffer.data(), buffer.size());
        auto received = stream.gcount();
        log_offset += uint64_t(received);
        log_pending.append(buffer.data(), size_t(received));
        size_t newline;
        while ((newline = log_pending.find('\n')) != std::string::npos) {
            auto line = log_pending.substr(0, newline);
            log_pending.erase(0, newline + 1);
            if (line.find("XClient_AsyncSessionReplySink") != std::string::npos && line.find("IcsStatusCodeSuccess") != std::string::npos && line.find("Missing") == std::string::npos) authenticated = true;
            if (line.find("XClient_AsyncGetCharactersReplySink") != std::string::npos && line.find("IcsStatusCodeSuccess") != std::string::npos) lobby_ready = true;
            if (line.find("Welcomed by server") != std::string::npos) { welcomed = true; world_loaded = gameplay_visible = false; world_loaded_at = gameplay_visible_at = 0; }
            if (line.find("Load map complete") != std::string::npos && line.find("Verra_World_Master") != std::string::npos) {
                world_loaded = true;world_loaded_at=log_timestamp(line);gameplay_visible=false;gameplay_visible_at=0;
            }
            // The final visibility log follows HideLoadingScreen and its garbage collection;
            // a title-screen hide or a prior travel epoch must never unlock gameplay.
            if(welcomed&&world_loaded&&world_loaded_at>0&&line.find("\"category\":\"LogLoadingScreen\"")!=std::string::npos&&line.find("\"message\":\"Visible for ")!=std::string::npos){
                double hidden_at=log_timestamp(line);if(hidden_at>=world_loaded_at){gameplay_visible=true;gameplay_visible_at=hidden_at;}
            }
        }
        if (log_pending.size() > 65536) log_pending.clear();
    }
    bool running = code == STILL_ACTIVE;
    std::string status = !running ? "Client closed" : welcomed ? "World connection accepted" : lobby_ready ? "Connected to local lobby" : authenticated ? "Local login accepted" : "Client running; connecting to local lobby";
    return {{"running", running}, {"pid", pid}, {"status", status}, {"authenticated", authenticated}, {"lobby_ready", lobby_ready},
        {"welcomed", welcomed}, {"world_loaded", world_loaded}, {"world_loaded_at", world_loaded_at}, {"gameplay_visible",gameplay_visible},{"gameplay_visible_at",gameplay_visible_at}, {"exit_code", running ? Json() : Json(code)}, {"launch", launch}};
}
}
