# Contributing to Ashes Server Lab

Ashes Server Lab is a small, very experimental C++20 exploration server for Ashes of Creation. Contributions that turn observations into reliable behavior are welcome. AI-assisted work is fine; describe what you verified and where you still depend on an assumption.

## Start small

Build the source-only targets first, then configure your own matching client and generate terrain. The README has the exact sequence. Keep a separate client copy or the original EOS backup if you need to restore the game installation.

Useful first contributions include:

- Extend the verified stationary jump case to moving jumps, air control, slopes and landing; capture remaining walking jitter with matched timestamps, inputs and positions.
- Verify live Shift/sprint activation and owner-scoped stamina consumption; fixture key handling is not sprint proof. Resolve the period-key walk toggle.
- Extend the verified Winstead platform to real settlement tier transitions and matching collision/readiness.
- Improve initialization retry/error reporting without weakening executable identity or actor lifetime checks.
- Split the dense C++ implementation into readable, documented components.
- Add meaningful synthetic tests for unsupported shapes or timing edge cases.

See [the roadmap](docs/ROADMAP.md) for larger work.

Gameplay development is paused at the 2026-10-08 checkpoint. Review [the handoff](docs/PAUSED_DEVELOPMENT.md) and [verification](docs/VERIFICATION.md) before resuming research. Historical process identities, native pointers and input leases must not be reused as current evidence.

## Reviewable changes

Describe the trigger, prior behavior and resulting behavior. Include the client build, build/test command, and whether you verified against a real client or only synthetic fixtures. Protocol or native-offset changes should include enough sanitized evidence to explain the mapping.

Run `CPP/tools/Build-CPP.ps1 -Configuration Release`. With locally generated terrain, also run `CPP/build/msvc/Release/ashes_terrain_tests.exe CPP`. Reconnect a matching client for initialization or movement changes and check the dashboard's readback evidence. Do not call transport ACKs proof that native state was accepted.

## Keep private files private

Do not commit game archives, collision buffers, executable fragments, downloaded proprietary DLLs, complete Unreal SDK dumps, live logs, saved profiles, session tokens, Steam account identifiers or machine-specific paths. `CPP/data/`, `CPP/config/backend.json`, profiles and builds are ignored. Screenshots should contain only the app/game being demonstrated.

Submit source, small synthetic fixtures, documentation and sanitized compatibility definitions. Update the known-issues list when behavior changes; keep demonstrations honest about coverage.

## Documentation site

The static site is generated from the README and documentation Markdown. After editing a published source, regenerate and validate it before committing:

```powershell
python -m pip install -r tools/site/requirements.txt
python tools/site/build.py
python tools/site/build.py --check
```

Commit the updated Markdown and generated `docs/` outputs together. The documentation workflow rejects stale generated pages.
