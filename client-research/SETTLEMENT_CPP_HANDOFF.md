# Settlement implementation handoff

Research owner: Map Ashes of Creation client. Implementation owner: Implement C++ movement compatibility. Input/testing owner: Find Unreal LLM Testing Libraries. Human authorized this collaboration, settlement implementation and documented evidence on 2026-10-08 JST. Research does not edit CPP, send packets or operate the client.

## Exact build and accepted actor

EXE SHA256 `4f1cd43ceeb89190f048734efd4d63152b9f8e11fa31fc41093b0d90f4a1cd43`. RVAs below belong only to this build. Initial accepted empty actor snapshot (historical): PID51076 / creation134358640824425238, dynamic GUID object_id0x54936b40b6795cfe/server_id1/randomizer471624486, native weak index359579/serial71479. NodeGuid0, initialized0, Items0. That lifetime and backend20032/connectionb58666cb47289ca3b2ff8ff4 have ended. Recheck lifetime, GUID and weak identity immediately before any update; addresses/identities expire with the process, connection or object destruction. See acceptance updates and fresh timestamped proofs below; never treat this historical identity as a current grant target.

Read `SETTLEMENT_LOADING.md`, `proofs/settlement-replication-live-51076-134358640824425238.json`, `proofs/settlement-struct-ops-51076-134358640824425238.json`, `proofs/settlement-winstead-capture-decoded.json` and `proofs/settlement-native-verification.json`. Exact original capture SHA256 is1ca8360868dd6c034f0c164c3bb91915ea69ed3b3c52e2950d2d96d20094490d. `scripts/decode_settlement_capture.py` reproduces the complete57269-bit body from frames3876..3883/reliable534..541, with zero remaining bits. Historical dynamic GUIDs and Village3 metadata must not be replayed.

## Fresh one-floor property update

Native matching RepLayout binds **NodeGuid ordinary relative handle25**, Int64Property+500. Matching ClassNetCache binds **LayoutAssetSetGuids custom field13 / FieldMaximum16**. SerializeInt(13,16) consumes4bits. Do not use declaration order, the stat component's cache maximum, or the raw array command handle19 as a custom field.

The ordinary RepLayout segment observed in the capture has checksum-enabled0, packed handles/values, then packed handle0. A minimal fresh ordinary segment is checksum0(1bit), packed25(8), NodeGuid62d024b45678(64), packed0(8): **81bits**. It precedes the custom field in the same actor content block. Use the implementation's proven actor-content envelope, reliable sequencing and current connection identity.

The custom field is SerializeInt13/max16, packed payload-bit-length, then exactly this payload:

| Field | Wire representation | Fresh first-floor value |
| --- | --- | --- |
| SupportsFastArrayDeltaStruct | 1bit | 1 |
| NodeLevel | UInt8 | 1 Crossroads |
| NodeCulture | UInt8 | 0 Kaelar lab profile |
| NodeSeason | UInt8 | 1 Spring lab profile |
| GameplayTagContainer is empty | 1bit | 1; no count or tag bytes follow |
| PlotChangeVersion | UInt8 | 1 |
| ArrayReplicationKey | Int32/raw32 | 1 |
| BaseReplicationKey | Int32/raw32 | 0 |
| Deleted count | Int32/raw32 | 0 |
| Changed count | Int32/raw32 | 1 |
| Item ReplicationID | Int32/raw32 | 1, new positive ID for this empty array |
| OwnerGuid | Int64/raw64 | 62d024b45678 Winstead |
| OwnerSecondaryId | Int32/raw32 | 0 |
| OwnerArrayIndex | Int32/raw32 | 14, the layout prop ordinal |
| AssetSetRecordGuid | Int64/raw64 | 5429e761b0070000 |
| Rotation XYZ | 3 IEEE754 little-endian doubles | 0,0,0; receiver reconstructs W1 |
| Translation XYZ | 3 doubles | 0,0,0 |
| Scale3D XYZ | 3 doubles | 1,1,1 |

