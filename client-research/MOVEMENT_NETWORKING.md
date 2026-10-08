# Movement, collision, and prediction compatibility

Research checkpoint: 2026-10-07. Scope: read and document the installed client; no server implementation or runtime client modification.

The client contains a custom `AoCCharacterMovement` implementation layered on Unreal character movement. This pass recovered its constructor/dispatch ownership, a custom direction serializer, received-move input restoration, speed selection and modifiers, compressed gait flags, parts of timestamp-based simulation, acknowledgment/correction dispatch, and a gravity-relative walkability test. This is enough to specify several concrete compatibility requirements. It does **not** yet establish an exact replacement server or demonstrate jitter-free movement.

All addresses here are RVAs in the installed `AOCClient-Win64-Shipping.exe`, preferred image base `0x140000000`, SHA256 `4f1cd43ceeb89190f048734efd4d63152b9f8e11fa31fc41093b0d90f4a1cd43`. Native instruction evidence takes precedence over SDK field names when they disagree. Generated SDK headers supply candidate names and layouts; they are not original game source and their complete build provenance is unresolved.

## Saved evidence and confidence

The [native movement map](<E:/Ashes Of Creation GPT/client-research/proofs/movement-native-map.json>) records constructor links, table targets, constant probes, and instruction snapshots. The [movement verification report](<E:/Ashes Of Creation GPT/client-research/proofs/movement-verification.json>) passes 12 evidence-consistency checks: executable identity, selected constructor and thunk instructions, selected virtual targets, the four one-bit calls, thresholds, mask initializers, the walk flag setter, 28 native fragment fingerprints, and all 70 requested pseudocode outputs. These checks bind static findings to this executable; they do not execute the game or compare against the official server.

Ghidra retains overlapping-global warnings in many outputs and a type-propagation warning in baseline move-copy routine `0x3dd0800`. Output presence and hash binding do not clear those warnings. Use the exact instruction snapshots to check claims involving inferred types; full baseline-copy semantics remain to be reviewed.

The broader [index verification](<E:/Ashes Of Creation GPT/client-research/verification.json>) also passed all 21 checks at 2026-10-07 12:54:58 UTC, including SQLite integrity and 625 saved table entries. That report checks structural consistency across research layers; it does not upgrade unreviewed pseudocode to understood behavior.

The [70-range manifest](<E:/Ashes Of Creation GPT/client-research/batches/movement-extended.tsv>) and [Ghidra transcript](<E:/Ashes Of Creation GPT/client-research/ghidra-movement.log>) preserve the focused passes. Pseudocode is saved in `decompiled/movement/`; manifests represent native ranges, not a claim of 70 fully understood logical functions. Compiler fragments and indirect calls still require review. Six selected targets lack indexed bounds and are reported separately in the native map; a small leaf getter was reviewed as raw instructions. Seven incremental bounded Ghidra passes completed, saved the isolated project, and exited. No broad decompilation queue was restarted for this movement pass. The earlier global coverage/catalog snapshots have not been regenerated and should not be interpreted as this pass's counts.

## Dispatch ownership

The movement class accessor `0x58d61d0` registers object callback `0x58d6570`, which reaches constructor `0x5e928b0`. That constructor calls the engine constructor and installs primary table `0xb110970` at the object start. The adjacent secondary table bounds an explicit scan of 441 primary entries. This establishes a constructor-installed table, not the current vptr of every runtime or Blueprint-derived character.

`BaseCharacter` accessor `0x5d75170` reaches callback `0x5d78360` and constructor `0x6b2b540`, which installs primary table `0xb741268`. `PlayerCharacter` accessor `0x5def450` reaches callback `0x5df8830` and constructor `0x6bee450`, which installs primary table `0xb7bf4e8`. Their speed-related dispatch targets corroborate the owner calls made by movement code.

| Movement primary-table byte offset | Target RVA | Reviewed role / naming limit |
| --- | --- | --- |
| `0x568` | `0x5ea5370` | GetMaxSpeed, linked through reflected engine thunk |
| `0x978` | `0x3de4f70` | IsWalkable, linked through reflected engine thunk |
| `0xa08`, `0xa18` | `0x3de5590`, `0x3de54f0` | K2_FindFloor / K2_ComputeFloorDist wrappers; underlying solver remains unresolved |
| `0xb48` | `0x5ec1b30` | Position-error decision candidate; formula below |
| `0xb58` | `0x5ead520` → `0x3de7ce0` | Trampoline into timestamp/delta/flags/acceleration movement path |
| `0xb60` | `0x5ece600` | Restore compressed flags into game movement state |
| `0xbc0` | `0x3dcf5a0` | ClientAckGoodMove, linked through reflected thunk |
| `0xbc8` | `0x5e9e420` | ClientAdjustPosition override, linked through reflected thunk |
| `0xbe8` | `0x5ec1f80` | Receive/defer a decoded move container |
| `0xbf0` | `0x5ec20b0` | Restore custom input and process an individual received move |
| `0xbf8` | `0x3dd0a90` | Dispatch decoded response to acknowledgment/correction paths |
| `0xcd8` | `0x5ea2150` | Movement-mode/walk-state base-speed selector |
| `0xd08` | `0x5ea0070` | Conditional deferred-server-move path |
| `0xd80` | `0x5ea4b90` | Direction and optional stat-backed speed selection |

An early neighboring callback lead (`0x58d6530` → `0x5e91b00`) was rejected as movement-constructor ownership evidence after checking the accessor's actual LEA target. Historical proof files for that lead are preserved; use the links in `movement-native-map.json` and the confirmed constructor snapshots.

## Forward/backward/sideways input

The cooked [input configuration](<E:/Ashes Of Creation GPT/client-research/INPUT_CONFIGURATION.md>) binds W/S/A/D to character movement actions and LeftShift to IA_Sprint. Those are asset declarations, not a measurement of a player's live remapped bindings. Native controller handlers `0x6ad89c0` and `0x6ad93a0` call filtering routine `0x6ad4670` and contain camera/control orientation, pawn, and vehicle branches. The complete transformation from action value to world acceleration is not yet resolved.

The character's `CurrentMovementInput` is a pair of doubles at `+0x1258/+0x1260`. Getter `0x5ea4700` copies these through `BaseCharacterOwner` at movement `+0x1300`. The speed predicates treat negative X as backward and classify pure sideways input when `abs(X) <= epsilon` and `abs(Y) > epsilon`. Diagonal input is therefore a distinct case; the pure-sideways test does not classify every input containing Y as strafing.

### Four custom direction bits

Custom move-data constructor `0x58d65e0` installs table `0xb110910`. Its copy routine `0x5e9e780` copies saved-move input at `+0x450/+0x458` into move data `+0x70/+0x78` after the baseline copy. Serializer `0x5ec10b0` serializes baseline movement fields and calls `0x63e7a80` for this custom pair.

`0x63e7a80` makes four ordered calls through archive slot `0x188`, each requesting **one bit**:

1. `X > epsilon`
2. `X < -epsilon`
3. `Y > epsilon`
4. `Y < -epsilon`

The exact threshold operand is double `9.999999747378752e-05` at RVA `0x9e08fd8`; the negative operand is at `0x9e09278`. It is the promoted float approximation of 0.0001. Comparisons are strict: equality with either boundary does not set that sign bit. On loading, each axis becomes +1 if its positive bit is set, otherwise −1 if its negative bit is set, otherwise 0. Positive wins if both sign bits for one axis are set.

| Source X,Y | Flags in serializer call order | Loaded X,Y |
| --- | --- | --- |
| 0,0 | 0 0 0 0 | 0,0 |
| 1,0 | 1 0 0 0 | 1,0 |
| −1,0 | 0 1 0 0 | −1,0 |
| 0,1 | 0 0 1 0 | 0,1 |
| 0,−1 | 0 0 0 1 | 0,−1 |
| 1,1 | 1 0 1 0 | 1,1 |
| epsilon,−epsilon | 0 0 0 0 | 0,0 |

