# Active checkpoint â€” 2026-10-06

The user explicitly resumed work and asked to focus on character movement.
No developer EOS access is available; the user reports the game is end of life.
The active goal is a properly spawned character with working UI, a loaded and
visible world, and verified fresh-input movement on our own local server.
Character/UI readiness and world streaming/visibility are explicit prerequisites.
Use the existing attached input adapter; computer use is optional inspection.
The exact packed move codec is implemented; server handling remains unfinished. Launcher investigation is
complete and deferred. Do not disable security checks or fabricate credentials.

Normal desktop helper11072 serves http://127.0.0.1:8765; client56180,
session92e21f044c62. Latest world epoch3 is connectionf2c6093403ab83e420425d64,
peer127.0.0.1:64638, started1791286976.879, NOW CLOSED at12:02:57-59UTC.
Epoch3 returned to lobby after about20minutes despite both PlayerState links.
All epoch3 addresses below are now stale. Recheck active state and identities
before actions. Both previous pre-BeginPlay scenes returned to lobby after about
20 minutes; cause unverified. Authentication refreshes continued normally.
Epoch3 accepted HUD, mutual possession, Controller.PlayerState and
Pawn.PlayerState via separately guarded one-shot server properties. PawnRole1,
GameState BeginPlay false. No walking proof or new BeginPlay trial. Never run a
character-selection scenario while world_entry.active.
All fixed one-shot proof snapshots expire after180 seconds.

Epoch3 current PC0x18ed1b20040, pawn0x18e68bd8020, PS0x18f9d7edb80,
GS0x18ebfe78040, HUD0x18ec5504930. These become stale on world teardown.
Read-only proof confirms same PlayerState on PC and pawn and camera ViewTarget.
Body remains tiny SK_PC_MASTER; appearance Skeleton/CharacterCreatorSubsystem/
MergedMesh null. HUD actor exists, gameplay widgets not visible.
WorldSettings.WorldPartition resolved; streaming/source enabled. All556 current
streaming levels loaded and visible. Runtime-cell inventory associates all556:
503HLOD +53detail cells across MainGrid/Landscape/Foliage/Water/Corks; detail
ContentBounds overlap the spawn. This does not prove actual render detail ready.
Camera location[-661184,389360.3,13702.9], target actualpawn, cache timestamps
advance. D3D12/SM6, ordinary qualitysettings; no dx11/nullRHI launch override.

New lab/pawn_player_state.py fixed handle21, raw known128-bitGUID, guarded actual
Pawn.OnRep virtual870=433c720 ->4345050 setsPS.PawnPrivate and broadcasts;
actual finalvirtual830=131c2f0 is RET. PlayerState SetPawn4437760 and delegate
441b9c0 decompiled. tools/inspect_pawn_player_state_receiver.py binds current
actor+property+native target+bytes before dispatch. Controller linkhandle19
notification3eebc80 ->PS44119c0 ->SetOwner3b8f7b0 reviewed and accepted.
tools/create_client_restart_experiment.py and lab/unreal.py support these two
fixed commands with fresh proof, same-peerGUID and consumed-nonce guards.
Full suite134 tests passed. New observer tools inspect worldsettings, camera,
runtime cells and appearance virtual targets without invoking client functions.
Fresh W0.5sec after both links and PawnAutonomous run8b911b9176e449dea814b7c3b13d353b
sent/released input;003-position-comparison.json proves position unchanged.
No epoch3 pawn_movement_rpc_observed events. Role/lifecycle remains blocking.

Latest controller RPCfield791 is ServerRequestClientLoad, empty arguments;
exec5d59d30 validatesvirtual21c0=c8ab00 and impl21c8=131c2f0 RET in this shipping
client. It does not establish an expected server response. ClientInitializeCharacter
exec5d2d010 ->actual21d0=6a99a30 tests3b7fdb0 then tailcalls58e9330 UClass getter;
this apparent stub cannot be treated as a full initialization response.
Appearance OnRepCustomization exec5980430 ->5ff2dd0 ->virtual688 actual5ff7e70
branches on client/netmode predicate56f0e70(owner,1), assembles through
5ffc2f0/virtual680/5fd2f10/virtual690. Full follow-up dependencies and component
custom serializer remain unresolved. No appearance packet authored yet.

Offline continuation found25 EPlayerLoadCheckpoint booleans (SDK enum1747):
0LoadStarted,1LoadCompleted,2Information,3Location,8Actionbars,9Equipment,
12InGameSettings, others ordinary persistence. Getter6ac1000 boundschecks the
bytearray atPC+3158/count3160.6ad2140 readsindex1;6ad2160 readsindex0.
LoadTracker63e7600 ->63d5eb0 serializes6-bit count<=25 then32-bit UEbools.
Do not fabricate all-complete markers; missing actual initialization remains.
Character identity/name/race/gender actually replicate through existing
CharacterInformationComponent (BaseCharacterInfo) atBaseCharacter+7c8,
UCharacterInfo/derivedPlayerCharacterInfo fields118GUID,130name,150race,
151gender,154serverID,158level. Capture exports pawn925a6 component925aa,
pathBaseCharacterInfo checksum2952361071 no_loadtrue; these GUIDs are historical.
Next investigate fresh component identity, name/class/checksum and explicit
same-pawn defaultsubobject export, then emptyproperty content to initialize its
current classcache/RepLayout before actual own-character data.
NativeReadContentBlockHeader3f2c340..3f2da31 reviewed:HasRepLayout bit,IsActor bit;
subobject knownGUID viaPackageMapvirtual340; stable-name bittrue returns resolved
existingobject without creation/classGUID. Payload3f2da40..3f2dc52 thenpackedbits.
Property-empty content would bechecksum0+packedterminator0=9bits. Validate exact
ReceivedBunch/create-replicator path before any component warmup experiment.
No component export/warmup/identity/appearance payload has been sent.

