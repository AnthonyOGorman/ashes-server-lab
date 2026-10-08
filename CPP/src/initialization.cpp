#include "ashes/backend.hpp"
#include <iphlpapi.h>
#include <chrono>

namespace ashes {
namespace {
bool owns_udp_port(DWORD pid, unsigned port) {
    ULONG bytes = 0;
    GetExtendedUdpTable(nullptr, &bytes, FALSE, AF_INET, UDP_TABLE_OWNER_PID, 0);
    require(bytes >= sizeof(MIB_UDPTABLE_OWNER_PID) && bytes <= 16 * 1024 * 1024, "UDP ownership table bounds");
    std::vector<uint8_t> storage(bytes);
    require(GetExtendedUdpTable(storage.data(), &bytes, FALSE, AF_INET, UDP_TABLE_OWNER_PID, 0) == NO_ERROR, "UDP ownership query failed");
    auto table = reinterpret_cast<PMIB_UDPTABLE_OWNER_PID>(storage.data());
    for (DWORD i = 0; i < table->dwNumEntries; ++i) {
        auto& row = table->table[i];
        if (row.dwOwningPid == pid && ntohs(static_cast<u_short>(row.dwLocalPort)) == port) return true;
    }
    return false;
}
}

void Backend::initialize_clients() {
    Json snapshot;
    DWORD inspected_pid = 0;
    const bool with_winstead_floor = config.value("initialize_winstead_floor", false);
    std::vector<std::string> steps{
        "ClientSetHUD", "LoadingInputLock", "LoadingInputLocked", "ClientRestart", "LoadingInputRelock", "LoadingInputRelocked", "ControllerPlayerState", "PawnPlayerState", "PlayerStateVerified", "CharacterInfoExport", "CharacterGuid", "CharacterGuidVerified", "CharacterName", "CharacterNameVerified", "StatsComponentExport", "GameStateBeginPlay"
    };
    if (with_winstead_floor) {
        steps.insert(steps.end(), {"NodeLayoutProbe", "NodeLayoutWinsteadFloor"});
    }
    steps.insert(steps.end(), {"StatsGravity", "StatsSpeed", "StatsResources", "StatsResourcesVerified", "PrepareMovement"});
    if (with_winstead_floor) steps.push_back("WinsteadCollisionAdmitted");
    steps.insert(steps.end(), {"PawnPresentationReady", "ActivateMovement", "PawnAutonomous", "NativeMovementReady", "GameplayPresentationReady", "LoadingInputRelease", "WorldReady"});
    while (!stopping) {
        bool progressed = false;
        double attempt_started = mono_time();
        try { synchronize_movement_speed(); } catch(const std::exception& error) { event("speed_sync_waiting",{{"reason",error.what()}}); }
        std::string connection_id, step;
        DWORD pid = 0;
        try {
            {
                std::lock_guard lock(mutex);
                if (!config.value("auto_initialize", true) || !world.running || !client_process.process) {
                    snapshot = Json();
                } else {
                    auto client = client_process.state();
                    if (client.value("running", false) && client.value("world_loaded", false)) {
                        pid = client_process.pid;
                        for (auto& [peer, c] : protocol.connections) {
                            if (c.phase != "joined" || client.value("world_loaded_at",0.0)<c.handshake_time || c.initialization_failed || c.stages.contains(steps.back())) continue;
                            auto port = unsigned(std::stoul(peer.substr(peer.find(':') + 1)));
                            if (!owns_udp_port(pid, port)) continue;
                            connection_id = c.id;
                            if (!c.initialization_started) c.initialization_started = mono_time();
                            if (mono_time() - c.initialization_started > 180) {
                                c.initialization_failed = true;
                                c.initialization_status = "Initialization blocked";
                                event("initialization_failed", {{"service", "world"}, {"connection_id", c.id}, {"reason", c.initialization_error}});
                                connection_id.clear();
                                break;
                            }
                            if (c.actors.empty()) step = "bootstrap";
                            else for (const auto& candidate : steps) if (!c.stages.contains(candidate)) { step = candidate; break; }
                            c.initialization_status = "Initializing: " + step;
                            break;
                        }
                    }
                }
            }
            if (!connection_id.empty() && !step.empty()) {
                double observed = snapshot.is_object() && snapshot.contains("client_proof") ? snapshot["client_proof"].value("observed_at", 0.0) : 0;
                double full_observed = snapshot.is_object() ? snapshot.value("full_inspection_observed_at", observed) : 0;
                // Keep inspection off the UDP thread. The stage rechecks current identities, fields and values before dispatch.
                if (step == "bootstrap") {
                    ProcessReader reader(pid, config.at("client_exe").get<std::string>(), config.at("client_sha256"));
                    std::lock_guard lock(mutex);
                    attached = reader.proof();
                } else if (inspected_pid != pid || wall_time() - full_observed > 8) {
                    double inspection_started = mono_time();
                    snapshot = inspect_client(pid, config.at("client_exe").get<std::string>(), config.at("client_sha256"));
                    inspected_pid = pid;
                    write_file(root / "data/client-inspection.json", snapshot.dump(2));
                    std::lock_guard lock(mutex);
                    attached = snapshot.at("client_proof");
                    attached["inspection_errors"] = snapshot.at("errors").size();
                    event("initialization_inspection_completed", {{"connection_id", connection_id}, {"stage", step}, {"duration_ms", (mono_time()-inspection_started)*1000.}, {"bytes_read", snapshot.at("bytes_read")}});
                }
                if (step != "bootstrap") {
                    std::map<std::string,Guid> actors;
                    {std::lock_guard lock(mutex);for(auto& [peer,c]:protocol.connections)if(c.id==connection_id)actors=c.actors;}
                    ProcessReader reader(pid, config.at("client_exe").get<std::string>(), config.at("client_sha256"));
                    try {snapshot=refresh_actor_matches(reader,snapshot,actors);} catch(const std::exception& e){
                        std::string reason=e.what();
                        if(reason.find("lifetime changed")!=std::string::npos||reason.find("connection changed")!=std::string::npos||reason.find("GUID cache changed")!=std::string::npos||reason.find("Evidence process identity")!=std::string::npos)inspected_pid=0;
                        throw;
                    }
                    write_file(root/"data/client-inspection.json",snapshot.dump(2));
                    std::lock_guard lock(mutex);attached=snapshot.at("client_proof");attached["inspection_errors"]=snapshot.at("errors").size();
                }
                if (stopping) break;
                if (step == "WinsteadCollisionAdmitted") {
                    control({{"action", "admit_winstead_collision"}, {"connection_id", connection_id},
                             {"pid", pid}, {"created_filetime", snapshot.at("client_proof").at("process_created_filetime")}});
                } else {
                    stage({{"connection_id", connection_id}, {"stage", step}});
                }
                progressed = true;
                std::lock_guard lock(mutex);
                for (auto& [peer, c] : protocol.connections) if (c.id == connection_id) {
                    c.initialization_error.clear();
                    event("initialization_step_completed", {{"connection_id", c.id}, {"stage", step}, {"duration_ms", (mono_time()-attempt_started)*1000.}, {"since_initialization_ms", (mono_time()-c.initialization_started)*1000.}});
                    if (step == "PrepareMovement") {
                        c.initialization_status = "Character initialized; selected name, PlayerState, possession, HUD, BeginPlay and stats verified";
                        event("character_initialized", {{"service", "world"}, {"connection_id", c.id}, {"pid", pid}, {"movement_verified", false}});
                    }
                    if (step == "WorldReady") {
                        c.initialization_status = "Character and world initialized";
                        event("world_initialized", {{"service", "world"}, {"connection_id", c.id}, {"pid", pid},
                                                    {"winstead_floor_loaded_and_collision_admitted", with_winstead_floor}, {"native_input_release_verified", true}, {"movement_verified", false}});
                    }
                }
            }
        } catch (const std::exception& error) {
            std::lock_guard lock(mutex);
            for (auto& [peer, c] : protocol.connections) if (c.id == connection_id) {
                if (c.initialization_error != error.what()) event("initialization_waiting", {{"service", "world"}, {"connection_id", c.id}, {"stage", step}, {"reason", error.what()}});
                c.initialization_error = error.what();
            }
        }
        // Advance immediately after successful work; only unmet native prerequisites need polling.
        if (!progressed) std::this_thread::sleep_for(std::chrono::milliseconds(connection_id.empty() ? 100 : 25));
    }
}
}
