# Contributing

This is a small, very experimental exploration server. Contributions that turn observations into reliable behavior are welcome. AI-assisted work is fine; describe what you verified and where you still depend on an assumption.

## Start small

Build the source-only targets first, then configure your own matching client and generate terrain. The README has the exact sequence. Keep a separate client copy or the original EOS backup if you need to restore the game installation.

Useful first contributions include:

- Capture a minimal walking pushback reproduction with timestamps, inputs and server/client positions.
- Identify the period-key walk toggle and Shift/sprint flags; extend decoding and speed handling with real evidence.
- Improve initialization retry/error reporting without weakening executable identity or actor lifetime checks.
- Split the dense C++ implementation into readable, documented components.
- Add meaningful synthetic tests for unsupported shapes or timing edge cases.

See [the roadmap](docs/ROADMAP.md) for larger work.

## Reviewable changes

Describe the trigger, prior behavior and resulting behavior. Include the client build, build/test command, and whether you verified against a real client or only synthetic fixtures. Protocol or native-offset changes should include enough sanitized evidence to explain the mapping.

Run `CPP/tools/Build-CPP.ps1 -Configuration Release`. With locally generated terrain, also run `CPP/build/msvc/Release/ashes_terrain_tests.exe CPP`. Reconnect a matching client for initialization or movement changes and check the dashboard's readback evidence. Do not call transport ACKs proof that native state was accepted.

## Keep private files private

Do not commit game archives, collision buffers, executable fragments, downloaded proprietary DLLs, complete Unreal SDK dumps, live logs, saved profiles, session tokens, Steam account identifiers or machine-specific paths. `CPP/data/`, `CPP/config/backend.json`, profiles and builds are ignored. Screenshots should contain only the app/game being demonstrated.

Submit source, small synthetic fixtures, documentation and sanitized compatibility definitions. Update the known-issues list when behavior changes; keep demonstrations honest about coverage.