This describes a four-bit **extension field**, not a four-bit movement packet. Exact placement in the enclosing Unreal network message, byte packing, export/RPC identifiers, and all baseline quantization remain to be validated. The separate acceleration field can still preserve information absent from this direction field. Verification examples implement the reviewed comparisons; they are not independent native execution or packet golden vectors.

## Walking, running, and sprinting

`SetSprintRequest` implementation `0x5ec4de0` stores movement `bWantsToSprint` at `+0x11d0`. BaseCharacter's ToggleSprint thunk `0x5d83d90` toggles that request after its checks. A request is only one part of the gait calculation.

Compressed-flag restoration `0x5ece600` first delegates engine handling, then applies three global masks. Their **on-disk initializers** are:

| Mask global | Initial mask | Destination |
| --- | --- | --- |
| `0xd378c7c` | `0x10` | BaseCharacter `bWantsToWalk`, `+0x1269` bit 0, via `0x6b61ea0` |
| `0xd378c80` | `0x20` | Movement `bWantsToSprint`, `+0x11d0` |
| `0xd378c84` | `0x40` | Movement `bClientMantling`, `+0xfff` |

These globals may change at runtime. The collaboration follow-up now links the sender as well: custom saved-move table `0xb7cd440`, slot `0x50`, reaches `0x5ea46c0`, which calls base `0x3ddcfa0` and ORs these same three mask globals. Walk and sprint come from saved-move `+0x448` bits 0/1; mantle comes from `+0x464` bit 0. Setup routine `0x5ec39a0` copies character walk state, movement sprint request, and the custom input pair into the saved move. Base `0x3ddcfa0` preserves saved byte `+0x10` bits 0 and 1 as output bits `0x01/0x02`. This is a bidirectional static link; live global values and complete unsupported movement-state behavior remain unmeasured. The walk setter also invokes a helper when the bit changes; its effects need review.

PlayerCharacter `GetAllowedGait` at `0x6c11030` returns Walking (0) when the walk bit is set, otherwise Running (1) or Sprinting (2) according to the sprint request and `CanSprint` (`0x6c003d0`). Mounted state has a separate branch. CanSprint requires movement input, excludes Aiming rotation mode, and checks an input-amount threshold; LookingDirection also checks an angle. BaseCharacter IsSprinting (`0x6b4d470`) and PlayerCharacter ActualGait (`0x6c10de0`) are separate predicates. Their complete state/angle/transition behavior is not yet specified.

`SetAllowedGait` (`0x5ec2d80`) updates an internal movement byte at `+0x12c5` under its owner/permission checks. That storage alone does not establish how the effective sprint speed changes.

## Actual speed is a selection plus modifiers

`GetMaxSpeed` (`0x5ea5370`) obtains backward/pure-sideways predicates, selects a base speed through movement slot `0xcd8`, applies an owner multiplier and an optional cap, then applies additional owner, movement, and physical-material multipliers.

For the reviewed ground-speed branch, `0x5ea2150` passes one of these triplets to selector `0x5ea4b90`:

| State | Forward field | Pure-sideways field | Backward field |
| --- | --- | --- | --- |
| Walking requested | MaxWalkSpeed `+0x2c8` | MaxWalkStrafeSpeed `+0x1020` | MaxWalkSpeedBackward `+0x1024` |
| Walking not requested | MaxRunSpeed `+0x1028` | MaxRunStrafeSpeed `+0x102c` | MaxRunSpeedBackward `+0x1030` |

The selector prioritizes the pure-sideways case. Forward/backward may instead use stat-backed values when flags `+0x1090/+0x10d0` are enabled; associated identifiers are at `+0x1098/+0x10d8`. Missing-owner/stat fallback behavior is movement-mode dependent. Swimming, flying, falling/previous-mode handling, and custom modes have separate branches.

For ordinary finite values, the reviewed top-level calculation can be written:

```text
B = direction/mode/walk-state selected speed
A = B * owner.virtual[0xcd0]()
C = optional cap returned by 0x6b3cfe0
if C >= 0: A = min(A, C * owner.virtual[0xce0]())
MaxSpeed = A * owner.virtual[0xcd8]() * movement.float[0x1348]
             * owner.PhysicalMaterialSpeedMult[0x1274]
```

The constructor-installed character tables map `0xcd0` to getter `0x6b3cdc0`, which reads the cached MoveSpeedMult float at character `+0x13a0`, and `0xcd8` to `0x6b3be90`. The cache identity is corroborated by reflected OnMoveSpeedMultUpdated thunk `0x5d811d0` → character slot `0xdb8` → `0x6b527c0`, which evaluates the stat via StatsComponent `+0xf60` and `0x5e8db50`, storing the result at `+0x13a0` (zero without valid stats). Thus pure-lateral base selection bypasses forward/backward stat lookup **but still receives the outer cached MoveSpeedMult** and other multipliers/cap. Triplet ratios alone remain conditional on the remaining modifiers being equivalent.

Owner `0xcd8` includes an optional mounted modifier, owner slot `0xce8`, a clamped `1 − stats.float[0x1410]`, and `AIMovementModifier` at `+0x126c`. This `stats+0x1410` is on the stats object, **not** the identically numbered BaseCharacter soft-collision flag. Owner `0xce8` (`0x6b3c8b0` on the inspected PlayerCharacter table) includes effect/stat calculation that still needs full identification. Neither this routine nor the reviewed ground selector establishes an effective sprint-speed consumer. PlayerCharacter GetSprintingSpeedModifier `0x6c181a0` and crouch counterpart `0x6c11b80` simply read instance floats `+0x24f8/+0x2500`; getter presence is not proof of locomotion use. EnableSprint/DisableSprint `0x6b3a360/0x6b36400` only change movement request `+0x11d0` after type checks.

Constructor `0x5e928b0` writes MaxWalkStrafeSpeed=180, MaxWalkSpeedBackward=220, MaxRunSpeed=1100, MaxRunStrafeSpeed=180, MaxRunSpeedBackward=220, and MaxSprintSpeed=750. These are **base constructor initializers**, not measured live player speeds. Assets, derived constructors, stats, material state, and effects can override the outcome. The reviewed ground GetMaxSpeed path does not directly read MaxSprintSpeed `+0x1034`; setting a server's sprint speed to 750 on this evidence would be unjustified. The consumer of SprintSpeedModifier and the effective sprint transition remain priority gaps.

## Move timing and state restoration

### Saved-move allocation ownership

Constructor `0x5e928b0` also installs interface table `0xb111938` at movement `+0x1e0`. Client prediction lookup `0x3de1b10` calls that interface's slot `0x28` when its cached pointer is absent. Target `0x5ea6060` allocates `0x180` bytes, calls baseline prediction construction, and installs custom prediction table `0xb7cd4b0`. Its allocator slot `0x10` (`0x5e95b40`) allocates a `0x470`-byte saved move, calls baseline construction, and installs saved-move table `0xb7cd440`. This links the sender/setup routines above to the AoC movement constructor. The primary-table slot `0xb88` was separately inspected and rejected as a prediction accessor lead: `0x5ecddf0` refreshes floor state.

The movement constructor assigns its embedded custom container at `+0x1390` to the engine container pointer at `+0x988`. It contains three custom move objects with stride `0x80` in addition to the baseline objects.

The registered ServerMovePacked thunk `0x3d73c40` reaches `0x3dff940`, which initializes a bit reader, invokes container serialization, and dispatches movement slot `0xbe8`. Its bit-limit global has an on-disk initializer of 4096; this is not an observed packet length. The custom `0x5ec1f80` path either copies the container into a deferred history array (stride `0x2e0`) or delegates immediate processing to `0x3dffa90`. The engine container traversal dispatches individual old/pending/new move data through slot `0xbf0`.

