# Exact-client loading screen hold and release

Updated 2026-10-08 JST. This research belongs to the first ordered goal in `LOGIN_AND_MOVEMENT_GOALS.md`. CPP/backend/dashboard/input-adapter changes belong to **Implement C++ movement compatibility**; live input belongs to **Find Unreal LLM Testing Libraries**. Research performs static analysis and coordinated read-only observations.

## What improved and what remains

The second fresh trial used client579760/creation134358951827478205 and CPP ReleaseD360FF5D2F217BDFC87E1D2E9B3464969134F8C5D35AD4AA40F8BCA49C12A6F6, connection edb5d1554f27e7151b30d9b9. Post-possession input relocking, early node dispatch, settlement floor/collision admission, appearance and native autonomous walking/floor contact passed. Bootstrap→WorldReady was13.564129s; bootstrap→world_initialized was13.570751s, compared with the historical approximately40.809s initialization baseline. These are server/native endpoints, not time to the visible game. Only one new timed trial establishes this improvement.

The same client's game log shows the separate UI delay:

| Event | UTC timestamp / seconds after Play request |
|---|---|
| Play requested | 01:08:31.444891 / 0 |
| Native WorldReady | 01:08:49.165228 / 17.720338 |
| HideLoadingScreen | 01:09:02.974 / 31.529109 |
| Post-hide `Visible for 28 seconds` | 01:09:03.004 / 31.559109 |

The overlay remained for13.838772s after native WorldReady. It used a22-second client record timer that starts after the client loading prerequisites clear. The timer overlaps some server initialization; it is incorrect to simply add22s to the13.6s native duration. The independent screenshot at01:09:02.121 still showed100%/final touches, consistent with the later native hide log. Subsequent screenshots showed the pawn and terrain.

CPP is implementing **GameplayPresentationReady** after native movement readiness and before input release, using the owned current-run post-hide log scoped to current welcome/Verra map completion. This staged change and its third fresh trial are separate from the accepted second native trial. An early W test must prove the final gate in a coordinated input lease. Jump is not blocked merely by IgnoreMoveInput, and Role1 is not a complete physics freeze.

## Data record and native timer

All native RVAs below belong to executable SHA256 `4f1cd43ceeb89190f048734efd4d63152b9f8e11fa31fc41093b0d90f4a1cd43`.

`650ED60` evaluates real loading prerequisites, then resolves `AoCRecordConstants` CDO through class getter5BE9520/globalD8FC150. It reads **LoadingScreenDataId+610**, resolves record type01FE2A2ECEF1BE39, and reads **LoadingScreenHoldSeconds+88**. Manager+130 stores a double QPC timer start; a negative start initializes to current time. Hold<=0 or elapsed>=hold exits the hold branch; otherwise it reports “Holding loading screen for final touches.”

The small read-only snapshot `proofs/loading-hold-live-579760-134358951827478205-1791422307694740200.json` independently validates exact class/CDO/property ownership, positive design-manager weak serial and record/hash identities, then rechecks lifetime and values. It read31,493bytes and closed its reader. The selected record is **5429E6B0C6C00000**, nameLoadingScreenData_6064632020154187776. Values: Hold22.0/Hang0.0/HeartBeat2.0, four force flags1. Only one record of this type was loaded. The initial expectation of `IntrepidSettings` was rejected by the class-name assertion; the verified class is **AoCRecordConstants**.

LoadingScreenHoldSeconds is an **Edit/BlueprintVisible record field, without Config**. LoadingScreenDataId is a Config selector. No supported shipping-client INI/CVar/data-record override has been established. Setting an invented INI HoldSeconds line or zeroing the record selector is not a valid demonstrated fix. SDK DesignDataPlugin exposes an EditCache and provider callback, but no validated runtime override API. Native104ACD0 constructs a DesignDataCache name; it is not evidence of a record override. LoadingScreenHangDurationMultiplier affects a separate hang-duration path, not the22-second hold.

## Native presentation state

**Manager+E9 is the showing byte. +EA is different and must not be used as the showing flag.**

Show650FFC0 requires a valid selected record and E9==0. In the ordinary viewport path it creates/attaches Widget+70, writesE9=1, broadcasts manager+58(true), and records show-start+ C8. Initial movie-player paths remain separate.