Custom payload **962bits** =1+24+1+8+128+800. Custom field header4+16bits, ordinary segment81 → **actor content1063bits**. No invented tag count, four-double quaternion, stat array item layout or custom-field terminator. Metadata choices are an explicit Crossroads/Kaelar/Spring/empty-tags lab profile; ground admits them. Fresh array keys1/base0 are the initial standard delta from an empty receiver, not historical140/70-item replay. Implementation must retain per-array state/IDs for future changes rather than resend the initial delta as progression.

Native dispatch `44E4620` reads SupportsFastArrayDeltaStruct into delta params+4F for protocol custom version>=11, then obtains UScriptStruct+D8 and invokes CppStructOps vslot58. Fresh NodeLayoutAssetSetGuids vtableB49C8D8 slot58 is5B76490→5B7E440. That serializer writes level/culture/season, calls39F65D0 for tags, writes version, then tail-calls5B77280. 39F65D0 serializes `(TagCount==0)` as one bit; count/tags follow only for nonempty containers. Native5B7E610 proves four raw32 array headers/counts. Generic5B77280 creates stride90 items, reads ID32 and invokes the reflected item serializer callback. Fresh DeltaFlags+100 are0, selecting the standard full-item path rather than5B78DF0 alternate delta support.

Quat CppStructOps vtable9E8EDA0 slot50 is16C7780→1438440. It has version-dependent float/double paths: version>21 except26 reads XYZ as three doubles, matching all70 captured items; loading reconstructs positive W=sqrt(1-XYZ²), with an overlength normalization branch. Saved constant9DDB290 is double1. Identity needs no sign/normalization ambiguity. The compound ID and translation/scale fields are corroborated by native item RepLayout and100-byte/800-bit complete capture item boundaries.

PostNetReceive65A9260 sets initialized+508 and invokes OnRep65A8F40 when NodeGuid is nonzero. OnRep resolves the assetset/filter graph and async load; no manual OnRep call or process write is needed. Constructor thunk5B79900 is the complete20-byte null-guard/argument-rearrangement/JMP wrapper, already corrected by CPP. Keep exact constructor/lifecycle guards.

## Correct floor placement and server collision

Node62d024b45678 / Verra_RVR_Winstead, Layout5429e7362f260000 / Layout_Flat_D, prop14 assetset5429e761b0070000 / NS_Flat_D_Master_01_Landscape. Riverlands14 selects definition5429e761b0070001 / Landscape_Flat_D_Master_01, exact path:

`/Game/ENV/Nodes/Nodes_Master/Node_Sublevels/Landscape_Platforms/Layout_Flat_D/Landscape_Flat_D_Master_01`

World origin(cm) **[-644519.105296,376773.237813,12012.231952]**, rotation(pitch,yaw,roll degrees) **[0,-40.79154,0]**, scale[1,1,1]. Prop/item, asset-definition tuple and contained instance are all identity. Native6588CD0/65A25A0 compose these transforms and explicitly fetch CityNode origin/rotation. The historical actor spawn location[-641389,377367.1,13841.8] differs and is not this ground origin. 6578B20 binds actual Engine.World dispatch; 4189470 creates ULevelStreamingDynamic, requests load/visibility and priority1000, then65A1430 receives loaded callbacks. Ground applies at levels0..6, including Wilderness.

CPP candidate decoded-world manifest SHA2565256a4abeb79200551495e72f990929de125b8f4b4d37faa080dd37360bb8efc; isolated256 tiles. Research inventory independently checks512height/material buffer hashes and764303solid cells. CPP collision-metadata.json reports256Landscape components/collision enabled/no overriding BodyInstance settings. Do not admit all5257 other-world tiles at local origin, or turn material255 holes into solids. CPP's capsule-preview.json finds support across the recorded seam, but that is offline evidence, not live acceptance.

## Required observation and rollout

First bounded one-floor update on the accepted actor: verify NodeGuid, initialized1, Items1, exact compound ID, reconstructed identity transform and metadata1/0/1. Then prove the exact streamed World package becomes loaded/visible at the native origin/yaw and provides pawn collision. Testing owner retains exclusive input, verifies native floor contact and a bounded traversal across the known gap. CPP admits the matching world-transformed collision candidate for that accepted instance. Record connection/lifetimes/packet and movement results; do not call decoded items alone a collision pass.

