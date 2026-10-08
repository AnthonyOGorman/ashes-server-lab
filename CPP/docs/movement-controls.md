# Web movement controls



The dashboard Movement panel controls native server movement for all current players and future connections. Settings persist in `data/movement-settings.json`.



- Speed: 10–10000 centimetres per second; normal forward run default 600; walk/lateral/backward caps use the current possessed movement instance when the corresponding base-field branch applies.

- Collision: capsule sweeps and terrain support; disabled permits passing through static geometry.

- Gravity: normal falling when enabled; disabled uses flying movement mode 5, brakes on released input, and maintains altitude.

- Fly: speed at least 1320 cm/s, collision off, gravity off.

- Rise / Descend: moves the player 10 metres vertically in flight, respecting collision if enabled, and sends a native movement correction immediately. Game movement keys steer horizontally; vertical movement inputs are also accepted in flight.

- Normal movement: 600 cm/s, collision on, gravity on. The player falls from their current position to supported terrain.



Apply settings saves the complete validated settings atomically with respect to server movement. Invalid settings leave the active settings unchanged. Flight altitude controls are refused with gravity enabled or without a joined player. Frozen collision coverage remains incomplete. The server synchronizes the accepted existing MoveSpeedMult stat to the requested forward run speed, using the live MaxRunSpeed as its base, and verifies native FastArray readback. Only the existing speed item is updated. Matching moves are acknowledged; corrections are retained for position errors or movement-mode mismatch. Flight and incomplete collision coverage can still require corrections.



API: POST `/api/control` with action `movement_settings` and `settings` containing `speed`, `collision_enabled`, `gravity_enabled`; action `flight_altitude` takes a `delta` in centimetres (maximum absolute 10000). Current settings appear in `/api/state` and each `/api/world-view` player.



Native sessions read current walking friction, walking/flying braking, braking substep and factor from the possessed character, and flight drag from its verified physics-volume weak reference. The server applies turn friction and braking rather than treating every input release as 8192 cm/s² deceleration. Ground spacing uses the native floor-distance midpoint of 2.15 cm. Native sessions now use the reviewed float timestamp and discrepancy-resolution path with live configuration and a shared packet processing clock. The historical offline fixture path retains its arrival budget. Small corrections are spaced by at least 100 ms, with immediate corrections for large errors or mode changes. Captured baseline parity retains its historical simulation profile.


## Movement compatibility changes (2026-10-07)

The C++ simulator now accepts the traced jump (0x01), walk request (0x10) and sprint request (0x20) combinations. The former `flags == 0 || flags == 1` guard refused the walk-toggle flag. Crouch (0x02), mantle (0x40), reserved and unreviewed custom flags receive explicit refusals because their simulation is unsupported. Sender and receiver share the same masks in the exact executable's static evidence; initialization and speed synchronization now read the live globals and require the supported effective masks. `ground_speed_profile.runtime_masks_verified` records successful readback. This path still needs a fresh real-client session.

The existing packed decoder already read the four custom axis sign bits. It now also exposes the restored input pair, and simulation consumes that pair separately from acceleration. Positive wins when both signs are set. Pure lateral uses abs(X) <= double(.0001f) and abs(Y) > double(.0001f); diagonals use the forward/backward branch. Native initialization and speed synchronization read current reflected walk/run forward, lateral and backward fields and stat-selection flags. Field-selected speeds share the existing synchronized MoveSpeedMult model. Forward stat selection retains the existing synchronized speed for both walk and run; backward stat selection retains the previous scalar approximation and labels it `unresolved_backward_stat`. Dynamic owner caps, effects and physical-material modifiers still need full resolution.

Sprint flags preserve the request and allow simulation to continue. Effective sprint eligibility, allowed/actual gait transitions and the speed modifier consumer remain unresolved. The server does not assign the constructor's MaxSprintSpeed=750 as an effective sprint cap. Telemetry reports `sprint_speed_resolved: false`.

Native velocity integration now uses the client helper's strict squared-speed comparison, including its float-product 1.01 tolerance. After braking/drag, acceleration uses the current speed cap when still overspeed; it no longer immediately snaps run-to-walk overspeed to the lower nominal cap. Released input does not force an extra final nominal-speed clamp. The 10 cm/s braking stop threshold requires active deceleration, and nonzero small acceleration remains input. Target/override velocity, requested movement, root motion and character-dependent braking modifiers remain unsupported branches.

Packed moves are processed old/pending/new instead of sorting numeric timestamps. Native timestamps use the reviewed 240-second reset validator and cooldown, preserve an active resolution override across reset and use native iteration/substep rules. First-move seeding and the 60 Hz elapsed processing clock remain lab approximations. The wall-time budget and uniform subdivision described by the earlier checkpoint apply to historical offline fixtures.

Acknowledgment/correction authority is retained: the existing 10 cm position boundary, matching mode, synchronized speed and no discarded interval are required for a good-move acknowledgment. Existing correction cadence remains. No error allowance was widened. Native error-manager allowance/snapshot policy and reliable-wrapper selection remain to be implemented from fuller evidence.

## Comparison telemetry and next live check

Each `movement` event records timestamp/kind, compressed flags, separate acceleration and custom signs, restored direction, walk/sprint requests, effective cap/source, simulation interval/step count/budget, before/after position and velocity, reported position/mode/rotation, collision contacts and response. New moves include error magnitude/vector and speed synchronization state. `/api/world-view` includes `movement_comparison` and `ground_speed_profile`.

For one fresh connection, export the earliest recorded mismatch:

```powershell
python CPP/tools/analyze_movement_trace.py <fresh-connection-id> --output CPP/runs/<session>/movement-comparison.json
```

This report reads SQLite without changing the server. Bind the connection to the current PID/process lifetime, accepted pawn NetGUID and inspection/speed-readback events. A server comparison is not independent client acceptance or a client simulation oracle.

Release validation passed 487 existing checks (including 101 captured baseline steps), 83 focused synthetic/offline movement checks and 12,071 terrain checks. The C++ headless backend also passed 22 network integration and 9 movement API checks, with saved settings restored. Debug core/movement validation is recorded in the implementation run directory. Full collision equivalence is not established by terrain coverage or these tests.

The later character/timing follow-up verified native selected identity, PlayerState, possession, nameplate and resources. It also removed a measured half-second dashboard polling stall from the movement lock. A short DLL walk baseline passed, while broader walking acceptance and effective sprint behavior remain under investigation. Complete floor/step/slide/depenetration order, falling control, moving bases and replay remain partial. See [character-movement-followup.md](character-movement-followup.md) for current live evidence and limitations.

Implementation checkpoint and focused research gaps: [movement-research-collaboration.md](movement-research-collaboration.md). Build/test logs and pre-change snapshot: `CPP/runs/movement-compatibility-20261007/`.