Actual Ghidra review of the exact installed executable confirmed GameState
BeginPlay override5ef7800, predicate56f0e70, client driver/helper result3 and
WorldSettings lifecycle callback chain. The strict reviewed override guard is
implemented and ten targeted tests passed. tools/refresh_world_proofs.py
regenerates the fixed read-only proof set for a live possessed world pawn.

Background full login test a79d29fb80ef46a58c3ae95f0593b73f passed fresh Play,
Welcome and Verra loading. Correct HUD, mutual acknowledged possession and
pawnRole2/RemoteRole4 were independently accepted. PlayerState links remained
null. The loading overlay cleared, but the body stayed a placeholder.

BeginPlay single bool was sent1791281669.111 on ch5 handle21, reliable932.
Client then logged IntrepidInitialize/RequestInitializeCharacter/HUD setup,
and sent a real ServerMovePacked ch9 field44 packet1791281669.433. No fresh W
was sent; old pending input was nonzero and no walking is proved. Client logged
EACExitGame/Custom Failure1791281669.644, lobby KICK_ERROR Browse.647, then
closed connection1791281670.056. Posttrial reads correctly refused unloaded
objects. Trace the actual failure path before another initialization attempt.
Do not infer close caused return or adapter caused failure.

Current offline additions: exact pawn movement RPC envelope decoder and guarded
observer plus custom move decoding (no authoritative movement model/response); fixed controller
PlayerState property encoder (actual OnRep chain now reviewed and accepted in epoch3);
read-only predicate proof; world-entry scenario refuses active-world use. Full
suite123 tests passed after observer and initialization-error reporting changes.
Recheck required tests only after new changes.

Movement milestone after resume: lab/movement_serialization.py decodes exact
AoC native packed struct and custom per-move serializer. Offline tool
tools/analyze_captured_movement.py fully consumed all424 client RPCs (543 moves),
and281 server responses (280 ACKs plus one ordinary correction), each timestamp
matching a decoded move. Evidence/movement_capture_decoded_20261006.json
records full coverage, client locations and acceleration. Current live observer
records decoded reports but does not accept client positions as authority, send
ACKs, or claim walking. The actual prior local252-bit argument independently
decodes the pawn position, timestamp0.0001, nonzero old acceleration and mode3;
this remains no-fresh-W evidence. lab/movement_response.py encodes exact ACK
arguments and field35 envelopes, byte-identical to saved real-server fixtures;
no response is dispatched before server validation. Full suite131 tests passed.

Exact executable remains unchanged: SHA256
4f1cd43ceeb89190f048734efd4d63152b9f8e11fa31fc41093b0d90f4a1cd43, UE5.6.0.
Do not rebuild native input adapter while the game is running; compiled v1 is
still the validated build. The first resumed launch was restricted/invisible;
restart helper in normal desktop execution context for user-visible clients.

Ghidra project evidence/ghidra-project/AshesExactClient must have exclusive
access. The movement_binary agent finished the milestone and released the project.
No concurrent project access is allowed. Saved movement decompiles locate custom
container parsers through AoCCharacterMovement offsets988/bd0 virtual10;
fresh accepted world container identities are required for further live reads.
The saved next server validation/simulation targets are in
evidence/movement_server_handler_chain_20261006.md. Timestamp reset/discrepancy
state, bounded move delta, controller readiness, authoritative movement/collision
and error-response comparison remain to implement; do not ACK client positions
merely because their wire format is decoded.

Original paused checkpoint preserved as evidence/paused_checkpoint_20261006.md.

## Concrete initialization blocker found before pause

Exact Tether_SessionReplyCallback6490320 reads launcher tags eac_sandbox_id,
eac_deployment_id and auth0_accesstoken, then calls IntrepidEOS setter56cbeb0.
Our lab/tether.py sends both IDs empty and the synthetic lab-local-account token.
The setter rejects empty IDs, logs the observed startup error and leaves EOS
state0. After BeginPlay retains the world controller, tick56ccb40 state0 invokes
the controller failure callback, then Custom Failure/KICK_ERROR lobby travel.
Installed Game/EasyAntiCheat/Settings.json has populated IDs but is not the
source consumed by this tether callback. Copying IDs alone does not supply a
legitimate authenticated EOS Connect identity. This limits sustained live
BeginPlay testing. Movement decoding and server implementation continue from
the exact binary and captured gameplay; do not fabricate credentials, disable
security checks or memory-patch gameplay.