Only then roll out eligible exact-world node placements using `proofs/settlement-placement-catalog.json` / `catalogs/settlement-locations.csv`. There are81 definition records,46Verra records and44valid nonzero layouts, including non-settlement POIs/harbors. Do not spawn zero-layout/origin records as settlements. `proofs/settlement-tier1-services-catalog.json` resolves125tier1plots across those44layouts without missing references. Culture, season, tag filters, node purpose and actual building state still control selection. Winstead's4plot defaults are one Operational2 node-type building and3UnderConstruction1 projects; names alone do not select the node-type variant. Full service-building ownership/producer lifecycle and static mesh collision are outstanding research, so the first floor is not a completed all-settlements implementation.

## Acceptance update

The initial51076 actor expired; CPP rebuilt/restarted and sent the reviewed update on76232/creation134358660541395868/connection7179becb12fbae5bd5dc1286, freshGUID39EA87566AD07426/server1/random2464315690/index359620/serial71692. Independent native readback proves correct initializedNodeGuid/profile/item and **loaded/visible floor at exact origin/yaw/unit scale**. `proofs/settlement-floor-observation.json` has full reflected offsets/masks and timestamped copies. Nativecontact/traversal and all-location rollout remain outstanding. CPP's privatecollisionadmission guard has been factually reviewed against that proof.

Correct SoftObjectPtr innerlayout is WeakPtr8/ObjectID+8, not+16. WorldAsset+48→packageFName+50/assetFName+58. WorldAssetpackage includes nativeinstance suffix; sourcePackageNameToLoad+7C stays exact. Match actualLoadedLevel+1A8/outerWorld/outerPackage against the softpath, currentOwningWorld and actual Level.bIsVisible+260mask20. World.StreamingLevels+B0 and LevelTransform+B0 are separately reflected fields on different classes. Requestflags+118/masks10+8 are not actualvisibility. Live native streamingstate+138=6. The first wrong soft-inner scratchdecode is retained/corrected in the journal; no CPP guard used it.

For subsequent rollout use `proofs/settlement-crossroads-profile.json` (318filteredprops/44layouts,13Winsteadslots) and `proofs/settlement-landscape-instances.json` (26floorinstances/12packages/6144bufferhashes,6nonzeroRiver_C localtranslations,18no-selected-landscape). Do not force identity translations across other nodes. For nonidentity mesh/service quaternions, implement native normalization and W>=0 sign canonicalization before writingXYZ; simply dropping a negativeW changes orientation. All48historicalprops match actuallayoutindexes/fulltransforms up to quaternion sign. The22serviceitems match actualPlotIDs/plottransforms/buildinggroups, but SecondaryId2 spans construction/operational groups and is notEBuildingState2. NativeRoadBase initialization and actualAoCNodePlotComponent initialization are separately bound; the client Exec SetNodePlotState is an empty stub, so it cannot recover the serverstateproducer.

### Collision-enabled lifetime and first movement pulse

The 76232 lifetime above has ended. On PID115896 / creation134358667522731418, connection932b04cfcb0bb267473947c3, fresh GUID54c9da41a1f45322/server1/random2479824626 resolves to actor359617/serial71493. The independent timestamped native floor proof `proofs/settlement-floor-observation-115896-134358667522731418-1791393516491248000.json` confirms the same exact item and loaded/visible placement, streamer361021/71528 and loadedLevel361025/71533. CPP Release SHA256df87f29337eda95f62e224b5ff7c5c73c7727d6af817a2bfc509aca979a752d8/backend63248 admitted 256 tiles to this player's private collision world (2925 total/base2669), without changing player state. Stale-lifetime and duplicate attempts were refused; CPP owns `runs/settlement-probe-20261008/collision-admission.json` and the refusal artifacts.

