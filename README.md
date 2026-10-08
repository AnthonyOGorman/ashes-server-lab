<div align="center">

# Ashes Server Lab

**A small beginning for a very big world.**

Ashes Server Lab is an experimental open-source **Ashes of Creation private server / server emulator** written in **C++20**.
It supports local Verra exploration, movement, flight and live browser tools, with substantial bugs and missing systems. This independent server-emulation and reverse-engineering lab is a contributor starting point, not a complete MMORPG server.

![C++20](https://img.shields.io/badge/C%2B%2B-20-00599C?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%20x64-0078D4?style=flat-square)
![Status](https://img.shields.io/badge/status-very%20experimental-orange?style=flat-square)
![License](https://img.shields.io/badge/code%20license-MIT-green?style=flat-square)

**[Project website](https://anthonyogorman.github.io/ashes-server-lab/)** · **[Get started](#get-started)** · **[FAQ](docs/FAQ.md)** · **[Live demo](#see-it-running)** · **[What works](#what-works-today)** · **[Help build it](CONTRIBUTING.md)**

</div>

> **Bring your own client.** This repository contains lab source and interoperability definitions. It does not include the game, extracted terrain, an Unreal SDK dump, Epic's EOS SDK, or Oodle. The GIFs show a separately installed client.

> **Development paused, 2026-10-08.** The latest server, client-testing bridge, research scripts and unfinished work are saved in this source checkpoint. See the [pause handoff](docs/PAUSED_DEVELOPMENT.md) for verified results, pending work and local evidence locations.

## Why this exists

This is an **AI-generated “one-shot” prototype**, followed by iterative debugging and a lot of checking against one real client build. It is very buggy. The goal was to get a character into the world, moving over terrain, and leave a useful starting point for someone who wants to invest more time, skill, and tokens in developing a private server.

The motivation is simple: players should have a chance to explore the world they cared about. Development was [reported to have halted in early 2026](https://www.pcgamer.com/games/mmo/2-days-after-promising-it-was-still-worthy-of-your-investment-the-most-successful-kickstarter-mmo-ever-was-canceled-and-its-team-laid-off-the-developers-and-staff-acted-in-good-faith-and-deserved-better/). This is an independent community experiment, with no affiliation with or support from Intrepid Studios.

There is **no actual combat or MMORPG gameplay here**. Think of it as an exploration sandbox and a head start for contributors, with the useful work and the rough edges both visible.

## See it running

These previews come from player-recorded sessions in the real client and Web UI.

### In-game exploration

![Exploring the world in the locally connected client](docs/media/exploration.gif)

*Explore Verra with the locally connected character, including movement, jumping and flight.*

[View the full exploration GIF](docs/media/exploration-full.gif)

### Live Web UI

![Live server collision view and moving player](docs/media/live-world.gif)

*The live viewer follows the connected player over server terrain. Cyan is landscape terrain; amber is the local collision wireframe. Coordinates, movement state and the player marker update as the character moves.*

[View the full live-view GIF](docs/media/live-world-full.gif)

Each inline preview is an eight-second excerpt played at the original speed. Full-length GIFs preserve the complete 30-second exploration and 23-second Web UI recordings, with fewer frames and a smaller image to keep downloads manageable. The repository contains GIFs only; audio, recording metadata and original videos are excluded.

The recorded lab includes an older, incomplete prop cache. **The repository defaults to terrain-only collision.** Buildings and scenery visible in the client, or amber wireframes in the recording, are not evidence of complete server prop collision. No geometry from that local prop cache is distributed. See [media notes](docs/media/README.md).

## What works today

| Area | Current state |
| --- | --- |
| Local connection | Native C++ launcher tether, lobby, world handshake and one local account |
| Character | Local character records, actor initialization, possession, HUD and movement animation observed in the supported client |
| Exploration | Basic movement and jumping, configurable speed, collision/gravity toggles, flight altitude controls |
| Terrain | Offline extraction from your own archives: 2,669 Verra heightfields, including 82 rotated components, plus one warped landscape collision mesh |
| Live tools | Browser dashboard, interactive 3D terrain view, player trails, packet/event inspection and SQLite logs |
| Runtime | C++20 server and locally built EOS compatibility shim; Python and C# are offline setup tools |
| Combat / NPCs / quests | Not implemented |
| Production multiplayer | Not validated; current evidence is one locally connected player |

### Known rough edges

- **Walking pushback/jitter persists.** Client prediction and server simulation still disagree. Flying showed less pushback in the current session.
- **The period (`.`) walk toggle can stop server movement handling** until toggled back. Shift/sprint behavior needs investigation. Use normal movement keys for now.
- Speed updates reach the connected character and keep its animation running, but they do not solve prediction differences.
- Terrain collision is implemented; buildings, rocks, foliage, dynamic objects, water behavior and other gameplay collision are not comprehensively implemented.
- Initialization can fail or time out. The UI shows evidence and errors; reconnecting may be necessary.
- Compatibility depends on native offsets, schemas and byte ranges for one exact client. Supporting another build requires real investigation.
- Some code is dense and AI-generated. Passing tests is not a claim of protocol completeness or production readiness.

## Supported client

Verified on **2026-10-07** from the installed Steam manifest, executable metadata, executable SHA-256 and a live session:

| Identifier | Value |
| --- | --- |
| Steam App ID | `4124950` |
| Steam Build ID | **`21564631`** |
| Executable version | **`AOC-CL-438018`** |
| Unreal Engine version | `5.6.0-438018` |
| Depot / manifest | `4124951` / `5983602515922551495` |
| Executable SHA-256 | `4f1cd43ceeb89190f048734efd4d63152b9f8e11fa31fc41093b0d90f4a1cd43` |

This matched Steam's public branch in the [SteamDB depot listing](https://steamdb.info/app/4124950/depots/) when checked. **“Latest Steam client” is not a compatibility guarantee.** The setup and launcher reject a different executable hash. Supply your own matching installation; no client download is provided.

## Get started

### 1. Install the build tools

Use Windows x64. You need:

- **Visual Studio 2022**, Desktop development with C++, a Windows SDK and the C++ CMake tools. [Microsoft's CMake setup documentation](https://learn.microsoft.com/en-us/cpp/build/cmake-projects-in-visual-studio?view=msvc-170).
- **[MSYS2](https://www.msys2.org/)** for the dependency DLLs. The server itself is compiled with MSVC.
- **Python 3.10+** and NumPy for offline collision decoding.
- **[.NET 10 SDK](https://dotnet.microsoft.com/en-us/download/dotnet/10.0)** for the offline archive extractor.
- Your matching client installation and your own compatible Windows x64 **`oodle-data-shared.dll`**, for archive decompression. Supply this from an installation/tool you are entitled to use. It is not included.

In an MSYS2 terminal, install the MINGW64 dependency packages:

```sh
pacman -S --needed mingw-w64-x86_64-nghttp2 mingw-w64-x86_64-sqlite3 mingw-w64-x86_64-openssl mingw-w64-x86_64-gcc-libs
```

In PowerShell, from this repository's root:

```powershell
python -m pip install numpy
powershell -NoProfile -ExecutionPolicy Bypass -File .\CPP\tools\Build-CPP.ps1 -Configuration Release
```

The build creates the MSVC import libraries from your dependency DLLs, builds the native targets, copies their runtime dependencies beside the executables, and runs the source-only tests. The default dependency directory is `C:\msys64\mingw64\bin`; pass `-DependencyBin 'D:\msys64\mingw64\bin'` if yours differs. A fresh build does not require the game or extracted terrain.

### 2. Prepare your own client

Close the game first. Replace the example path below with the installation directory containing `Game\AOC`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\CPP\tools\Configure-Lab.ps1 `
  -ClientRoot 'D:\SteamLibrary\steamapps\common\Ashes of Creation' -InstallLocalEOS
```

This verifies the executable, generates nine reviewed code ranges from **your own executable**, writes the ignored `CPP/config/backend.json`, backs up the matching original EOS library under ignored `CPP/data/client-backup/`, and replaces that client's EOS library slot with the **locally built** `LocalEOSConnect.dll`.

The shim supplies a minimal local account/Connect interface. It does not connect to Epic services or implement production authentication. The installer refuses an unexpected EOS library. A separate copy of your client can be used if you prefer to keep the Steam installation untouched.

To restore the original library later, close the client and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\CPP\tools\Configure-Lab.ps1 `
  -ClientRoot 'D:\SteamLibrary\steamapps\common\Ashes of Creation' -RestoreOriginalEOS
```

Keep the backup until you have restored the original library. After rebuilding the shim, run the installer again; restore the previous original first if the installer reports an unexpected existing shim.

### 3. Generate terrain locally

The extractor reads the installed IoStore archives. **You do not need to visit the world as a character, or even run the client.** Build-matched terrain type definitions and observed class-default collision settings are included; actual terrain is generated privately from your own files.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\CPP\tools\Export-Terrain.ps1 `
  -OodleLibrary 'D:\YourTools\oodle-data-shared.dll'
```

This restores pinned parser packages from NuGet, builds the extractor, scans Verra heightfields and its warped collision mesh, checks archived collision overrides, decodes the cooked Chaos buffers and validates the result with the native C++ consumer. Archive scanning takes time and uses memory/disk space. Output stays under ignored `CPP/data/terrain-offline/`.

The decoder preserves transforms, rotated tiles, holes and sample quantization. Unknown collision overrides fail admission. The default active cache covers **Verra landscape terrain only**. Other installed maps are separate because their coordinates can overlap; see [terrain details](docs/TERRAIN.md).

### 4. Click to play

Double-click **`Start C++ Client.cmd`** at the repository root. It starts the native backend if needed, starts the local services, launches the game visibly on the normal Windows desktop, and opens:

```text
http://127.0.0.1:8865/
```

In the game, select **Ashes C++ Lab**, select/create a character, and press **Play**. The dashboard opens the lobby flow rather than launching a map directly, so character initialization and the HUD can complete.

Use the dashboard to change speed while connected. Start near **600 cm/s**. **Fly** disables gravity and collision; the altitude buttons move you up/down 10 metres. **Normal movement** restores both toggles. The `.`, Shift and prediction issues above remain open.

If you only want the backend in a terminal:

```powershell
.\CPP\build\msvc\Release\ashes_lab.exe --root .\CPP --start-services
```

| Service | Default address |
| --- | --- |
| Web dashboard | `http://127.0.0.1:8865/` |
| Live 3D view | `http://127.0.0.1:8865/world.html` |
| Lobby | TCP `127.0.0.1:16051` |
| World | UDP `127.0.0.1:18089` |
| Launcher tether | TCP `127.0.0.1:18090` |

Services bind to loopback. This package is a local lab; hosting a public server requires substantial additional work.

### Troubleshooting

- **Build cannot find Visual Studio/CMake:** install the 2022 C++ workload, Windows SDK and C++ CMake tools. The build script deliberately selects Visual Studio 2022.
- **Missing dependency DLL:** use the MINGW64 packages above and point `-DependencyBin` at their `mingw64/bin` directory. Do not mix UCRT64 DLLs with these import libraries.
- **Unsupported client or EOS hash:** use the exact client above. Restore the original EOS slot before installing a newly built shim; do not bypass the hash check.
- **Terrain missing / blank live view:** finish Export-Terrain, then restart the lab or click Reload collision cache. A full cache can take time to load at startup. The live view needs a joined player to centre on.
- **Client audible but invisible:** use this launcher, which selects `winsta0\default` and a normal visible game window. Close any previously running hidden instance first.
- **World visible but no character/HUD:** connect through the lobby, select the world and press Play. Check initialization/readback errors on the dashboard; reconnect if initialization timed out.
- **Pushback or frozen walking:** see the known issues. Normal movement keys and flight are the current exploration paths; the period-key walk toggle and prediction still need work.

## Develop from here

```text
CPP/src/             Native lobby, protocol, movement, collision and client initialization
CPP/include/ashes/   Native interfaces and types
CPP/native/          Local EOS compatibility shim source
CPP/web/             Dashboard and dependency-free 3D wireframe renderer
CPP/config/          Example configuration and build-matched interoperability definitions
CPP/tools/           Build, client setup and offline terrain extraction
CPP/tests/           Source-only checks and optional local terrain validation
docs/                Architecture, terrain, roadmap, media and third-party notices
```

Read [the architecture](docs/ARCHITECTURE.md), [the contributor guide](CONTRIBUTING.md) and [the roadmap](docs/ROADMAP.md). The most useful next work is reproducible movement/prediction evidence, the walk/run/sprint flags, initialization reliability, and a maintainable protocol implementation. Large gameplay features come after that foundation.

## Validation and scope

The packaged native source-only build passes **86 checks** covering protocol byte parity, protobuf round trips, time budgeting/rollover, movement settings, flight, capsule-wall contacts, stat updates and correction cadence. The local EOS shim passes **9 ABI/behavior tests**. The packaged offline setup completed end to end with **11,452 native terrain checks passed**. Terrain checks are registered only after local data is generated when CMake is configured; the executable can also be run directly.

The original local lab passed **12,071 terrain checks** with two extra runtime reference tiles, plus **487 earlier checks** including 101 terrain-dependent baseline movement steps. Those private reference tiles are deliberately not distributed. The public terrain suite validates every loaded heightfield, holes, rotations, warped-mesh floors and sweeps, reload behavior and collision admission; its check count differs without private references.

The recordings demonstrate a real single-player local session with possession, HUD and animation. They do not demonstrate combat, complete prop collision, production multiplayer or full native movement parity. See [verification notes](docs/VERIFICATION.md).

## License and contents

Original lab code is provided under the [MIT license](LICENSE). Third-party headers and dependencies retain their own licenses: [notices](docs/THIRD_PARTY.md). Game names, client-rendered imagery and game content belong to their respective owners and are not covered by this code license. Do not contribute client binaries, extracted game assets, account data or proprietary SDK libraries.

If you build on this, please share reproducible fixes and measured results. The aim is to give the next person a working foothold.