UI source now exposes initialization errors and background full-entry preset,
and rejects world-entry runs while a connection is active. Helper26548 retains
the earlier application class until a future normal-desktop helper restart;
source changes and tests are saved. WorldProtocol was reloaded for BeginPlay
but observer integration afterward needs reload before a future experiment.
No automatic wakeup is scheduled. Client28500 is left alive at character
selection; helper26548 and local dashboard remain running. Recheck on resume.
# Current readiness milestone: epoch4, 2026-10-06

Goal remains active and expanded to visible spawned character, working gameplay
UI, correctly rendered world, then fresh-input movement accepted by our server.
This goal turn made concrete progress; it is not a repeated impasse turn.

Client56180/helper11072 remain live. World epoch4 connection
664bb52b52dc2a0448b2424a started1791288983.5080504, peer127.0.0.1:49213.
Accepted PC0x18f140f0040, GS0x18f09118040, pawn0x18ee7df0040,
PS0x18f9a87e930. Recheck state/freshness before future reads or dispatch;
previous world epochs returned to selection at almost exactly20 minutes.

Verified new local CharacterInfo export plus property-empty warmup:
command e647fa2c8076c0f96d695e595359b9d7 dispatched1791289371.5626357.
Existing BaseCharacterInfo is **PlayerInfo**, not PlayerCharacterInfo.
Component0x18fd7ad8940/index72624/weakserial344311, outer and cachedActor+c8
both actual accepted pawn. New GUID2e7522ab5b72e750/server1/random3922224476
independently mapped to exact existing object in guidcache0x18f705f12d0.
Native PreNetReceive2a8 is131c2f0RET, PostNetReceive2b0 is15f4670JMP tosameRET.
Empty update initialized actual PlayerInfo driver ClassNetCache and RepLayout:
38 parents/85commands, classindex5263/serial344307, layout0x18fa5c8a180.
No load checkpoint or character data was supplied by warmup.

Fixed CharacterInfoName command f8d34772508c13e48509a5b102852f5c sent
1791289763.618589, wirehandle8. Normal name serializer16de940 ->item1610120
->archive130 FString; OnRep wrapper5d81500 ->actual570=6c2b150 marks dirty1a8.
Single local database character name LabExplorer supplied and independently
read back in evidence/character_info_after_name_56180.json. Before value was
**Player**, not empty: prior observer did not decode StrProperty, now fixed.
One first name command f1f14ec...sent nothing duecachedmoduleImportError; nonce
consumed, fixed component module reload before subsequent freshnonce. Live Lab
reload method remains original, so name branch reloads its helper module.

ClientSetHUD053dd7cf8b6378753c448385c2bcc902 and
ClientRestart2822443d5d040dd7ac4bd49848403233 restored current HUD/possession.
Fresh refresh_world_proofs now succeeds with mutual acknowledgement/backpointer
and exactIntrepidNetDriver. BegunPlay remainsfalse. No PawnAutonomous,
PlayerState associations, or GameStateBeginPlay sent in epoch4 yet.
Attached screenshot calibration.png after possession still shows coarse world,
Player label, no body/widgets. Name dirty notification is not yet visible.
No movement is proved. CharacterGuid stillzero, Race/Gender/ServerId0, Level1.
Actual phaseflags bIsPhasedOutfalse,bClientIsReadyToPhaseIntrue,
bHasBeenPossessedfalse,TeleportState0. Do not fake phase/load markers.

New code lab/character_info_component.py, fixed schemas in unreal.py and
create_client_restart_experiment.py, read-only receiver and mapping inspectors.
Tests use bounded stable fixture tests/fixtures/character_info_epoch4_20261006.json;
140tests passed before final notification-metadata guard addition. Rerun only
appropriate affected tests after that change.

Next identity work: PlayerInfo CharacterGuid is parent2, four IntProperty child
commands2..5/handles3..6/offset118,11c,120,124, raw32 perword. Do not write raw16
bytes asonehandle. Need exact childscalarserializerproof and local DB character
ID binding before authoring. Guid wrapper5d81460 ->actual560=6c2b0c0 calls
base6b539f0, actorlookup3b7fdb0/5e0ec70, oldvalidguidremoval662bf90,
newguidregistration661c5a0 (maps/delegates). Reviewed files saved in
evidence/ghidra-readiness-review. Name/Guid callbacks markpending info dirty;
client update/ticking maystillrequire realBeginPlay.

User highlighted IntrepidNet servermeshing/dynamicgridding. Already used current
IntrepidNetDriver and extended128-bit networkGUIDs, actualmesh-specific gameplay
serializers. Local field acceptance demonstrates working actorreplication layer;
notproof of fullregion/service initialization. Former gameplayengineer primary
source https://jburdecki.com/ashes-of-creation describes service-coordinated cross
serverauthority. Investigate serverassignment and readiness rather than assuming
the wholedistributedmesh is necessary for one localcharacter or causeofbadLODs.
EOS lifecycle blocker remains unchanged; no securitychecks disabled or fake EOS
credentials. Legitimate missing initialization stilllimits liveBeginPlay.