Individual-move handler `0x5ec20b0` restores the custom direction pair into character `CurrentMovementInput` **before** invoking the movement simulation path. It handles move timestamp, acceleration, compressed flags, and control rotation, calls a timestamp-validation virtual and delta-time helper `0x3de2340`, advances prediction time for positive deltas, and invokes slot `0xb58` → `0x5ead520` → `0x3de7ce0`. That engine path restores compressed flags and constrains acceleration before its movement update.

Compatibility consequence: received moves must be interpreted in the same state and time order. A server loop that advances position using only packet arrival time and a nominal speed cannot be assumed equivalent. Timestamp resets, duplicate/old-move treatment, move combination, time discrepancy resolution, delta clamps, and deferred-container draining still need complete tracing. SDK fields also expose alternate Player/NPC/Vehicle MovementSystem classes; live selection of those systems is unresolved.

## Error decisions, acknowledgments, and corrections

Engine ClientMoveResponsePacked thunk `0x3d705a0` reaches response decoding at `0x3de80b0`, then movement slot `0xbf8` → `0x3dd0a90`. An acknowledgment branch dispatches `0xbc0`; normal correction dispatches `0xbc8` with location, velocity, base/bone, mode, and optional rotation. Root-motion-specific response branches also exist. `ClientAckGoodMove` (`0x3dcf5a0`) searches prediction history by timestamp and advances acknowledged state. The AoC `ClientAdjustPosition` override (`0x5e9e420`) delegates engine `0x3dcf710` and performs additional orientation/correction work. The complete saved-move replay loop and smoothing integration have not yet been validated.

The SDK declares BaseCharacter ReliableClientMoveResponsePacked as a reliable client RPC. Outgoing routine `0x5ead530` selects character wrapper `0x5d7a410` or engine wrapper `0x3d4f660` under an internal flag/global, then clears the flag. Binding those wrappers' function-metadata globals to exact RPC names is still pending. Reliable versus standard outgoing routing is therefore a candidate identity, not a verified universal delivery rule.

Position-error decision candidate `0x5ec1b30` first checks current-versus-reported displacement through a manager virtual. With `bServerIgnoreErrorDirection` disabled, it returns an error when that check exceeds its allowance and distinguishes large correction distance.

With that flag enabled, the reviewed branch computes approximately, preserving native float/double conversions when implemented:

```text
D = distance(reported location, native snapshot at movement +0x1358)
V = maximum of GetMaxSpeed, velocity magnitude, and applicable override terms
dt = server prediction time (+0xa0) - native snapshot float time (+0x1370)
E = max(float(D) - float(dt) * V, 0)
```

Applicable override terms include the character's override velocity, another conditionally used movement vector, and an ability-component speed field. It returns an error only after the initial manager check and additional tests: `E² > manager.float[0x3ac]`, `E > NetworkLargeClientCorrectionDistance`, and actual current-versus-reported distance greater than that large distance. This describes one branch, not all correction policy, update frequency, or validation behavior.

**SDK discrepancy:** native code writes/reads the three snapshot doubles at `+0x1358/+0x1360/+0x1368` and time at `+0x1370`. The supplied SDK labels TargetSnapshotLocation at `+0x1378`. Do not silently apply that name/offset to this branch. The native snapshot fields remain unnamed pending layout resolution.

The base constructor initializes NetworkLargeClientCorrectionDistance to 45 and the error-direction flag to true. Effective instance/config values remain unmeasured. Disabling correction or increasing tolerance until movement appears smooth would not demonstrate compatible simulation; authoritative state could continue diverging.

Epic's [networked CharacterMovement explanation](https://dev.epicgames.com/documentation/en-us/unreal-engine/understanding-networked-movement-in-the-character-movement-component-for-unreal-engine) supplies a general baseline: clients retain predicted moves, servers process timestamped inputs, and clients handle acknowledgment or correction and replay. It also describes custom packed-move extensions. The currently served documentation is not evidence of the exact engine version or Ashes modifications in this executable.

## Collision findings and missing solver work

IsWalkable (`0x3de4f70`) requires hit flags `(hit[0xad] & 3) == 1` and computes the up-facing normal as `-dot(GravityDirection, ImpactNormal)`. It rejects values below the small positive threshold and compares against WalkableFloorZ (`+0x220`). A component slope override can lower or raise the threshold; another override type uses a separate constant. This is gravity relative, not universally a comparison against world-Z normal.

K2_FindFloor and K2_ComputeFloorDist are linked to wrappers that delegate underlying virtual solver slots `0xa00/0xa10`. The complete floor query, movement sweep, stair/step-up, wall slide, two-wall adjustment, depenetration, braking/friction, falling integration, and moving-base calculations are not recovered by those wrappers. Soft-collision flags/curve fields are known from metadata, but their actual response solver remains unresolved.

Authority-role setup candidate `0x5e96a80` copies ServerMaxSimulationTimeStep `+0x1000` and ServerMaxSimulationIterations `+0x1004` into engine simulation limits `+0x430/+0x434` under a role helper. Effective limit values and subdivision behavior need verification. Matching geometry also requires the actual capsule shape, collision profiles/channels, mesh/terrain collision, slope/step parameters, and moving-base transforms. A visually similar map is insufficient evidence of identical collision outcomes.

## CalcVelocity and slowing after a speed change

The reflected CalcVelocity thunk `0x3e11110` calls primary slot `0x7e8`, which the AoC constructor table maps to **custom override `0x5e9aa10`**. This is the client routine to compare with a future server integrator. It has owner override/root-motion guards, requested-movement handling, force-acceleration behavior, braking dispatch, directional friction, fluid drag, acceleration addition, and later avoidance/soft-push paths. Applying a generic engine formula without those conditions does not establish equivalence.

An important reviewed ordinary-acceleration branch at fragment `0x5e9b311` does the following after preceding braking/drag work:

```text
if IsExceedingMaxSpeed(effective_max):
    cap = float(length(current velocity))
else:
    cap = effective_max
velocity += acceleration * delta_time
velocity = clamp_magnitude(velocity, cap)
```

Requested-movement and zero-acceleration branches are separate. Do not introduce an unconditional end-of-function clamp to nominal speed when the native path skips this acceleration-add branch. Overspeed can be retained while braking, which matters when changing from a higher run cap to a lower walk/direction cap.

IsExceedingMaxSpeed is named through reflected thunk `0x3e655a0` → primary slot `0x570` → leaf `0x3e4ebe0`. For finite values, its exact comparison is:

```text
s = max(float(MaxSpeedArgument), 0.0f)
threshold = float(float(s * s) * 1.0099999904632568f)
exceeding = double_velocity_squared > double(threshold)
```

The tolerance is approximately **1.01 on squared speed**, not 1.01 on speed and not `speed + 1e-6`. The helper squares the three double velocity components at `+0x120/+0x128/+0x130`, compares strictly, and receives the float speed argument in XMM1. The acceleration-add branch passes its effective cap via XMM10 and narrows the chosen current-speed cap to float before addition/clamping. The [exact leaf proof](<E:/Ashes Of Creation GPT/client-research/proofs/movement-overspeed-leaf.json>) ends at its return (`0x3e4ec2e`).

Braking override slot `0x9f0` reaches `0x5e95e40`. It includes an optional target/override velocity, a character-dependent multiplier, braking friction factor `+0x2e4`, braking substep `+0x2ec`, nonnegative friction/deceleration handling, and repeated integration. Its substep clamp constants are float approximations of 1/75 and 1/20 seconds; stopping includes a 10.0 threshold when deceleration is active. Complete target-velocity semantics and PhysWalking/PhysFalling ordering/subdivision remain open. The base constructor also copies simulation limits, and BaseCharacter construction can modify them; use effective live instance values.

## Collaboration follow-up evidence

The separately authorized `Implement C++ movement compatibility` chat owns server source changes. This research chat supplied the lateral multiplier, cached stat, sender-mask, and velocity-cap findings through explicit follow-ups. Its implementation/questions document is [movement-research-collaboration.md](<E:/Ashes Of Creation GPT/CPP/docs/movement-research-collaboration.md>); server progress and validation status belong to that chat.

