# C++ movement implementation / client research checkpoint

2026-10-07. Implementation owns live `CPP/src`, `include`, tests and server documentation. Client research owns `client-research`. No applicable AGENTS.md was found in the workspace/CPP or workspace ancestors. The workspace has no Git repository; pre-change files are saved under `CPP/runs/movement-compatibility-20261007/before`.

## Confirmed audit findings and implemented changes

- Packed move decoder already consumes four custom sign bits after baseline fields. Simulation previously ignored them. Restore X/Y with positive-bit precedence (native RVA 0x63e7a80); retain separate acceleration.
- Simulation previously rejected every compressed flag except 0 and 1. Support jump 0x01, walk request 0x10 and sprint request 0x20; explicitly refuse crouch, mantle and unreviewed bits. Sender and receiver are now linked statically to the same mask globals. Initialization and speed synchronization now read the native globals and require effective masks 0x10/20/40, exposing runtime_masks_verified. Exercising this readback on a fresh client remains pending.
- Ground direction classification uses the exact promoted-float epsilon, pure lateral first, then backward. Read effective instance walk/run triplets through reflected property metadata at initialization and speed synchronization. Preserve synchronized forward run speed / existing MoveSpeedMult FastArray update.
- Forward-stat-enabled walk/run use the same existing synchronized forward stat branch. Backward-stat-enabled speed is unresolved and retains the previous scalar model with explicit telemetry. All base-ratio branches assume existing speed synchronization's common modifier model; full effects/caps/material behavior remains unimplemented.
- Traverse packed moves old/pending/new instead of sorting raw timestamps. Permit bounded rollover on pending/new; ignore redundant large-gap moves without replacing the newest clock. These retain existing reset/budget approximations, not a claim of complete engine timing equivalence.
- Per-move comparison records restored input, flags, request state, speed source, effective cap, dt/steps/budget, before/after state, reported position/mode/rotation and prediction-error vector. Keep ack/correction choice and the existing 10 cm position threshold.

## Focused client facts needed

| Fact | Native lead | Concrete implementation blocked |
| --- | --- | --- |
| Sender flags and live global masks | saved-move GetCompressedFlags; receiver 0x5ece600; globals 0xd378c7c/80/84 | Static sender/receiver defaults and engine jump/crouch linked; runtime guard implemented, fresh client execution pending |
| MoveSpeedMult consumer / lateral modifiers | 0x5ea5370 owner CD0 -> 0x6b3cdc0, character +0x13a0; OnMoveSpeedMultUpdated | OnMoveSpeedMultUpdated 0x6b527c0 now proves CD0 cached multiplier; resolve remaining caps/effects/material modifiers |
| Backward speed stat identity/value | 0x5ea4b90 movement +0x10d0/+0x10d8 | Replace explicit scalar approximation on backward stat branch |
| Sprint effective modifier and allowed/actual gait transition | 0x6c11030, 0x6c003d0; SprintSpeedModifier character +0x13f8 | Implement sprint speed without assigning constructor MaxSprintSpeed=750 |
| CalcVelocity/ground/falling order and native substeps | simulation 0x3de7ce0 and descendants; limits +0x430/+0x434 | Fix earliest integration divergence, overspeed/braking, falling control and subdivision |
| Reset/defer/container details | 0x5ec20b0, 0x3dffa90, 0x3de2340 | Replace bounded local clock/reset approximation with engine behavior |
| Correction error manager / wrapper identity | 0x5ec1b30, 0x5ead530 | Exact response cadence/policy/reliable route; snapshot +0x1358 (not SDK +0x1378) |

## Verification status

Release build and all three suites passed: 487 core checks, 83 new movement checks and 12,071 terrain checks. Final Release all three suites and Debug core/movement suites passed with the runtime-mask guard and all 83 movement checks. A dedicated C++ headless backend passed 22 network integration and 9 movement API checks; full terrain loaded without errors, saved flight settings were restored, and only that created backend was stopped. A read-only trace analyzer passed 5 synthetic checks. No C++ backend responded on port 8865 and no current lab/game process was listed at the initial read-only check. No live client acceptance, walking pushback or sprint compatibility result is claimed. Full collision order, gravity-relative capsule/slope handling, steps/depenetration/moving bases and static prop coverage remain incomplete.

## Native follow-up incorporated

Research supplied 21 additional pseudocode outputs and a 12-check/49-snapshot static verification. `OnMoveSpeedMultUpdated` (0x6b527c0) writes the stat result to owner +0x13a0, read by CD0 (0x6b3cdc0); this confirms the common cached multiplier on lateral speed too. Saved-move allocator/table and GetCompressedFlags (0x5ea46c0) share receiver globals; base flags are jump 0x01/crouch 0x02.

`CalcVelocity` override 0x5e9aa10 / acceleration fragment 0x5e9b311 and IsExceedingMaxSpeed leaf 0x3e4ebe0 bind the overspeed comparison and post-braking cap. C++ now retains gradual overspeed decay and applies the current-speed acceleration cap with float narrowing. Braking 0x5e95e40 applies the 10 cm/s stop threshold only with deceleration. Full requested movement, target velocity, character-dependent braking multipliers and PhysWalking/PhysFalling ordering are still unimplemented.

## Next dedicated client session

The later session is recorded in [character-movement-followup.md](character-movement-followup.md). It verified live mask/profile readback, selected character identity, both PlayerState links, nameplate and current/max health/mana/stamina. The C++ retry path omitted the frozen sender's retry-sequence guard; restoring it allowed controller initialization to complete. A subsequent dashboard packet-count scan was measured holding the movement lock for roughly half a second and has been replaced with a persisted maintained total. Tests now include 102 movement checks, 25 network checks, nine movement API checks and six isolated packet-counter checks, alongside the original 487 core/12,071 terrain checks.

At the user's explicit request, the client-testing chat owns the existing DLL's calibrated login/Play and bounded movement input. Each window binds the exact PID/process creation time, uses fresh screenshot checkpoints, releases keys afterward and retains the existing foreground guards. Login/Play and two post-fix W pulses were automated; the second still fell at the terrain gap. Supported-spawn recovery was independently verified and input is now off. The research chat owns read-only settlement analysis and no inputs. Full-route acceptance, sprint grants and effective physical speed/cost remain open. Future coordinated runs use the reviewed DLL runners. The older manual steps below describe the original test plan, rather than requiring the user to repeat login/input for each current test.

1. Launch through `Start C++ Client.cmd`, join the lab and select Play. Verify fresh PID/creation time/executable hash, UDP port owner, current pawn GUID, possession/HUD/BeginPlay/stats readback and the new live directional profile.
2. Switch to Normal movement (saved user setting was flight), then capture start/stop, W/S/A/D, both diagonal directions, period-key walk/run transitions, jump/land and Shift request/release. Restore the user's chosen settings afterward.
3. Compare per-move equal-time client native snapshots to server telemetry; inspect the first mismatch before any tolerance tuning. Record corrections/magnitude, mode/floor/velocity and input/gait transitions. Repeat flight control as a preserved-behavior check.
4. Use evidence to resolve backward stats/sprint, simulation subdivision/falling and collision order. Full jitter-free movement and replay remain unproven.
