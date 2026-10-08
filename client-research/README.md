# Ashes of Creation client research

This work maps the installed Windows client, its launcher, compiled functions, Unreal reflection, and packaged assets. The older exhaustive mapping goal remains paused. The current human request prioritizes fast safe login, then jump/gravity/sprint parity, and maximum settlement content with live tier controls. This chat owns research and saved evidence; the existing C++ chat owns implementation and the testing chat owns exclusive client input.

The game executable is a 235,606,624 byte x64 PE with SHA256 `4f1cd43ceeb89190f048734efd4d63152b9f8e11fa31fc41093b0d90f4a1cd43`. All native addresses below are RVAs relative to its preferred image base `0x140000000`. A runtime address also depends on the process's actual module base.

## Research outputs

Latest movement collaboration: `MOVEMENT_NETWORKING.md` section "Resources, world identity and enabled time discrepancy follow-up" records native discrepancy/debt/world-frame rules, substeps, CharacterInfo name source, six live resource IDs/types and owner/everyone replication routing. Twenty-five focused outputs and 36 snapshots passed `scripts/verify_resources_names_timing.py`. Direct same-session read-only cache inspection verified stamina Owner field3/max23 and health/mana EveryoneProxy field6/max23 with initialized shared receiver wrapper. Fresh resource amounts, new packet acceptance, sprint speed/cost and complete collision parity remain separate implementation/live validation work.