The follow-up saved 21 additional native range outputs in `decompiled/movement-followup/`, with four incremental Ghidra saves. [Follow-up verification](<E:/Ashes Of Creation GPT/client-research/proofs/movement-followup-verification.json>) passes 12 checks, covering selected dispatch, getter fields, sender-mask references, exact tolerance, 49 snapshot fingerprints and all manifest outputs. [Target manifest](<E:/Ashes Of Creation GPT/client-research/batches/movement-followup.tsv>) and [transcript](<E:/Ashes Of Creation GPT/client-research/ghidra-movement-followup.log>) are retained. These are static checks, not independent native execution or server equivalence tests. Runtime masks/configuration, sprint/stat consumers, full collision and replay still need evidence.

The separate implementation chat subsequently completed its C++ patch/build/offline checkpoint. Its [verification report](<E:/Ashes Of Creation GPT/CPP/runs/movement-compatibility-20261007/verification.json>) records 487 core, 83 movement, 12,071 terrain, 22 headless network, nine movement API and five trace-analyzer checks. Release passed all three suites; final Debug passed core/movement. This research chat reviewed the saved logs and matched all 15 recorded source/document hashes and both backend binary hashes, without rerunning the tests. The [review fingerprint](<E:/Ashes Of Creation GPT/client-research/proofs/cpp-implementation-checkpoint-review.json>) preserves that boundary. No game client was launched in that implementation pass; a dedicated fresh client trace remains necessary to assess the original walk-toggle/pushback symptoms, sprint behavior and actual prediction divergence.

## Specification for a future C++ server

The following is an implementation and validation plan, not a claim that these steps have already been completed on the server:

1. **Complete the movement wire contract.** Bind live class/RPC identities, finish baseline bit serialization and quantization, sender-side flags and saved-move extensions, and distinguish old/pending/new moves. Create exact serialized vectors for this executable build. Verify the custom four-bit extension and input restoration against those vectors.
2. **Recover effective movement configuration.** Resolve the actual possessed character/movement classes, asset defaults and overrides, stat/effect identifiers, direction speeds, sprint state consumers, acceleration, braking, friction, gravity, simulation limits, and collision settings. Preserve their source/build identity. Constructor values alone are insufficient.
3. **Reproduce per-move state transitions and physics.** Restore direction, flags, rotation, and acceleration in native order; match timestamp acceptance/delta handling and simulation subdivision. Match mode transitions, floor/sweep/slide/step behavior and collision geometry. Using the corresponding engine movement implementation may reduce the amount to reconstruct, but exact engine compatibility and AoC overrides must still be demonstrated.
4. **Reproduce acknowledgment and correction semantics.** Match timestamps, base/bone references, modes, rotation/root-motion response variants, and delivery selection. Finish tracing prediction-history removal and replay. Correct state/order errors before tuning tolerances or smoothing.
5. **Validate against a trace oracle.** Record per-move input, flags, timestamp/delta, effective speed/acceleration, pre/post position/velocity/mode, floor hit/base, acknowledgment, and correction. Compare equivalent states after equal simulated elapsed time and locate the first divergent move. Measure correction count/magnitude and replay displacement; establish tolerances from measured precision and quantization rather than an arbitrary large allowance.

| Validation group | Required cases |
| --- | --- |
| Direction/gait | Start/stop, forward/back/left/right, diagonals, walking transitions, sprint eligibility and release, direction reversal |
| Collision | Flat ground, ramps around slope boundary, stairs around step boundary, wall/corner sliding, penetration recovery, gravity changes, moving bases |
| Timing | Different frame intervals and server subdivisions, latency, jitter, loss, reordering, duplicated/old moves, timestamp reset, deferred processing |
| Special state | Jump/fall/land, root motion, mantle, mounts/vehicles, stat/material/effect changes during pending moves |
| Reconciliation | Valid acknowledgments, deliberate authoritative disagreement, corrected base/mode/rotation, replay of remaining inputs |

Existing Wireshark-folder captures are from February 2026 and have not been analyzed in this pass or tied to the current executable hash. They are potential leads, not a validated current-build movement oracle. Packet-level and runtime validation remain necessary before claiming exact replication or elimination of client jitter.

## Reproduce the saved static checks

Run from `E:\Ashes Of Creation GPT`:

```powershell
python client-research/scripts/research_movement.py --extended
python client-research/scripts/verify_movement_evidence.py
python client-research/scripts/verify_movement_followup.py
```

The first command regenerates the bounded map/manifests/snapshots against the recorded executable; it does not itself run Ghidra. The second checks the saved outputs and native links. To rerun the focused Ghidra pass deliberately, use the existing script's `-Manifest movement-extended.tsv -BatchName movement` arguments; do not open the same isolated project in the GUI while a headless pass is using it.
# Resources, world identity and enabled time discrepancy follow-up (2026-10-07)

These additions answer the implementation chat's fresh live-session questions. Server source/build/live changes remain owned by `Implement C++ movement compatibility` (thread `01a1167a-dcaf-7bd3-82b8-6acf396b15ae`). All native RVAs below refer to executable SHA256 `4f1cd43ceeb89190f048734efd4d63152b9f8e11fa31fc41093b0d90f4a1cd43`. Four isolated Ghidra manifests/logs/output directories use `resources-names-timing`, then suffixes `-2`, `-3`, `-4`; earlier movement manifests were preserved. Exception roots can have chained fragments: the 82-byte entry range for `3df5240` is not the entire logical handler.

## Timing: direct evidence and implementation implications

The constructor-bound movement primary table `0xb110970` maps timestamp-validator slot `0xb90` to `0x3e102b0`, and discrepancy-handler slot `0xba0` to `0x3df5240`. Individual-move handler `0x5ec20b0` restores custom input, validates timestamps, invokes discrepancy processing through validation, obtains the move delta, and simulates only if delta is positive. For positive delta it assigns prediction `+0x98 = received timestamp`, advances double `+0xa0` by the delta and assigns both `+8` and `+0xac` from float-narrowed `UWorld +0x7b8` time. The initial/uninitialized timestamp behavior must be considered separately.

`0x3de2340..0x3de237b` is a complete two-return leaf with no indexed exception range. If prediction `+0xc0` is true, it returns override delta `+0xc4`. Otherwise it returns:

```text
min(timestamp - prediction.float98,
    max(global.floatD26EEDC, 1.0f) * prediction.floatB0 * effectiveActorDilation)
```

Each subtraction/multiply/minimum is float arithmetic. Global disk default is `1.75f`; its live value was also reported as 1.75. Prediction `+0xb0` is the maximum move delta, distinct from component maximum simulation substep. `0x3b7d520` computes the passed dilation using WorldSettings virtual `+0x848` multiplied by actor `CustomTimeDilation +0x178`; `0x3b7d560` obtains the same factor through the actor's world lookup for resolution. The reviewed delta helper contains no arrival-token budget.

`0x3e102b0` accepts finite positive timestamps with delta at least the exact float `0.0000009999999974752427`. Absolute delta is compared to half movement `+0x818` reset interval. Small duplicate/reversed deltas are refused. A large positive delta is refused; a large negative delta can reset, subject to the `+0x81c` world-time cooldown, by subtracting the full reset interval from prediction `+0x98`. Accepted ordinary moves invoke discrepancy slot `0xba0`, except explicit prediction-state/reset branches. See full pseudocode and assembly for those branches; a fixed local wrap-window approximation is not a complete port.

`0x3df5240` obtains the GameNetworkManager CDO and returns unless detection is enabled and prediction `+0xac` is nonzero. Its config offsets match SDK reflection:

