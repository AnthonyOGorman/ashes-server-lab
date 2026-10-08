# Jump and gravity compatibility: current client evidence

Updated 2026-10-08 JST. Loading safety is accepted for the tested path; jumping/gravity is active. CPP owns implementation and testing owns all input. These findings use executable SHA256 `4f1cd43ceeb89190f048734efd4d63152b9f8e11fa31fc41093b0d90f4a1cd43`. Both initial client723352 and first gravity-fixed client518960 lifetimes are now historical. The gravity-only comparison is still pending a fresh restart, possession/profile/readiness and Space receipt.

## Confirmed sampled profile

Three bounded read-only receipts are saved as `proofs/jump-gravity-live-723352-134358967749612155-*.json`; the most complete is `...1791424144290339300.json`. Each verifies the CPP seed's client proof, positive actor/component weak serials, mutual acknowledged possession and exact gravity/jump dispatch slots; each closes its reader. Reads were280,080/280,224/289,367bytes, under a4MB limit, outside exclusive input trials. No object scan, native calls, input, packets or writes occurred.

| Parameter | Actual sampled value |
|---|---|
| JumpZVelocity | **900cm/s** |
| Movement GravityScale | **2.5** |
| WorldGravityZ / PhysicsSettings DefaultGravityZ | **-980cm/s²** |
| Configured character gravity stat | **0.5** |
| Active animation modifier array | **empty** |
| Slow falling | **false** |
| Gravity direction | **(0,0,-1)** |
| Physics-volume terminal velocity | **4000cm/s** |
| JumpMaxHoldTime / JumpMaxCount | **0 / 1** |
| ApplyGravityWhileJumping | **true** |
| DontFallBelowJumpZVelocityDuringJump | **true**, but hold force currently0 |
| AirControl / boost / boost threshold | **0.2 / 2 / 25cm/s** |
| Falling lateral friction / braking | **0 / 3000cm/s²** |
| Braking friction factor / separate braking | **1 / false** |
| Maximum substep / iterations / apex attempts | **0.05s / 8 / 2** |

The native constructor's600 jump velocity is overridden on this live pawn. **Do not change the server to600**: its900 default matches the live value. The earlier constructor discrepancy was a research lead, now disproved for this profile.

## Gravity getter chain

Movement vtableB110970 slot560→**5EA4B00** calls base**3DDFCB0**, which applies Movement.GravityScale+1F0 to**3E43260**. Its588 physics-volume dispatch is freshly bound to**3E46DD0**. The non-null UpdatedComponent+108 path tail-calls SceneComponent getter3E93500; the fallback selects World.DefaultPhysicsVolume+170. Current UpdatedComponent/UpdatedPrimitive both match the root capsule; its positive weak PhysicsVolume identity is the current DefaultPhysicsVolume.

That volume's840 getter→**441E300** delegates to the current WorldSettings840 getter→**47BAD50**, or PhysicsSettings defaults if no world is available. Current WorldSettings raw+376=8 means cached-gravity bit0 and global-override bit1 are clear. The saved complete128-byte getter has the default path: obtain PhysicsSettings CDO, read+58, store WorldGravityZ+3F0 and return. The factory is **43F8F80**, not443F8F80; its exact MOV at43F8F87 resolves class globalD855F10. Fresh class/default ownership and reflected DefaultGravityZ+58 establish **-980** for this path and fallback.

Custom5EA4B00 then calls owner slotCF0→**6B411A0**. Native configuration resolver60ACCF0 selects GameStatProfile636A8AD25678/type6A9C0102F8F941C0; cache+1530/+1538/+1540 binds **GravityScale5429E5E8643F0018/type4A74AE5ED850DC97**. HasStat61286D0 finds its type0 StatsInt32 entry. GetStat60F2950 reads **entry+12**, not base value+8, and6175EC0 reinterprets those integer bits as float. Fresh entry values are base0/value0.5/min0/max0. The mesh AnimScriptInstance native modifier arrayB8/countC0 is empty, so no extra active entries multiply the value.

OwnerCF8→**6B4D430** dispatches to Stats**612DAE0**. Its exact complete8-byte leaf `0fb68144080000c3` reads Stats+844 and returns. This matches reflected bIsSlowFalling=false, so the conditional615F770+334 falling multiplier is inactive in the sampled profile.

Thus the getter-derived ordinary gravity is **(-980 × 2.5) × 0.5 = -1225cm/s²**. This is a derived current-profile value supported by native dispatch and readback, not a direct invocation of GetGravityZ or a measured falling trajectory. It must be corroborated with the bounded jump/fall samples before claiming movement parity.

