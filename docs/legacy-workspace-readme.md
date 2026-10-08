# Ashes Lab

A fresh local server and Windows client test workbench for the installed Ashes of Creation Steam client. It records local protocol exchanges, imports selected historical capture payloads, and runs calibrated game input scenarios with screenshots and explicit milestones.

**Current verified result (2026-10-06):** local EOS compatibility login succeeds. The installed client enters Verra and accepts the gameplay HUD, possession, PlayerState links and BeginPlay. The in-world character model and gameplay UI are visible. Fresh forward input reaches the server in decoded movement reports, but the observed position stays unchanged. The pawn appears below terrain; ground height and capsule clearance have not been validated. See `evidence/eos-local-character-ui-49892.png` and `evidence/eos-local-fresh-forward-input-49892.json`.

**Current goal:** establish a valid terrain-supported spawn and verify fresh input drives server-handled movement; then investigate and implement world collision with gravity. Acceptance criteria and the next investigation are recorded in `data/current-goal.json`. Character movement, supported spawn and collision/gravity are still unfinished.

## Start on Windows

Use a normal desktop PowerShell window. Launching the game from a restricted agent sandbox can fail when the game initializes its Windows graphics/event infrastructure; the dashboard and game must run in your desktop session.

```powershell
Set-Location -LiteralPath 'E:\Ashes Of Creation GPT'
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\Start-Lab.ps1
```