| Manager offset | Field | Fresh implementation-chat readback |
| --- | --- | --- |
| 3f1 | bMovementTimeDiscrepancyDetection | true |
| 3f2 | bMovementTimeDiscrepancyResolution | true |
| 3f4 | MovementTimeDiscrepancyMaxTimeMargin | 0.25 |
| 3f8 | MovementTimeDiscrepancyMinTimeMargin | -0.25 |
| 3fc | MovementTimeDiscrepancyResolutionRate | 1.0 |
| 400 | MovementTimeDiscrepancyDriftAllowance | 0.0 |
| 404 | bMovementTimeDiscrepancyForceCorrectionsDuringResolution | request live readback |

Fresh `CPP/runs/character-movement-followup-20261007/native-character.json` is implementation-owned, bound to client PID 152140/creation filetime 134358551149045094 and the executable hash above. It reports actor/WorldSettings dilation 1.0, maximum move delta 0.75, simulation step about 0.05, eight simulation iterations and reset interval 240. These are current-session observations, not shipped server defaults. Preserve the file with the implementation's run checkpoint because a continuing readback can replace it.

The following is the enabled-handler interpretation for the observed **zero drift allowance**, transcribed from the chained assembly. Every intermediate arithmetic result is a float; world time is narrowed from double first. `P` means server prediction data. Use the full handler output if supporting nonzero drift, unusual/nonfinite configuration or overridden virtual callbacks.

```text
now = float(world.timeDouble7B8)
serverDelta = (now - P.float8) * actor.CustomTimeDilation
clientDelta = timestamp - P.float98
rawError = clientDelta - serverDelta
candidate = P.floatBC + rawError
P.floatB8 += rawError                         // lifetime raw discrepancy
adjusted = max(candidate, manager.minMargin)
effectiveError = candidate == 0 ? rawError : (adjusted / candidate) * rawError

if (!P.boolC0 || P.floatBC <= 0):
    P.boolC0 = false
    if (adjusted <= manager.maxMargin):
        P.floatBC = adjusted
    else:
        if (manager.resolution):
            P.boolC0 = true
            P.floatBC = adjusted - effectiveError
        else:
            P.floatBC = 0
        movement.virtualBA8(adjusted, P.floatB8, now - P.floatCC, rawError)
else:
    P.boolC0 = true                           // retain existing positive debt

if (P.boolC0):
    if (manager.forceCorrections): P.uintB4 |= 1
    serverDelta = (now - P.float8) * actor.CustomTimeDilation
    capped = min(clientDelta, max(globalD26EEDC,1) * P.floatB0 * effectiveActorDilation)
    if (serverDelta > 0):
        candidateDelta = capped + P.floatC8
        P.floatC8 = 0
    else:
        P.floatC8 += capped
        candidateDelta = capped + P.floatC8  // instruction order, not a typo
    available = max(min(candidateDelta, serverDelta), 0)
    rate = max(min(manager.rate, 1), 0)
    payback = min(rate * available, P.floatBC)
    P.floatC4 = max(available - payback, exactFloatMinimumTick)
    P.floatBC -= available - P.floatC4
```

In the zero/same-world-time branch, `available` clamps to zero, but `C8` retains the accumulation for the next positive server delta. At rate 1.0, active discrepancy resolution can reduce a move to the minimum tick. Therefore this evidence does **not** justify simulating every client delta unchecked. It does establish that token exhaustion/full interval discard, immediate timestamp advancement and lost simulation time are different behavior. All old/pending/new moves processed during one engine frame observe the same world clock, rather than a fresh packet-arrival clock per move. Choosing the C++ engine-equivalent frame/world clock and initial connection time is an implementation requirement; this research did not measure live original-server clock policy or demonstrate the port.

Native `0x3de2380..0x3de23ae` computes a simulation substep: if remaining time exceeds movement `+0x430` and iteration count is below `+0x434`, choose `min(maxStep, remaining*0.5f)`; otherwise choose all remaining time. Then enforce the same exact minimum tick. This differs from equally dividing by `ceil(dt/maxStep)`. The PhysWalking/PhysFalling loops' call sites, iteration-count increments and later contacts still need tracing before claiming complete subdivision parity.

## World name: proven component source

Registered `BaseCharacter.GetCharacterName` thunk `0x5d7c9a0` invokes leaf `0x6b3d100`, which returns `pawn.CharacterInformationComponent(+0x7c8)->CharacterName(+0x130)`. Registered `SetCharacterName` thunk `0x5d82d60` calls `0x6b5f430`, which compares/writes that same FString and marks the component dirty through `0x5036d60`. SDK `UCharacterInfo.CharacterName +0x130` is Net/RepNotify; `CharacterGuid +0x118` is also Net/RepNotify. `OnRep_CharacterName` thunk `0x5d81500` invokes component virtual `0x570`; its concrete derived callback remains unbound here.

Fresh implementation readback found existing component `BaseCharacterInfo`, class `PlayerInfo`, holding `CharacterName='Player'`, while pawn PlayerState was null. This supports binding the selected lobby record to world login, then replicating the existing identity component's selected name/GUID and supplying the existing controller/pawn PlayerState initialization stages. Pawn non-Net `CharacterName +0x1890` is not this getter's source. PlayerState PlayerName and controller GetPlayerName (`0x6ac2710` copies controller `+0x3178`) are additional distinct consumers; they must not be assumed interchangeable. `WidgetPlayer.GetPlayerName` → `0x68b2a30` reads a bound object's FText via widget `+0x1da8`/object `+0x290`, not a proven direct pawn-name read. Nameplate delegate/display propagation still requires live readback/UI acceptance or further callback tracing.

The existing CPP name serializer uses handle 8 for the identity component. This is an implementation lead to verify against its live network cache; this research does not establish the complete reflected wire-handle layout anew. The implementation chat corrected its initial visual concern about a short character GUID: current LabExplorer ID `50a31b0076a34ec78250fe299b779f09` is 32 hex digits. No arbitrary padding or record mutation is justified.

## Health, mana, stamina and sprint: dependencies and remaining evidence

Registered AoCStatsComponent resource getter thunks call native implementations below. Each obtains the design record from `0x60accf0`, then copies a **native compact cached stat reference** to evaluator `0x5e8db50`:

| Resource | Getter body RVA | Native reference offset in returned record |
| --- | --- | --- |
| MaxHealth | 61229f0 | 1330 |
| Health | 6121dc0 | 1350 |
| MaxMana | 6122af0 | 1390 |
| Mana | 61227e0 | 13b0 |
| MaxStamina | 6122bf0 | 13d0 |
| Stamina | 61230f0 | 13f0 |

`0x60accf0` resolves design type `0x6a9c0102f8f941c0`, record ID `0x636a8ad25678`, with revision refresh. Its missing-record fallback calls constructor `0x5a46400`, which clears references; this is not a source of valid resource IDs or amounts. These native 0x20-stride offsets **must not** be copied into the SDK GameStatProfileRecord layout (its reflected references have a different stride). Numeric resource IDs were subsequently verified through the live lookup below; production default quantities remain unverified.

Evaluator `0x5e8db50` resolves the reference, reads record ID `+8` and StatType `+0x79`, and looks up the stats component's native cache. SDK StatType enum corroborates Float=0, Int32=1, Bool=2, FloatArray=3. Base/min/max/regen/spawn/reset behavior are stat-record expressions/settings, rather than a universal hardcoded resource amount.

ApplyReplicatedStatInt32 thunk `0x5d6f510` → `0x6111600` resolves received item record ID at `+0x10` using design type `0x4a74ae5ed850dc97`. It searches the **existing** native stats map (`StatsComponent+0x668`, entries stride0x38), writes received value bits from item `+0x18` only when the entry exists, and conditionally reads item `+0x1c/+0x20` if record `+0x247` enables base/equipment buckets. It then performs recalculation/change notification via `0x613fbd0` and `0x6150020`. Missing definition/cache entry returns without constructing a stat. Delegate flushing wrapper calls `0x6126420` for each of four Int32 FastArrays; that applies every queued item and binds wrapper callbacks, confirming that replication includes cache/notification prerequisites.