| Output | Purpose |
| --- | --- |
| [Ordered login and movement goals](<E:/Ashes Of Creation GPT/client-research/LOGIN_AND_MOVEMENT_GOALS.md>) | Current priorities, measured loading baseline, ownership, native safety gates and acceptance limits |
| [Loading screen hold](<E:/Ashes Of Creation GPT/client-research/LOADING_SCREEN_HOLD.md>) | Native timing versus actual screen dismissal, verified22-second client record timer, show/hide functions and input-release gates |
| [Jump and gravity parity](<E:/Ashes Of Creation GPT/client-research/JUMP_GRAVITY_PARITY.md>) | Current900 jump velocity, getter-derived-1225 gravity, exact stat/slow-fall bindings and falling integration gaps |
| [Current gravity review](<E:/Ashes Of Creation GPT/client-research/proofs/current-jump-gravity-review.json>) | Hash-bound profile and exactReplication7 metadata, five falling helper outputs/22gravity+helper fragments; gravity-only comparison pending |
| [Loading positive control](<E:/Ashes Of Creation GPT/client-research/proofs/loading-positive-control-review.json>) | Five saved source hashes, early loading gate certificate and post-unlock12mW/113ACK/0corrections; limited route and expired world binding |
| [Stationary jump baseline](<E:/Ashes Of Creation GPT/client-research/proofs/stationary-jump-before-review.json>) | Independently derived running-server gravity-2450, four corrections/max19.965cm; sampled rise and observation bounds retained |
| [Winstead tier recipes](<E:/Ashes Of Creation GPT/client-research/proofs/winstead-tier-recipes.json>) | Exact levels0..6, original prop IDs/transforms and service alternatives; completed higher-tier appearance remains unverified |
| [Client map](<E:/Ashes Of Creation GPT/client-research/CLIENT_MAP.md>) | Architecture, evidence layers, behavior findings, and remaining gaps |
| [Structure atlas](<E:/Ashes Of Creation GPT/client-research/STRUCTURE_ATLAS.md>) | Package coverage, SDK inheritance, game classes, and diagnostic source areas |
| [Research journal](<E:/Ashes Of Creation GPT/client-research/RESEARCH_LOG.md>) | Experiments, failures, corrections, checks, and provenance |
| [Asset schemas](<E:/Ashes Of Creation GPT/client-research/ASSET_SCHEMAS.md>) | Versioned class/default decoding experiments and structural checks |
| [Cooldown path](<E:/Ashes Of Creation GPT/client-research/COOLDOWN_PATH.md>) | Constructor/virtual dispatch, shared-tag matching, time/fraction getters, and active-state predicate |
| [Input configuration](<E:/Ashes Of Creation GPT/client-research/INPUT_CONFIGURATION.md>) | Cooked action/binding declarations and selected data-table/AI asset coverage |
| [Movement networking](<E:/Ashes Of Creation GPT/client-research/MOVEMENT_NETWORKING.md>) | Direction codec, gait flags, speed modifiers, received moves, correction decisions, collision findings, and server compatibility gaps |
| [Settlement loading](<E:/Ashes Of Creation GPT/client-research/SETTLEMENT_LOADING.md>) | Exact node placements, tier-one candidates, native loading and platform collision evidence |
| [Settlement C++ handoff](<E:/Ashes Of Creation GPT/client-research/SETTLEMENT_CPP_HANDOFF.md>) | Reviewed Winstead first-floor wire specification, deployment and live collision gates |
| [Settlement traversal proof](<E:/Ashes Of Creation GPT/client-research/proofs/settlement-traversal-review.json>) | Accepted Winstead seam: 43 grounded samples, 106 ACK and no corrections on the bounded route |
| [Settlement platform metadata](<E:/Ashes Of Creation GPT/client-research/proofs/settlement-platform-metadata-review.json>) | Collision metadata readiness for all 12 platform packages and 26 cataloged placements |
| [Crossroads profile](<E:/Ashes Of Creation GPT/client-research/proofs/settlement-crossroads-profile.json>) | 318 filtered prop entries across44 Verra layouts; transforms, asset classes and service-owner correlations |
| `catalogs/settlement-locations.csv` | 81 definition locations; exact world/purpose filtering required |
| `coverage.json` | Current machine-readable counts and confidence limits |
| `toolchain.json` | Tool paths, versions, hashes, sources, and tested capabilities |
| `index/client-index.sqlite` | Searchable native ranges, references, strings, SDK declarations, assets, Blueprint scripts, and managed methods |
| `catalogs/reflected-functions.csv` | Reflected methods with signatures, candidate addresses, and decompilation status |
| `catalogs/blueprint-functions.csv` | Cooked Blueprint function names and serialized export sizes |
| `catalogs/blueprint-calls.csv` | Decoded script call references and candidate native targets |
| `catalogs/types.csv` and `catalogs/properties.csv` | Class/struct hierarchy and named property layouts |
| `catalogs/enums.csv` and `catalogs/enum-values.csv` | Reflected enum names, numeric values, and declaration provenance |
| `catalogs/assets.csv` | Asset package, name, class, and chunk declarations |
| `catalogs/modules.csv` and `catalogs/module-dependencies.csv` | PE module inventory and DLL dependencies |
| `catalogs/managed-methods.csv` | Tokens and RVAs for eight launcher-related assemblies |
| `catalogs/all-managed-methods.csv` | Method ownership, signatures, and IL fingerprints across all 640 installed managed modules |
| `catalogs/native-module-exports.csv` and `catalogs/native-module-ranges.csv` | Native exports and exception ranges across supporting binaries |
| `catalogs/native-unwind.csv` | Chained-fragment parents and unwind roots in the game executable |
| `catalogs/blueprint-fields.csv` and `catalogs/blueprint-flow.csv` | Function-local field schemas and partial script flow relationships |
| `catalogs/blueprint-classes.csv` | Validated terminal class metadata candidates and explicit partial-export gaps |
| `verification.json` | Evidence-consistency checks and their practical limits |
| `catalogs/decompiler-diagnostics.csv` | Explicit failures, bad-data halts, and control-flow warnings, including completed outputs |
| [Next work](<E:/Ashes Of Creation GPT/client-research/NEXT_WORK.md>) | Continuation priorities, known gaps, and resume commands |
| `decompiled/managed/` | ILSpy C# and project/resource reconstruction |
| `decompiled/initial/` and `decompiled/bulk/` | Hash-bound Ghidra pseudocode |
| `decompiled/movement/` | 70 focused movement range outputs, backed by the movement manifest and saved Ghidra project |
| `proofs/movement-native-map.json` and `proofs/movement-verification.json` | Movement dispatch/snapshots and 12 passing static evidence checks |
| `decompiled/movement-followup/` and `proofs/movement-followup-verification.json` | 21 collaboration range outputs; 12 static checks for sender ownership, cached MoveSpeedMult, and velocity/overspeed evidence |
| `proofs/` | Small exact instruction fragments supporting reviewed findings |
| `batches/` and `logs/` | Decompilation manifests and execution transcripts |