Hide6504FF0 returns without dismissal whenE9==0 or when the initial movie-player loading screen is still active. In the normal hide path it performs65010920, GC, removes widget via467CCBC0, clears Widget+70, releases viewport state, broadcasts manager+58(false), then clears both E9..EA. The `Visible for` log at6505184 occurs **after** these operations. Therefore an owned current-world/current-run post-hide log is a defensible fallback predicate; a matching stale title-screen log is not. Widget pointers alone, actor visibility flags, possession, asset counts or WorldReady alone do not prove a clear game screen.

Requester650F9E0 also checks manager+88 weak requester objects, current-world level script actors and their subsystem objects using IntrepidLoadingScreenRequesterInterface+10. A requester returning true keeps a reason and blocks release. Register/Unregister are local functions. AoCPlayerController.OnLoadingScreenVisibilityChanged is **Final/Native/Protected**, not a NetClient RPC: thunk5D42C20 calls6AD83A0, which handles local CVar/character/HUD work. No existing server RPC for constructing a loading requester has been verified.

The visibility callback has no direct ignore-counter write/reset or SetIgnoreMoveInput call. Its56F0E70 guard checks NetMode3 (or Standalone0 if explicitly allowed), not whether the controller is locally controlled. On false, it can call character6B30FD0 and controller5D1AC10. Selected saved bytes show6B30FD0 dispatches character vslotsF30/F38 and conditional5D7A5A0/6B57F60;5D1AC10 is a reflected event wrapper using global nameD914DE0 and virtual ProcessEvent2E8. These transitive callbacks have not all been resolved. Therefore survival of counter1 through hide must be observed in the third trial; a direct-call-only absence check is insufficient. `proofs/loading-visibility-callback-leads-targets.json` preserves two exception ranges and the missing6B4D080 range without inventing a boundary.

The third session is CPP Release48F210F907F739FF27EB1D0F8A46D6D993D18DA76B4DE563655FF80257FAA941, client723352/creation134358967749612155. The owner reports31 stages, bounded GUID refresh and five passing test suites including current-world/stale/partial loading-log guards. The UI/input owner has an exclusive automated-entry/early-W lease; research performs no native reads/heavy jobs during that trial. This records release, not acceptance. The previous579760 record snapshot is historical once that lifetime is retired.

## Saved evidence and limits

`scripts/verify_loading_screen_hold.py` verifies11 decompiled outputs and21 exact exception fragments, selected record identity and saved second-trial endpoints. Receipt: `proofs/loading-screen-hold-review.json`. It snapshots the changing game log under an immutable SHA256 filename. An initial strict JSON parser rejected malformed unrelated log lines; the corrected reader records those line numbers, rejects malformed loading records and preserves the raw snapshot. This does not change any game log.

Ghidra outputs are saved under `decompiled/loading-screen-hold`, `loading-screen-config`, `loading-screen-state` and `loading-screen-show-hide`; each project job completed and closed before the next input trial. Indexed string-only searches missed indirect logging metadata references; `scripts/inspect_loading_state_refs.py` preserves the bounded instruction review that recovered show/hide references. Discovery queries in `proofs/design-data-override-leads.json` do not prove absence of every override path.

The third trial subsequently passed the new UI gate and early-input test: `client-testing/runs/loading-review-43cbbe4fb2b947a3b9582d80b7995795.json` preserves201outer observations/15earlyW samples, all early samples Role1/counter1/zero velocity and0cm displacement for2.0228057s. Native Role2Walking/currentcontact appeared17.094s after Play with counter1; post-hide receipt39.193s after Play preceded observed unlock (last1 at3529.748282, first0 at3530.263371). Screens bound first clear pawn/HUD/terrain38.867..40.245s; final sample45.373s grounded. This confirms counter survival through the actual hide callback for this trial, not every transitive callback in all profiles. Post-unlock W later moved about12m with113ACK/0corrections/max0.269645cm.

Loading safety is accepted for this path. **The measured39.193s full presentation is not faster than the previous31.559s**; the fixed22s native hold remains and no supported override has been found. Native/server initialization improved to approximately13.57s in the prior corrected trial. The old exhaustive client-mapping goal remains paused. Broad settlement building/service-state coverage, jump/falling parity, slopes and sprint remain separate required work. Later lobby travel/connection closure requires fresh world bindings before further movement trials.