If the environment is already installed and activated, just run `Start-Lab.ps1`. Keep that terminal open, then open [the dashboard](http://127.0.0.1:8765).

The default client executable is:

```text
E:\Games\Steam Library\steamapps\common\Ashes of Creation\Game\AOC\Binaries\Win64\AOCClient-Win64-Shipping.exe
```

The lab uses extracted descriptors for this exact client build in `evidence/client_contracts.pb`. If you use a different game installation/build, update `GAME` in `lab/app.py` and regenerate the inventory/contracts before trusting compatibility:

```powershell
python tools\probe_client.py 'E:\Games\Steam Library\steamapps\common\Ashes of Creation\Game\AOC\Binaries\Win64\AOCClient-Win64-Shipping.exe' evidence
```

The dashboard listens at `127.0.0.1:8765`, the XClient gRPC service at `127.0.0.1:15051`, and the world UDP listener at `127.0.0.1:17089`. Launcher tether uses an automatically selected loopback UDP port. Dashboard controls start and stop these services. **Launch client** starts the required services automatically. Stop the client before stopping its services; Ctrl+C in the terminal shuts down the lab and its launched game process.

## Calibrate and run a scenario

1. In the dashboard, select **Launch client** and wait for the game window and realm list.
2. Under **Client screenshot**, select **Capture in 5s**, then put the launched game in the foreground within five seconds. The dashboard captures the game client area in physical pixels. Load the latest image after capture completes.
3. Under **Image click updates**, choose the **Enter realm** step. Click the intended realm-entry control in the captured image. Coordinates update that step in the scenario editor. Default coordinates are `-1,-1` and must be replaced from an actual screenshot.
4. For a world-entry experiment, also calibrate **Play** against its actual screen. Each button needs coordinates appropriate to the screen on which that step runs. Recalibrate after window size, resolution, or layout changes.
5. Check **Click positions calibrated**, then select **Save scenario**. Unsaved edits do not affect the runner.
6. Choose **Login sequence** to run only through the lobby assertion. Choose **Walk in world** to run the complete saved scenario, including world entry, spawn and movement assertions. Select **Run test**, then put the game in the foreground during the five-second countdown.

The foreground driver checks the exact launched process PID before input. It does not switch focus for you. Allowed keys are WASD, space, escape, enter, tab and the arrow keys; key holds and waits are bounded. **Cancel test** interrupts a running wait/key hold and performs input cleanup. A focus change blocks foreground input. If focus is lost during a hold, key releases are targeted to the original game window; global cleanup is deferred until the next tester action with the same game in the foreground.

The **Background (experimental)** driver runs locally without GPT computer use. It sends Windows messages only to the launched game's validated window and captures that window with `PrintWindow`; it does not move the desktop cursor, activate the game, or send global keyboard input. You can use other applications while testing. Keep the game restored: minimized windows are rejected. The installed client's rendered screenshots and Enter navigation have worked in live tests while another process retained foreground focus. Background mouse messages have not yet produced a realm selection, so full login and gameplay control in this mode remain under investigation. A sent input is not proof that the game acted on it.

The **Game process adapter (experimental)** driver adds a small local DLL to the exact hash-checked game process. During bounded input actions it supplies virtual cursor, key, focus and capture state through this executable's USER32 imports; it restores inactive state afterward and has a watchdog. In test `01180dc73b284b5b841172b3c59324b6`, Play produced a real local server request, Welcome and Verra load while another application retained foreground focus and the desktop cursor stayed unchanged. This establishes background Play activation for that test, not complete background gameplay. Screenshots and protocol assertions remain necessary. The source, fixture and manifest are in `native/input_adapter/`; calls through other modules or dynamic API lookups are outside its interception.

Visual checkpoints compare a saved screen region with a pinned PNG template before advancing. Each test preserves the template hash, screenshot, comparison score and protocol milestones. Use a stable control or label rather than an animated background. The runner can recognize screens and stop on a mismatch without an AI model viewing each frame; saved screenshots are available for diagnosing new or unexpected screens.

The default scenario waits for authentication, enters the realm, waits for lobby, selects Play, waits for accepted Welcome, world load and player spawn, then presses W and checks movement. Missing milestones time out rather than reporting success. Sending movement input or seeing changed pixels is insufficient: movement needs position and protocol evidence. Possession has been proved in one explicit experiment; automatic character initialization and walking are not yet implemented, so a complete walking test still stops at a missing assertion. The possession experiment currently requires separate actor/cache validation and is not automatically performed by this scenario.

Movement steps now require a valid read-only possessed-pawn sample before sending input, and preserve before/after samples plus a position comparison in the test directory. Samples bind the process lifetime, local controller, acknowledged pawn, exact network GUID and root component. A changed position is an observation; falling, teleporting or corrections can also move a pawn, so this comparison does not pass the walking assertion.

Use the **Character selection world entry** preset when already at the rendered lobby with LabExplorer available. It checks the character label and Play button before clicking, then requires new Welcome and Verra map-load observations from this attempt. World milestones reset on reconnect or a confirmed return to the lobby. This preset has passed one live retry after correcting a blank Play reference image; map completion alone does not prove the loading overlay cleared or the pawn became playable. Details are in `evidence/character_selection_world_entry_trial.md`.

Targeted Ghidra decompilation is saved under `evidence/decompiled/`, with the exact-client project in `evidence/ghidra-project/` and bounded analysis script `tools/ghidra/TargetDecompile.java`. The first crash investigation identified a null HUD receiver in the controller's UI/save path. This is separate from the missing PlayerState links; see the crash report before attributing other symptoms to that omission.

In the subsequent live trial, the correct HUD, acknowledged possession and AutonomousProxy pawn role were accepted. A bounded movement test still observed zero position change and no pawn movement RPC. Read-only inspection found pending pawn input and valid movement components, but the accepted GameState's `bReplicatedHasBegunPlay` remained false. See `evidence/hud_possession_movement_trial.md` and `evidence/movement_prerequisite_findings_56352.md`; walking and character appearance remain unverified.

## Packet evidence and captures

The packet table shows direction, channel, kind, raw hex and decoded fields. Select a packet to inspect it and save a label/note with an `observed`, `hypothesis` or `verified` confidence. Imported historical traffic is evidence of an old session, not proof of a successful current local test.

Wireshark's `tshark` is required for PCAP imports. The importer checks the PATH and the standard `C:\Program Files\Wireshark\tshark.exe` location. In the dashboard, enter an absolute `.pcap`/`.pcapng` path inside the supplied research folders and select **Import**. Import runs in the background and appears in run history.

For a standalone JSONL export:

```powershell
python tools\import_capture.py 'E:\Ashes Of Creation Wire Shark\general start up log in relm select walk around mount etc.pcapng' data\historical-game.jsonl
```

The importer scopes payloads to observed UDP prefixes `96760c50` (game) and `a55a02` (tether), plus selected loopback lab ports. It does not decrypt unrelated TLS or modify Wireshark preferences. Historical world traffic includes partly decoded replication, and the capture set does not provide successful decoded SessionReply responses. Protocol meanings must be established from client contracts, binary consumer evidence and new local experiments. New imports infer the client endpoint from its actual initial handshake; traffic before that observation keeps an unknown direction.

The binary analysis identified the exact session configuration key `ics_ping_client_config.json`; `ConfigJsonPing` is a log label. The client also consumes serialized `PlayerSessionState` through `SessionReply.data_map["player_session_state"]`. Evidence and instruction locations are recorded in `evidence/session_contract.json`, with the reproducible analyzer in `tools/analyze_session_contract.py`.

After a live Join, **Experimental controller bootstrap** sends freshly constructed object exports and a PlayerController creation bunch. It uses observed static object references and a new dynamic actor GUID. Each connection allows one attempt. It is an explicit experiment, and its transport acknowledgement alone does not prove a spawned player. The baseline run `runs/dd964e2e5f2d/` preserves the successful lobby-to-Verra flow without this experiment.

## Files and verification

`data/lab.sqlite` stores packet records, events, run history, annotations and local characters. `data/scenario.json` stores the editable scenario. Each client session has a directory under `runs/` with launch arguments, stdout/game logs, and test subdirectories containing `scenario.json`, `events.jsonl`, before/after PNG screenshots and `result.json`. `client-profile/` isolates the lab's client settings; `config/WindowsEngine.ini` is the local launch override.

Run protocol and tester checks with:

```powershell
python -m unittest discover -s tests -v
```

These tests cover protocol construction/parsing, lobby contracts, scenario gating, cancellation and evidence handling. They do not establish successful real-client world loading, pawn replication or movement. Those outcomes must be verified by running the installed game and inspecting the saved evidence.
