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
    const std::vector<std::string> steps{
        "ClientSetHUD", "ClientRestart", "PawnAutonomous", "StatsComponentExport",
        "GameStateBeginPlay", "StatsGravity", "StatsSpeed", "ActivateMovement"
    };
    while (!stopping) {
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
                            if (c.phase != "joined" || client.value("world_loaded_at",0.0)<c.handshake_time || c.initialization_failed || c.stages.contains("ActivateMovement")) continue;
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
                // Keep inspection off the UDP thread. The stage rechecks current identities, fields and values before dispatch.
                if (inspected_pid != pid || wall_time() - observed > 8 || step == "ClientSetHUD") {
                    snapshot = inspect_client(pid, config.at("client_exe").get<std::string>(), config.at("client_sha256"));
                    inspected_pid = pid;
                    write_file(root / "data/client-inspection.json", snapshot.dump(2));
                    std::lock_guard lock(mutex);
                    attached = snapshot.at("client_proof");
                    attached["inspection_errors"] = snapshot.at("errors").size();
                }
                if (stopping) break;
                stage({{"connection_id", connection_id}, {"stage", step}});
                std::lock_guard lock(mutex);
                for (auto& [peer, c] : protocol.connections) if (c.id == connection_id) {
                    c.initialization_error.clear();
                    if (step == "ActivateMovement") {
                        c.initialization_status = "Character initialized; native possession, HUD, BeginPlay and stats verified";
                        event("character_initialized", {{"service", "world"}, {"connection_id", c.id}, {"pid", pid}, {"movement_verified", false}});
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
        for (int i = 0; i < 5 && !stopping; ++i) std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
}
}