The reviewed server Movement default gravity remains-2450, and its configure method changes speed/toggles rather than applying this gravity stat. The CPP owner must confirm actual current player configuration/trace values and synchronize the server to the same profile. `speed_sync.cpp` already validates the gravity stat's replicated item identity, but that alone is not an assignment to Movement.gravity.

For an ideal stationary launch900 with constant gravity and no contact/hold/root-motion modifiers, `time_to_apex = 900 / abs(gravity)` and `rise = 900² / (2*abs(gravity))`. The derived native profile predicts0.734694s/330.612245cm, versus0.367347s/165.306122cm with the prior server default. These are analytical expectations for the baseline, **not measured trajectories**. They show why the coefficient can cause major vertical divergence even when walking agrees; collisions, substeps and actual native jump handling still require the before/after trial.

## Native falling behavior and remaining work

Focused batch `falling-gravity-parity` saved4 decompilations/exception fragments: volume441E300, HasStat61286D0, GetStat60F2950 and PhysFalling**5EB6250**. The Ghidra project completed and closed before the next input lease. PhysFalling is1459 pseudocode lines and is being reviewed, not fully replicated merely by successful decompilation.

It evaluates falling lateral acceleration via slot878, limiting via880, CalcVelocity7E8→5E9AA10, gravity560, NewFallVelocity7D8→3DE88B0, braking810→5EA51D0, hold-force time+530 and an apex split/retry path. It integrates a gravity-direction vector, separates vertical velocity for planar integration, sweeps the capsule and processes landing/step/slide paths. Fresh direction is ordinary down; other directions and active modifiers are untested.

The reviewed lines455..476 compute displacement from the average of old/new velocity times the substep, with a separate no-gravity hold-force split. This supports retaining the existing vertical trapezoid formula for the current stationary ordinary-gravity/no-hold/no-root-motion baseline. The apex path at352..425 detects old upward motion becoming nonpositive, derives time to apex from the measured velocity change, zeros the gravity-relative vertical component, refunds the unused portion of the substep and increments the attempt counter while retrying without consuming another iteration. Exact helper thresholds/constants remain to be pinned; the2-attempt cap is freshly read. Do not replace the correct900 launch or trapezoid formula just because the constructor/default lead differed.

Replication scope is now independently captured: `proofs/gravity-definition-live-723352-134358967749612155-1791424907151261000.json` verifies the current design-manager weak identity, exact profile/cache/definition identity, **Replication7**, buckets flag0 and raw246..247=`0700`. The reader closed after1760bytes/0.414s. This record-only receipt followed travel to Character_Lobby; it does not revalidate the expired world pawn. The CPP owner restored a strict7 guard for this exact configured gravity record. EveryoneProxy alone did not establish that literal: saved native routing maps1→Owner,4→ProxyOnly,5→OwnerProxy,6/7→EveryoneProxy. No new stat grant or packet routing follows from the read.

The saved `falling-air-control` batch completed four targets and11 exception fragments, then saved and closed the project. **NewFallVelocity3DE88B0** first adds `gravity * positive_dt` to velocity. If speed exceeds the absolute terminal threshold, it tests the component along normalized gravity and caps only that component, preserving the perpendicular component. It does not clamp the whole velocity vector to4000. **ShouldLimitAirControl3E04FB0** checks whether acceleration projected perpendicular to GravityDirection is nonzero. **GetFallingLateralAccel3DDFA30** projects acceleration onto that plane; outside root-motion override flag+F50 it dispatches slot888 with AirControl+300, then clamps to slot808 maximum acceleration. The slot888 boost/coefficient implementation remains unresolved: the sampled0.2/2/25 values are not a complete air-control algorithm. Requested3DE2380 and5EA51D0 have no indexed root exception range; the missing entries are preserved, with no invented boundaries.

Custom **GetMaxSpeed5EA5370** retains direction/mode/walk-state/stat selection through movementCD8→**5EA2150**, followed by cached owner, optional cap, effect, movement and material multipliers. The saved selector substitutes owner+1321 when current MovementMode+281 is Falling3; previous modes1/2/4 dispatch through the corresponding mode table, with other previous values falling back to ground walk/run selection. A ground-launched jump therefore does not simply use MaxWalkSpeed220. See `MOVEMENT_NETWORKING.md`, “Actual speed is a selection plus modifiers,” and saved movement/function_5ea2150.c/function_5ea4b90.c. Fresh mode/owner identities and effective values still need trial correlation.

The post-unlock W positive control completed: about12m,28moving moves among113new moves,113ACK/0corrections/0resolution and maximum error0.269645cm. The client subsequently traveled to Character_Lobby and closed its connection; the reason remains undetermined. CPP/testing are arranging re-entry on unchanged Release48F210 before the stationary Space baseline. No research readers or Ghidra jobs remain open during that window.