SDK distinguishes Int32 arrays Owner `+0x890`, ProxyOnly `+0x9b0`, OwnerProxy `+0xad0`, EveryoneProxy `+0xbf0`, and corresponding FloatArray arrays. Stat record `Replication +0x246` and `bReplicatesBaseAndEquipmentBuckets +0x247`, type, live network field and existing item IDs/array keys must be checked before updating. Current CPP speed synchronization requires exactly two records in fixed gravity/speed order: expand that guard to validated record lookup when adding resources. The existing speed float-bit serializer does not prove arbitrary resource initialization is valid.

StaminaBar change thunk `0x5c471f0` calls `0x6795240`; the body updates stamina display/fade state and obtains pawn maximum stamina through its getter. This establishes a UI resource consumer, not a physical sprint gate. PlayerCharacter.CanSprint `0x6c003d0` requires movement input, input amount greater than its threshold and permitted rotation/direction; no direct stamina test exists in this reviewed function. OnSprint input handler `0x6add9b0` checks HUD sprint-blocking windows through `0x666a0a0` before forwarding the request. SDK movement `SprintCostResource +0x1310` is a promising resource-cost lead, but no complete cost/depletion/effective-speed consumer is bound yet. The `+0x1310` load in movement tick `0x5ec5020` is on the **owner character**, part of its override-velocity vector, and is not proof of reading movement SprintCostResource.

### Fresh resource identities and native scope routing

The implementation chat subsequently saved `CPP/runs/character-movement-followup-20261007/native-resources.json`. Its session proof matches the client above. All six records resolve in the definition database and exist in the current native stats cache/StatList. All report StatType=0 (Float), no base/equipment replication, and current cached numeric buckets zero:

| Resource | Record ID | Replication byte | Native destination |
| --- | --- | --- | --- |
| MaxHealth | 0x631f5d125679 | 7 | Int32EveryoneProxy |
| Health | 0x631f5cd65678 | 7 | Int32EveryoneProxy |
| MaxMana | 0x634d486d5679 | 7 | Int32EveryoneProxy |
| Mana | 0x634d48455678 | 7 | Int32EveryoneProxy |
| MaxStamina | 0x5429e671574d01b4 | 1 | Int32Owner |
| Stamina | 0x5429e4778c77030c | 1 | Int32Owner |

New native replication passes saved `decompiled/resources-replication` (three roots) and `decompiled/resources-replication-routing` (one root), plus matching manifests, logs and snapshots. `0x61469f0` verifies record replication and authority, then routes scalar types 0/1/2 to `0x6144990`. That routine selects array destination from the actual byte: 1 → Owner `+0x890`, 4 → ProxyOnly `+0x9b0`, 5 → OwnerProxy `+0xad0`, 6/7 → EveryoneProxy `+0xbf0`. Matching existing records receive value/bucket bits and are marked dirty. This is direct routing evidence, rather than inferring scope merely from enum labels. EReplicationRules bits Autonomous=1, Simulated=2, Proxy=4 corroborate the combination.

Float scalar getter leaf `0x6175ec0..0x6175ecd` moves the stored Int32 bits then MOVSS loads them into XMM0; it does not numerically convert Int32 to float. Therefore these confirmed Float records use IEEE float bits in the Int32 FastArray, as the existing speed/gravity values do. Preserve proper item IDs/array keys and initialize each live scope using its verified network-cache field. Owner field index/max was subsequently verified directly below; complete new delta serialization acceptance still requires received-cache readback.

Direct research-owned read-only live inspection at 14:26:41 UTC verified **Owner field index 3/max23**, EveryoneProxy field index 6/max23, property offsets/sizes, and the same referenced `StatInt32Rep` UScriptStruct for both. The Owner array was empty; EveryoneProxy held two items. Both already had the same valid `StatRepDelegateWrapper`, whose outer is the current stats component. `proofs/resources-network-cache-live.json` binds metadata and receiver identities to PID152140, creation filetime134358551149045094 and the executable hash. `scripts/inspect_resource_network_cache.py` reproduces this bounded inspection with current snapshot/lifetime/weak serial validation. Sandbox module enumeration initially failed with WinError5; approved read-only escalation succeeded after correcting serial validation to read the GObjects item rather than assuming the generic identity helper returned a serial. No game calls or process memory writes occurred. These checks establish an initialized receiver/field path; they do not establish acceptance of the proposed new records.

The proposed 100 current/maximum resource amounts are explicitly configurable **lab profile values**, not recovered production defaults. They must be labeled that way and verified by received-cache, getter and HUD readback. Changing health/max-health can change death-state/UI consumers and requires that live acceptance; it is not evidence of movement solver equivalence.

Static verification `proofs/resources-names-timing-verification.json` passed for 25 manifest outputs and 36 saved snapshot fingerprints, including timing dispatch/constants, complete bounded name/float getter leaves and the no-exception timing leaves. This does not validate server timing behavior, resource packet acceptance, sprint parity or full native control flow.

Do not infer that populating resources fixes jitter, or that no stamina gating exists anywhere. Required next evidence: default resource expressions, received resource values/UI state and Owner wire field/serializer acceptance, sprint-cost and effective-speed consumers, full nameplate callback propagation, and first equal-time movement divergence after implementing native timing.

## Implementation review: reset override and sprint input handoff

The implementation chat's rebuilt timing path was reviewed against `3df5240`, `3e102b0` and the complete delta leaf `3de2340`. Its ordinary finite, zero-drift discrepancy arithmetic and same-frame carry match the reviewed handler. This is a scoped static review, not solver or live jitter acceptance. One concrete mismatch was reported: the port returns the capped delta immediately on reset and has no persistent `C4` value. Native validation skips discrepancy processing on an accepted reset, but the later delta leaf still selects existing `C4` if `C0` is true. Constructor-bound `B110970 + B98` points to `131c2f0`, whose complete bytes `C2 00 00` are `RET 0`; the reset callback does not clear these fields. `proofs/timing-reset-callback.json` records the exact executable/table/leaf bytes. Preserve the override when discrepancy processing is skipped or returns early. Initial timestamp seeding, the local 60 Hz world clock and the port's upper timestamp bound remain implementation choices requiring acceptance, rather than recovered server defaults.

The sprint input consumer is now identified: controller `+0x1188` is SDK `ComboManager`, an `AoCInputComboManager`. `OnSprint` (`6add9b0`) calls `613c040(manager, 6, pressed)`. Registered `AoCInputComboManager.SetComboButtonPressed` thunk `58e7d30` calls this same body; SDK `EComboButtons` value 6 is `BUTTON_Sprint`. The body sets/clears bit `1 << 6` in manager `+0x58`. This establishes the input-to-ability-combo path; it does not establish the eventual sprint ability, cost or speed effect. Follow `UseComboAbilities`, its ability selection, `AoCRecordConstants.Sprint`, and resulting stat/effect updates before changing server sprint speed or stamina consumption. `BaseCharacter.SprintSpeedModifier +0x13f8` and `CrouchSprintSpeedModifier +0x13fc` are distinct from PlayerCharacter's `SprintingSpeedModifier +0x24f8` and `CrouchSprintingSpeedModifier +0x2500`; matching offset reads alone do not bind an owner or prove a speed consumer.

Parsed PlayerPawn `SprintLogic` is an empty function (`EX_Return(EX_Nothing)`, `EX_EndOfScript`) in this indexed asset, rather than a recovered physical speed setter. Its parsed source was saved as `proofs/blueprint-playerpawn-sprintlogic.json`. Runtime overrides or other functions still require evidence.

Metadata correction: the saved resource array byte at `+0x100` is `FFastArraySerializer.DeltaFlags`, not an initialization boolean. Its label in the inspection script/proof is now `delta_flags`; the original snapshot timestamp, process lifetime and bytes were retained. Owner was 0 (`None`), EveryoneProxy was 1 (`HasBeenSerialized`). A valid shared delegate wrapper establishes the receiver binding, not that the empty Owner array had already received a serialized delta. Full new record/getter/HUD acceptance remains the implementation chat's live check.

