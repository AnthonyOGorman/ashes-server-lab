# Ashes Server Lab roadmap

These are research and implementation priorities for Ashes Server Lab, the experimental Ashes of Creation server-emulation project. This is an ordered list of useful directions, not a delivery schedule.

Development is paused as of **2026-10-08**. The checkpoint includes improved controlled walking, automatic Winstead platform streaming and collision admission, verified character name/resource bars, loading input gates and a stationary jump/gravity fix. DLL login/Play/movement automation is available in the configured testing workspace. See [verification](VERIFICATION.md) and the [pause handoff](PAUSED_DEVELOPMENT.md). The work below remains pending.

## Stabilize exploration

1. Extend the stationary jump fix to moving jumps, horizontal air control, braking, slopes, step-up and landing. Resolve remaining walking jitter with matched input/time/position traces.
2. Verify live Shift sprint activation, gait/speed and stamina consumption. The reviewed adapter supports Shift, but its fixture is not live sprint proof. Resolve the period-key walk toggle.
3. Improve initialization recovery and visible entry time while preserving current world/pawn/floor/presentation gates. The native 22-second loading-screen hold remains unresolved.
4. Cover longer sessions, timestamp wraparound, reconnects, lower frame rates and multiple local clients.

## Improve world fidelity

1. Extend the verified Winstead platform foundation to real settlement content and live tier transitions across 0–6 (Metropolis), with matching collision/readiness before unlocking input. Resolve empty saved service selections at tiers 5/6 instead of treating metadata as a populated city.
2. Implement reliable static-prop extraction and transforms, including collision channels/responses, complex/simple selection and unsupported shape admission.
3. Study water, swimming, movement bases and streaming boundaries beyond the tested platform seam.
4. Add explicit separate-map selection and collision admission before attempting travel.

## Make the foundation maintainable

1. Refactor dense generated code into documented stages and protocol types.
2. Add a build-profile layer for offsets, schemas and evidence. New profiles need actual native verification.
3. Add CI for source-only synthetic checks and offline format fixtures that contain no game assets.
4. Improve deterministic replay and sanitized bug-report export.

## Only then expand gameplay

NPCs, combat, inventory, abilities, quests, progression, persistence, social systems and safe public hosting require substantial research and implementation. Nothing in the current demo establishes those systems. Start with a small, verified vertical slice.
