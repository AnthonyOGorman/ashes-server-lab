# Recovered client structure atlas

This atlas groups declarations and diagnostic paths. It describes recoverable structure and provenance, not verified behavior or exhaustive subsystem ownership.

## Largest reflected packages

| Package | Types | Methods | Native candidate links | Enums |
| --- | ---: | ---: | ---: | ---: |
| GameSystemsPlugin | 4,304 | 7,767 | 7,251 | 787 |
| Engine | 2,370 | 4,565 | 4,396 | 581 |
| ControlRig | 655 | 391 | 383 | 42 |
| RigVM | 556 | 55 | 54 | 20 |
| PCG | 467 | 383 | 354 | 158 |
| Niagara | 461 | 262 | 249 | 137 |
| GeometryCollectionNodes | 338 | 0 | 0 | 44 |
| MovieScene | 252 | 85 | 79 | 25 |
| MovieSceneTracks | 239 | 64 | 57 | 8 |
| AIModule | 236 | 224 | 172 | 49 |
| CoreUObject | 235 | 1 | 0 | 39 |
| GameplayCameras | 228 | 115 | 101 | 23 |
| MeshModelingTools | 224 | 84 | 72 | 77 |
| GeometryScriptingCore | 181 | 584 | 581 | 79 |
| InteractiveToolsFramework | 180 | 24 | 11 | 25 |
| UMG | 168 | 816 | 699 | 18 |
| MovieRenderPipelineCore | 163 | 401 | 391 | 27 |
| MeshModelingToolsExp | 158 | 59 | 52 | 52 |
| StateTreeModule | 139 | 25 | 13 | 28 |
| IKRig | 124 | 81 | 50 | 17 |
| AkAudio | 123 | 167 | 154 | 29 |
| AnimGraphRuntime | 123 | 110 | 110 | 34 |
| HoudiniEngineRuntime | 117 | 54 | 54 | 40 |
| DataflowCore | 114 | 0 | 0 | 5 |
| TypedElementFramework | 105 | 30 | 26 | 1 |
| ModelingComponents | 92 | 40 | 37 | 17 |
| Landscape | 86 | 26 | 23 | 24 |
| Chooser | 81 | 12 | 11 | 8 |
| InterchangeImport | 78 | 0 | 0 | 3 |
| Synthesis | 78 | 224 | 190 | 38 |

The complete package table is `catalogs/sdk-packages.csv`. `catalogs/type-hierarchy.csv` retains unique candidate parent resolutions and ambiguous/unresolved declarations. `catalogs/game-classes.csv` lists every indexed GameSystemsPlugin class whose C++ name has an Unreal class prefix.

## Game diagnostic source areas

These groups come from embedded Public/Private source paths referenced by machine instructions. Counts reflect diagnostic provenance; an inline helper can contribute a path inside a differently owned function.

| Area | Distinct paths | Attributed ranges | References |
| --- | ---: | ---: | ---: |
| (module root) | 1 | 1 | 1 |
| CharacterCreator | 1 | 1 | 1 |
| DesignData | 2 | 4 | 15 |
| Dialogue | 1 | 6 | 6 |
| GameService/CityNode | 1 | 43 | 43 |
| GameService/Guild | 1 | 2 | 2 |
| Interactables/V2 | 1 | 1 | 1 |
| Narrative/V2 | 1 | 49 | 49 |
| Node | 2 | 7 | 7 |
| Placeables | 1 | 1 | 1 |
| Roads | 1 | 1 | 1 |
| ServiceBuildings | 1 | 1 | 1 |
| UI | 24 | 36 | 166 |

`catalogs/source-areas.csv` contains every matched source module. Full original path strings and instruction RVAs are in `catalogs/source-references.csv`.

## Coverage boundaries

Generated SDK parents and member layouts are declarations from a saved dump. The main executable and archives have separate fingerprints. Matching native registration candidates do not prove all layout assumptions for every type. General asset default objects still require correct serialized property schemas. Indirect dispatch, object lifetime, state transitions, expression evaluation, and complete exception flow require semantic review.