## Sprint ability definitions and input selection

Read-only `scripts/inspect_sprint_ability_records.py` inspected the native ability-type map `198cb7f1dd552cb7` through the validated design-manager weak handle. The saved proof `proofs/sprint-ability-records-live.json` binds the complete hash-chain enumeration (2,130 occupied records) to client PID119000, creation filetime134358571966106569 and the exact executable hash. This was a fresh lobby client, not the earlier PID152140 resource session. Relevant loaded definitions:

| Name | Record ID | Combo inputs | Exact input | Buffer priority |
| --- | --- | --- | --- | --- |
| General_Sprint | 5429e658a60b0054 | [6] | false | 0 |
| MountAbility_Sprint | 5429e6448d6619dd | [] | false | 2 |
| MountAbility_Sprint_AllowSwimming | 5429e7daf94505f4 | [] | false | 2 |

Registered `UseComboAbilities` thunk `58e80d0` invokes `61494c0`. The routine resolves the weak AbilityComponent at manager `+0x50`, iterates ability component `+0xa00` (`KnownAbilities`, SDK Net/RepNotify TArray<int64>), resolves each ability record and calls input matcher `612cc50`. That matcher checks record ComboInputs count `+0x7d8`, obtains the input mask through `611fec0`, excludes matching buffered/weak input entries, then compares manager `+0x58`: `(pressed & required) == required` when `bExactInput +0x7e0` is false, or strict equality when true. The selection routine subsequently uses BufferPriority `+0x7e4` and activation branches calling ability-component virtual `+0x630`/`+0x680`. Exact meanings of those virtuals, the activation prerequisites and resulting effects still need binding.

Therefore verify that `KnownAbilities` contains the General_Sprint record and that activation reaches the movement request/effect consumers. Populated stamina and a physical sprint-request flag are separate prerequisites. Loaded definitions do not prove granted abilities, successful activation or final speed/cost behavior. All three records had count1 at the SDK Costs array location `+0x450`; cost element/reference layout, expression values and payment timing are not independently established yet. Do not interpret this as one stamina point per tick. A follow-up attempted bounded cost-string reads, but the client had exited before access and the original successful proof was preserved. The expanded script explicitly labels unbound cost layouts as candidates and checks process lifetime before/after access.

The focused Ghidra pass `sprint-ability-selection` completed, saved the isolated project and exited. Three roots (`611fec0`, `612cc50`, `61494c0`) and seven hash-checked exception fragments are preserved with manifest, decompiled outputs, log and `proofs/sprint-ability-selection-verification.json`. `611fec0` has chained fragments; its 25-byte entry is not the complete mask builder. Registered `GetKnownAbilities` thunk `5cd43c0` copies the array at ability `+0xa00` using eight-byte elements. `OnRep_KnownAbilities` thunk `5cd63f0` jumps to `6bbb9c0`, whose eventual tail jump `6b0dc40` leads to HUD/action-bar update behavior in the existing bulk output. Exact notification dispatch was not rebound in the focused pass.

Minimum grant implementation lead: update the existing ability component's ordinary replicated `KnownAbilities` array, preserving its other entries, then read back the exact General_Sprint ID. Before authoring this delta, verify the fresh component/driver RepLayout parent, commands, handle, Int64 element and array shape. No wire handle or complete grant packet was recovered here; do not reuse stat FastArray field numbers. Grant receipt is a prerequisite for the reviewed selection path, not proof of successful activation, stamina payment or movement speed.

## Fresh cost definition and controller-link regression

Fresh client PID90816, creation filetime134358578814410142, independently supplied the same General_Sprint definition. `proofs/sprint-ability-records-live-90816-134358578814410142.json` now includes reflected runtime `AoCAbilityRecordBase` (4656 bytes), `AbilityCost` (200), `AbilityStatCost` (136) and `AoCExpression` (80) layouts, with nested array/struct type links verified. Costs +450 is an Array of AbilityCost; its Enabled expression starts at0 and StatCosts at50. AbilityStatCost.Stat at0 is a56-byte StatTypeDefId, and Value at38 is an80-byte AoCExpression. The reference resolves through the design map to **Stamina**, record5429e4778c77030c/type4a74ae5ed850dc97. General_Sprint's verified Enabled source is `IsMoving(GetOwner())`; its Value expression returns1.25 ordinarily and2.5 when `IsInCombat(GetSource())`. These are definition values, not a recovered payment cadence. Runtime evaluator context, exact exhaustion handling and physical sprint speed are still unbound. Mount variants have no StatCosts in the inspected first cost; no mount equivalence is inferred.

On fresh world entry the pawn received PlayerState but the controller remained null. Research-owned `proofs/controller-playerstate-live.json` verified actual controller OnRep slot888→3eebc80 and PlayerState ClientInitialize840→44119c0, plus controller RepLayout command18/handle19/type8/offset370. There is no controller pointer clear in the reviewed callback. The implementation chat's saved packet evidence showed different ClientRestart and ControllerPlayerState payloads both using reliable sequence50 on channel3 after retries of sequences48/49. Its C++ retransmit path moved the channel's last-issued counter backwards and reused an already-consumed sequence; the independent pawn channel9 succeeded.

The earlier fix was present in both root `lab/unreal.py` and frozen `CPP/baseline/lab/unreal.py`: `_send_bunches` updates `channel_reliable` only under `if retries == 0`. The C++ port omitted this retry guard. Thus this recurrence is a port regression of the prior retry behavior, not evidence that PlayerState wire layout changed. The implementation chat owns restoring the guard and adding an interleaved old-retry/new-stage regression; renewed native link acceptance is required before proceeding through character identity/resources. An initial message to that chat incorrectly attributed rollback to Python after reading an incomplete search snippet; it was promptly corrected after reading the enclosing `if retries == 0` block. No research edits to CPP or memory writes occurred.

Deployment checkpoint after the retry fix: read-only inspection confirmed `WorldProtocol::send(..., track_reliable)` updates the last-issued channel counter only when tracking new sends, and retransmissions use `send(c, bs, false)`. The deployed Release executable SHA256 independently matches `a9cdf0c725a0425c487bc37aa2b5c0a7db5740a648726dc3fbb581f51a392e38`. Server PID7520 and client PID85420/creation filetime134358585513175628 match the implementation chat's new session. That chat reports all three native suites plus25 network identity and9 movement API checks passing. Research did not rerun these suites. Fresh world PlayerState/name/GUID/resource acceptance is still pending; no client/server restart or input was performed here.

## 2026-10-08 JST: dashboard stall and movement acceptance checkpoints

The preceding deployment subsequently passed the implementation chat's native controller/pawn PlayerState, selected LabExplorer name/GUID and six resource current/max gates. The user independently confirmed the character name and bars, while reporting W rubberbanding. These initialization checks establish receipt in that session; they do not establish movement or sprint parity.

The first large correction in `CPP/runs/character-movement-followup-20261007/retry-fixed-live-trace.json` followed a backlog burst. Research independently replayed float32 arithmetic in `proofs/backlog-first-correction-review.json`, which retains the source hash and selected rows. Moves125102–125113 had errors no greater than0.063cm; move125114 had client delta0.07413482666015625s and processed world delta0.0666656494140625s. Adding their difference to prior discrepancy0.2437896728515625s crossed the0.25s margin. Native resolution selected the exact minimum tick, and computed debt0.1771250218153 matched the recorded value; position error then reached44.48386172033cm. This first divergence agrees with the reviewed zero-drift timing formula. It does not justify disabling discrepancy resolution or resetting debt.

The implementation chat measured the dashboard's database count scan at about0.479s with1,351,001 packet rows in a917MB database, and `/api/state` at0.895s while holding `Backend::mutex`. Movement processing needs that same mutex. Dashboard polling could therefore delay packets and produce catch-up bursts. Native timing reads world time during processing; sampling before a blocking lock adds a stale-clock mismatch. Dashboard queries/rendering must not hold the movement lock for their expensive work. A short lock for a bounded snapshot is consistent with this requirement; the server must keep processing independently of dashboard availability.

