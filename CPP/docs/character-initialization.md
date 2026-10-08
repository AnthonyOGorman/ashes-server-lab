# Automatic character initialization

The C++ backend now runs the fixed initialization sequence for the game launched by this lab. A joined socket alone is insufficient: it also waits for the current client's Verra map-load log entry and verifies that the client's PID owns the UDP source port. Each connection initializes once.

World Login first consumes the lobby Play token to bind the selected character ID/name. The sequence is actor bootstrap, ClientSetHUD, ClientRestart, controller/pawn PlayerState links and readback, PawnAutonomous, CharacterInfo export, selected GUID/name and readback, StatsComponentExport, GameStateBeginPlay, StatsGravity, StatsSpeed, current/max health/mana/stamina and readback, then activation of native movement. The bootstrap creates controller channel 3, GameState channel 5, pawn channel 9 and PlayerState channel 39. HUD and restart use the live controller field maximum 1032; pawn movement uses 198. Gravity, speed and health/mana use stats field 6; stamina uses owner field 3, both with maximum 23. Resource amounts are explicit configurable lab defaults.

Read-only inspection binds the executable hash, process creation time, reflected classes, weak identities and accepted network GUIDs. Subsequent stages require live possession, current property/layout metadata, HUD acceptance, BeginPlay readback, component GUID acceptance and current stat state. BeginPlay also checks the reviewed Verra world, driver, WorldSettings and native code paths. Dispatch and packet acknowledgement are not treated as client acceptance.

Full object inspection runs on a separate worker; verified stage dispatch serializes with world state. The dashboard's world connections display the active stage and any refusal reason. Initialization is bounded to 180 seconds, and a blocked connection does not count as an online authoritative player. The configuration can disable automatic initialization with `"auto_initialize": false`.

This ports the fixed working character sequence from the frozen Python baseline. Complete collision export/refresh, appearance customization and all development tools remain separate migration work. Walking and jumping still require live verification against this backend.

The character/timing follow-up fixed a retry-sequence regression in the C++ sender, then verified both PlayerState links, selected LabExplorer GUID/name, HUD bars and all six resource getter caches in the live client. See [character-movement-followup.md](character-movement-followup.md) for the current movement and automation evidence, as well as the unresolved sprint/settlement content work.


During the 2026-10-07 terrain deployment, the first reopened client acknowledged the gravity-stat packet at the transport level but retained an empty stat proxy array. Initialization correctly waited for native readback, so it did not activate authoritative movement. Reopening that client once completed all stages and live speed synchronization. Record this as an unresolved intermittent initialization/readback issue; the terrain cache loaded and remained active throughout the retry.