Testing's first W-only two-second pulse (`client-testing/runs/traversal-083c6ff6b8fb4b82ac174695d74153c9.json`) moved 12.099m to X-679290.0668/Y406500/Z12506.8583, with all14 native samples walking and final velocity/acceleration zero. Its native floor was still base Verra, not the settlement platform. CPP's bounded trace review `CPP/runs/character-movement-followup-20261007/winstead-floor-pulse1-window.json` reports35 new ACK/0 corrections, maximum prediction error0.26065cm, no time resolution;28 ACK were during movement. Three initial corrections occurred before this pulse and must not be attributed to it. This is approach acceptance, not gap-crossing acceptance. Only testing owns input, and CPP releases each next pulse after reviewing the previous trace.

### Seam accepted; next implementation evidence

Independent `proofs/settlement-traversal-review.json` now joins all3W2s pulses and saved native/server rows:43groundedsamples,106newACK/0corrections/0resolution,maxerror0.260647616cm,total36.179635m. Pulse2 and3 CurrentFloor outer chains match the exact accepted LoadedLevel361025/71533; pulse3 passes formerlossX-677940 toX-676882.0365 with finalclient/serverheightdiff0.010111cm. DLL controls are released/lease revoked. These are bounded route observations, not all-location coverage. CPP owns making Winstead setup automatically repeat after future login and verifying a fresh lifetime; research does not author its source or manual stages.

For the subsequent nearby/relevance-aware floor rollout, **`proofs/settlement-platform-metadata-review.json`** adds archive/native-default collision readiness for all12packages/3072components, no disabled actors/BodyInstance/template overrides. The reader invocation/source/binary/mappings hashes and log are saved in `proofs/settlement-platform-metadata/`; no CPP files or live client state were modified. Combine this with **`proofs/settlement-landscape-instances.json`** (26exactplacements and6nonzero item translations) and **`proofs/settlement-platform-collision-inventory.json`** (6144bufferhashes). Keep each admission bound to a fresh received item, actual loaded/visible level, matching transform and connection; static readiness is not a live grant for25otherinstances. Preserve per-node array IDs/keys, relevance/teardown and duplicate guards. Do not load every platform globally. Class-default cull radius is approximately2.1km, not a recovered complete official activation policy; any chosen lab activation radius must be documented as such.

Full Crossroads content: `proofs/settlement-crossroads-profile.json` has318props/44layouts and correct compoundIDs/full transform chains; `proofs/settlement-tier1-services-catalog.json` has125plots. Nonidentity quaternion sign canonicalization remains essential. Other18layouts may have base/staticmesh/World ground and require their own inspection. Authoritative service progression/ownership/state selection and staticmesh collision export remain explicit research gates before calling these completed tier-one settlements.

Additional service-state boundary: `proofs/settlement-plot-state-stub.json` verifies the direct658B71A CALL to shared131C360 (33C0C3, XOR EAX,EAX; RET). Its null result prevents658B600's nonnull success branch at658B9D1 from reaching the conditional plot-map/component initialization in this shipped build. Do not interpret the saved success-path pseudocode as a recovered functioning server node lookup. SetNodePlotState's separate131C2F0 empty stub is already verified. Neither routine was invoked; definitions/captured compound ownership remain useful independent inputs.

### Fresh automatic-login acceptance

Automatic Release894a1432bcae81779115a6042132706a5f1a9ee418641aa7b975faa58482d665/server60080 enables initialize_winstead_floor. CPP `runs/settlement-probe-20261008/automatic-world-verification.json` records21stages/private2925tiles/no manual floor commands on client115060/creation134358682868627251, connection984e00ca99d53aef4ab769f1. Independent research1791394996/4999 read confirms freshGUID2aecfb28364cf71a/server1/random3103122797/actor359614serial71491, correctinitializedWinsteaditem/profile and exactloadedvisiblefloortransform: streamer362259/71522, loadedLevel362263/71527. Immutable115060 replication/floor proofs are saved, and aliases updated. All prior115896 actor addresses/GUIDs are expired; its acceptedthreepulse route remains historical evidence. This fresh run proves automaticsetup, not a fresh movement pulse or all-node rollout. Remaining26-placement handoff stays this research chat's broader objective; existing CPP movement chat's immediate scope is accepted automaticWinstead plus its movement issues.