The implementation chat deployed Release SHA256 `bbc5596e780472652fe39239557abf9fb10ff66ea53d7e4de1d12f7fdafa2290`, serverPID125732, with committed-insert packet counts, immutable geometry snapshots/rendering outside the backend lock, processing-time clock sampling and lock-wait/simulation telemetry. Read-only source inspection confirms cached `Store::packet_count()` and clock sampling after acquiring the processing lock. The peer reports ten state calls at1.403million rows with median0.85ms/max15.4ms, and three native suites,25 network identity checks and9 movement API checks passing. These are peer-owned benchmark/test results. Fresh clientPID145444/creation134358596923129243 has passed initialization and600cm/s speed synchronization; automated W acceptance is ongoing at this checkpoint. Both older serverPID7520 and clientPID85420 have exited. Do not reuse their addresses or treat a short successful movement pulse as complete jitter acceptance.

## Existing ability receiver, captured export and notification evidence

Read-only `scripts/inspect_known_abilities.py` binds the current CPP inspection seed to executable hash, PID/creation, pawn weak index/serial, owned component and driver. First snapshotPID85420 showed empty `KnownAbilities` and no initialized AoCAbilityComponent RepLayout. The fresh `proofs/known-abilities-live-145444-134358596923129243.json` independently confirms the same state: existing `AbilityComponent`, classAoCAbilityComponent, index301616/serial66269; outer, `OwningChar +838` and native notification owner`+C8` all point to the current pawn. `OwnersStats` points to that pawn's stats component. `bReplicates=true`, `bNetAddressable=false`, and ComboManager's weak component reference matches. `KnownAbilities +A00` is reflected ArrayProperty of eight-byte Int64Property elements, currently count/capacity0. Native permanent UClass objects may have serial0 and flags42000000; the script narrowly permits that identity while retaining positive serial requirements for the dynamic pawn/component.

Live tableB6873D0 receive slots2A8/2B0 resolve respectively to131C2F0 and trampoline15F4670. `proofs/ability-component-receive-callbacks.json` independently verifies the table bytes, complete `C2 00 00` return leaf and `E9 7B 7C D2 FF` trampoline back to that leaf against the hash-bound executable. These callbacks add no initialization side effects in the observed table. This does not establish every receiver/activation prerequisite.

Offline evidence files `evidence/captured_stats_exports.json` and `evidence/world_bootstrap_capture.json` retain existing-component exports named exactly `AbilityComponent`, with pawn outer and `no_load=true`. `proofs/ability-component-captured-exports.json` collects64 references across these two overlapping decoded files, not64 independent captures, all network checksum2657332828. `proofs/ability-component-export-decode-verification.json` independently decodes frame3796/channel9's4209-bit export payload with zero bits remaining. This is a captured object export checksum, not a computed class CRC. Captured GUIDs must not be reused for the current pawn/component.

A verified existing-component export followed by an ordinary empty property block may initialize the receiver layout, as the implementation's CharacterInfo path suggests. This remains an implementation experiment requiring fresh export identity and layout readback. No research-owned exports, grants, activation calls or process writes occurred. Do not send General_Sprint until the actual KnownAbilities parent/commands/handle and array encoding are proven. An all-text RIP-relative LEA search for three ordinary-array receiver error strings found no matches; `proofs/ordinary-array-receiver-leads.json` records that restricted search. It does not establish absence of a receiver or recover its wire format.

Focused Ghidra batch `ability-grant-notify` completed and saved four roots/four fragments; `proofs/ability-grant-notify-verification.json` checks output headers and bytes against the executable. `OnRep_KnownAbilities`5cd63f0→6bbb9c0 requires helper56f0e70(native owner+C8, false), which tests net mode through3b847b0 and accepts the reviewed client mode3. It then requires OwningChar, its AoCPlayerController and AoCHUDBase before tailcalling6b0dc40. That routine refreshes action-bar objects/child slots through HUD+10F8. No physical sprint speed setter or EnableSprint call occurs in this reviewed notification path. Combo selection reads KnownAbilities directly; notification/HUD refresh alone does not prove activation, payment or speed.

## Automated client testing ownership

The human explicitly authorized coordinating automated login/Play/movement through the existing DLL. The separate **Find Unreal LLM Testing Libraries** chat owns `client-testing/` and all input; the **Implement C++ movement compatibility** chat owns CPP implementation, build and services. This research chat only inspects and documents evidence. Current adapter pins/IPC versions are in `client-testing/vendor/input-adapters.json`; legacy README build-status claims are historical. Testing uses a verified already-resident adapter, exact PID/creation and an expiring exclusive lease, bounded actions and release/watchdog cleanup. Coordinate through the owner; do not inject a new DLL or run concurrent input.

The old-session three-second W baseline is `client-testing/runs/baseline-b26f3fd206ae4c59953bd4c371ed9245.json`: reported horizontal displacement658.391cm/vertical45.768cm, held keys released and lease revoked. A short interval with all51 new moves ACKed and max3.82cm error does not cover later stalls. The owner now completed fresh DLL login/LabExplorer selection/Play and is testing the new deployment. `client-testing/ui_action.py` requires a fresh matching screenshot/checkpoint, correct dimensions, bounded client coordinates and finally-release; older fixed1280 scenarios must not be blindly reused against a different client size.

Latest peer acceptance update: the first new W pulse moved about18m as expected; the second exposed the character falling through the world, so the testing owner stopped the third. The implementation chat is investigating the collision trace and restoring verified ground. This is a peer-reported collision failure, not evidence that dashboard contention explains every remaining problem or that movement acceptance has passed.


## Jump/gravity work queued after loading acceptance, 2026-10-08

Exact PlayerCharacterCF0->6B411A0 multiplies the configured Stats gravity value with active mesh animation modifiers; GetGravityZ560->5EA4B00 also applies engine GravityScale1F0 and PhysicsVolume/PhysicsSettings gravity, plus a conditional falling multiplier throughCF8/6B4D430 and615F770+334. Gravity stat configuration is exact GameStatProfile636A8AD25678/type6A9C0102F8F941C0/cache1530, not a guessed variable name. DoJump770->5EA1480 sets upward velocity to max(current, JumpZVelocity1F8), then Falling3, with additional eligibility, hold/count, gravity-direction and optional horizontal-boost paths. The constructor600 and server900 discrepancy is a lead, not an accepted live coefficient. Native falling integration, jump press/release/apex/landing and slope contact still require comparison.

The bounded `scripts/inspect_jump_gravity_bounded.py` subsequently completed three current723352 receipts outside input leases. Actual jump is900, disproving the constructor600 mismatch for this pawn. Native getter/configuration derives ordinary gravity-1225=(-980×2.5)×0.5, while the reviewed server default is-2450. PhysicsSettings defaults/volume/WorldSettings dispatch, stat cache and value, empty animation modifiers and false slow-fall state are bound in the saved receipts; these are derived getter values, not measured jump trajectories. Separate exact definition metadata proves Replication7/buckets0. CPP staged guarded synchronization and retained900; unchanged-Release Space baseline remains pending. See `JUMP_GRAVITY_PARITY.md` and verified `proofs/current-jump-gravity-review.json` for the full chain, terminal-velocity directional clamp, air-control dependencies, apex split and limits. Lobby travel invalidated the world pawn after the positive W control; require fresh connection/weak bindings for later trials. All research jobs/readers closed before testing re-entry.

The saved loading/show/hide proof is in `LOADING_SCREEN_HOLD.md`; IgnoreMoveInput does not by itself block Jump, and Role1 does not freeze all physics. Third loading trial accepted the31-stage safety gate and immediate earlyW0cm displacement, then post-unlock walking113ACK/0corrections/max0.269645cm. The fixed22s client hold remains; measured39.193s full presentation was not faster than the prior31.559s.