The current server falling branch uses full planar acceleration and lacks native falling braking on the zero-input branch. This differs from the sampled AirControl0.2, boost2 below25, falling friction0 and braking3000. Jump initiation, count/hold/release, per-step apex handling, terminal velocity, floor distances and contact/landing time must also agree. Gravity parity alone does not prove slope/step-up/collision parity.

The next coordinated baseline should first prove that the same input path moves after unlock, then use one stationary brief Space press/release. Compare native/server vertical position and velocity over launch, ascent, apex, descent and landing; record corrections, compressed jump flags, move timestamps/deltas, contact identities and final release. With JumpMaxHoldTime0, the first trial should not assume a variable-height hold mechanic. Preserve the existing accepted walking behavior. No Space or Shift trial has been executed by research.

Shift sprint remains unverified: MaxSprintSpeed750 is a parameter, not proof that pressing Shift is accepted or that a sprint ability is granted. The armor hypothesis remains unproven.

## Stationary baseline and gravity-only deployment

The unchanged Release48F210 re-entered on connection69fd7994c2817b9439dddb46 using the same client723352 lifetime, but a fresh world pawn/controller. Testing's0.104942s acknowledged Space pulse completed with controls released. `proofs/stationary-jump-before-review.json` independently joins immutable native artifacta97d3841/native-review48d8b2c4/CPP `stationary-space-gravity-before.json`. There are37native samples,5Falling, and sample intervals0.10893..0.19028s. The maximum **sampled** rise is174.124290cm; velocity at that sample is still+275.238cm/s, so it is not the exact continuous apex. Later server corrections also alter the client trajectory. Final landing is within0.001134cm vertically of the initial position, with noXY motion, Role2/Walking1/counter0 and blocking/walkable/nonpenetrating floor.

The full server window has56new moves/52ACK/**4corrections**, max19.96533664cm, zero time-resolution moves. Independently deriving `(VZ_after-VZ_before)/simulation_dt` on unobstructed nonlaunch falling rows gives median **exactly-2450cm/s²**. This establishes actual running-server gravity rather than merely its source default. It does not measure the client getter through an uninterrupted trajectory, since corrections occurred.

CPP deployed a **gravity-only** fix in Release8a657da7c3fa57fbb4659291c931fb51c4090b44e95046551f9f6510161a7364, first backend507432/creation134359000705167547 and client518960/creation134359000998546045. The owner reports five Release suites passed, owner+1300==current pawn/cache/scope7/ordinary down/no animation modifier/no slow fall guards, jump900 retained and air-control algorithm unchanged. Testing saved `client-testing/runs/resume-readiness-cba7327454cd418793e448f57f494b92.json`: connection5dc7f320dbb287bf0c17fc3b, all31stages, setup profile-1225/jump900,45.171s stable idle and visible grass/HUD/no overlay. **Both processes subsequently ended before an after-fix Space artifact was saved.** Root is restarting the same tested Release for a fresh comparison. Setup acceptance is not trajectory acceptance, and neither old lifetime may be reused. Research remains closed through fresh entry and Space.

Additional released static subset saved `proofs/falling-helper-leaves.json` and `decompiled/falling-air-coefficient/function_3ddc2f0.c`; Ghidra completed/saved/closed before the new client input window. Slot888→**3DDC2F0** delegates nonzero AirControl to slot898→**3DC5320**, then scales projected acceleration. The898 boost helper remains unreviewed. MaxAccel808→**5EA51C0** is a10-byte taildispatch toD60→**5EA6560**, a previously saved getter: use MaxAcceleration+2DC unless enabled stat flag1190/validowner/stats selects configured stat1198. A future moving-jump profile must bind this flag/stat/effective value, not assume the raw field.

The exact saved braking jump table binds mode3→**5EA51F9**, complete9-byte `MOVSS[rcx+2F4];RET`, corroborating reflected BrakingDecelerationFalling3000. Missing exception ranges are retained as missing; selected leaves do not invent them. The3DE2380 selected leaf computes `dt=min(MaxStep,remaining*0.5)` only when remaining exceeds MaxStep and iteration count is below MaxIterations; otherwise it uses remaining, then clamps to approximately1e-6. Apex code uses absolute gravity-relative net acceleration>1e-8, float time-to-apex>=approximately1e-4 and less than the current substep, with the sampled2-attempt cap. Mutable apex-enableD26EE98 is **on-disk1 only**, not a fresh runtime value. These refinements support later air/landing work; they were not silently added to the first gravity-only comparison.