`coverage.json` records global counts as of its generation timestamp; later batches and focused movement outputs can be newer. Movement pass counts and checks are recorded separately in `proofs/movement-verification.json`. A native exception record is not necessarily one complete logical function. Successful decompilation remains **unreviewed** until its types, dispatch, conditions, and effects are examined. A parsed Blueprint script remains a **decoding candidate**, even when its structure passes the checks.

## Search the map

Run from `E:\Ashes Of Creation GPT` using the installed Python 3.10:

```powershell
python client-research/scripts/query.py sdk Inventory
python client-research/scripts/query.py types PlayerCharacter
python client-research/scripts/query.py properties bWantsToSprint
python client-research/scripts/query.py labels SetSprintRequest
python client-research/scripts/query.py assets InputMapping
python client-research/scripts/query.py scripts AoCGameState
python client-research/scripts/query.py managed LaunchGameImpl
python client-research/scripts/query.py managed-all LaunchGameImpl
python client-research/scripts/query.py enums EAbilityFailureType
python client-research/scripts/query.py unwind 0x9284703
python client-research/scripts/query.py rva 0x58d9e40
python client-research/scripts/query.py callees 0x58d9e40
python client-research/scripts/query.py callers 0x5ec4de0
```

The `sql` mode opens the database read-only and supports joins across evidence layers. For example, Blueprint calls can be joined to native candidate names and decompiled outputs:

```sql
SELECT b.package, b.function, b.target_name,
       printf('0x%x', b.native_candidate_rva) AS rva,
       q.status, q.output
FROM blueprint_calls b
LEFT JOIN decompile_queue q ON q.begin=b.native_candidate_rva
WHERE b.package LIKE '%Inventory%';
```

## Continue native decompilation

The isolated Ghidra project is `client-research/ghidra-project/AshesExactClient`. It was copied from the existing exact-client project. Do not open it in the GUI while headless batches are using it.

```powershell
python client-research/scripts/run_batches.py --batches 8
python client-research/scripts/inspect_decompiler_outputs.py
python client-research/scripts/export_catalogs.py
```

The runner preserves each selected manifest and transcript. It refreshes the queue from hash-bound outputs and resumes pending ranges. Each batch has at most 256 ranges; each decompiler call has a 30 second timeout. Six ranges exceeding 64 KiB initially require separate review. Chained exception fragments are indexed with parent roots instead of queued independently; earlier fragment pseudocode has a separate unreviewed status. Failures remain explicit queue states.

Priorities are game/Intrepid native dispatch targets, their direct callees, diagnostic paths in game code, other named native functions, other source references, anonymous exception ranges, then metadata accessors. Metadata constructors and execution thunks have separate labels.

To prioritize a bounded direct-call neighborhood for review:

```powershell
python client-research/scripts/trace_native.py GameSystemsPlugin.AoCAbilityComponent.CanUseAbility --depth 2 --max 48 --reason 'Ability prerequisites'
```

To inspect a decoded Blueprint function:

```powershell
python client-research/scripts/inspect_blueprint.py /Game/UI/Widgets/Inventory/Tetris/WBP_TetrisInventory PreConstruct --output client-research/proofs/tetris-preconstruct-blueprint
```

For an exact instruction fragment:

```powershell
python client-research/scripts/disassemble.py 0x5ec4de0 --bytes 16 --stop-at-terminal --output client-research/proofs/sprint-request-setter
```

## Rebuild static inventories

`build_index.py` replaces the derived SQLite database and therefore discards its code/asset/decompilation indexes. Rebuild only deliberately; preserve an earlier database if comparisons are needed. The game installation and SDK are inputs.

```powershell
python client-research/scripts/build_index.py
python client-research/scripts/index_code.py --limit 1000000
python client-research/scripts/index_unwind.py
python client-research/scripts/link_metadata.py
python client-research/scripts/index_entry_blocks.py --core-callees
python client-research/scripts/index_enums.py
python client-research/scripts/index_modules.py
python client-research/scripts/index_module_definitions.py
python client-research/scripts/import_assets_and_reflection.py
python client-research/scripts/import_headers_and_managed.py
python client-research/scripts/import_bytecode.py
python client-research/scripts/blueprint_flow.py
python client-research/scripts/import_class_metadata.py
python client-research/scripts/build_atlas.py
python client-research/scripts/decompile_queue.py
python client-research/scripts/inspect_decompiler_outputs.py
python client-research/scripts/export_catalogs.py
```

The imports require the saved asset and managed metadata outputs. `index_module_definitions.py` requires the compiled `scripts/metadata-reader` helper; it reads managed PE metadata without loading assemblies. `index_code.py` is resumable; it must not be rerun against a changed executable. Its summary describes the initial exception-table scan; supplemental entry-block references are recorded separately.

## Asset inspection

The custom CUE4Parse program supports archive/registry inventory, `--headers`, `--bytecode`, `--class-metadata`, `--class-schema`, `--defaults`, and `--asset-values`. Object modes accept a package limit; schema/default/value modes also require struct and enum mapping paths. It reads installed archives and writes derived research outputs. Header analysis uses an empty schema container without deserializing objects. Bytecode analysis uses minimal zero-property schemas for Object, Field, Struct, and Function with `GAME_AshesOfCreation` serialization. Empty-schema class-metadata mode only succeeds when classes have no serialized property values. Separate SDK-schema, default-object, and configuration-value passes have explicit structural checks and remaining gaps.

The class loader can return a partially constructed export after catching an internal parser exception. The initial empty-schema class-pass log counted returned objects, not validated classes. `import_class_metadata.py` rejects objects without terminal UClass records: 624 baseline candidates and 6,816 partial exports. New class runs enforce terminal records and fatal exceptions. The separate `--class-schema` experiment decodes all 7,440 selected class exports with inferred SDK schemas and exact-consumption replay. `--defaults` adds a separate default-object experiment. See `ASSET_SCHEMAS.md` for versioned evidence, checks, and limits; default values remain candidates and some objects fail or consume an incorrect byte count.

The initial generic header attempt failed because CUE4Parse requires a mappings container for unversioned packages. Its failures remain in `package-headers.jsonl`; the successful header pass is `package-headers-v2.jsonl`. Bytecode package checkpoints prevent completed packages from being decoded repeatedly. Failures should be reviewed and retried with a separate versioned output rather than silently discarded.

## Toolchain

[Ghidra](https://github.com/NationalSecurityAgency/ghidra) provides native disassembly and pseudocode. The installed 12.0.2 build runs with the installed Corretto JDK 21. A direct Java launcher keeps its settings, caches, and temporary files inside the research folder.

[Capstone](https://www.capstone-engine.org/download.html) 5.0.6 supplies reproducible x64 decoding. [ILSpyCmd](https://github.com/icsharpcode/ILSpy/tree/master/ICSharpCode.ILSpyCmd) 11.1.0.9782 supplies modern C# reconstruction and method-table exports. These two tools were installed locally in this workspace. [CUE4Parse](https://github.com/FabianFG/CUE4Parse) 1.2.2.202610 was already cached and powers the archive and script indexer.

Existing FModel, x64dbg, dnSpy, UnrealPak, and Dumper-7 outputs are also inventoried. GUI asset browsing and debugger attachment have not been tested in this workflow. dnSpy successfully exported the launcher, but ILSpy's newer output avoids several async reconstruction artifacts found in that older output. None of the generated C# or pseudocode has been established as a buildable replacement client.

## Provenance boundaries

The installed EOS DLL is a local replacement. The historical original backup is `evidence/eos-sdk-original-backup/47261706ef55eca3df8ff2fef22937c77c7e1cc8e98f3171a8562c47005d781b.dll`. Treat the installed replacement, that backup, and the vendor game executable as separate inputs.

The supplied SDK is a generated reflection/wrapper dump. Its complete build provenance is not established by its existence. Matching saved runtime snapshots corroborate selected native function addresses and layouts for this executable hash. The snapshots are historical observations, not current process state.

The file inventory contains no original game PDB. The PE records the expected name `AOCClient-Win64-Shipping.pdb`, GUID bytes, and age. Source paths embedded in diagnostic code reveal project organization, but do not recover original source files. Optimized/inlined code, unnamed non-reflected routines, virtual dispatch, and stripped design intent remain substantial limits on a complete semantic map.
