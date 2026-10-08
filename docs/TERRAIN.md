# Ashes Server Lab terrain collision

This page documents landscape collision extraction and admission for Ashes Server Lab's experimental Ashes of Creation exploration server. The offline tool reads your installed IoStore archives and decodes cooked Chaos landscape collision. It needs the matching client files and an Oodle library you supply. It does not need a character to travel through cells or a running game process.

Included interoperability metadata describes 268 native classes/structs and 59 enums for the pinned build. It contains names, field types and serialization indexes, not terrain geometry or an Unreal SDK implementation. The exact-build Landscape and LandscapeStreamingProxy defaults were observed to enable actor collision with QueryAndPhysics and BlockAll. Per-archive actor and BodyInstance overrides are inspected before admission; unknown overrides are rejected.

## Main-world coverage

| Data | Verified local result |
| --- | --- |
| Verra heightfields | 2,669 |
| Rotated Verra components | 82 |
| Heightfields containing holes | 288 |
| Warped landscape meshes | 1 |
| Warped mesh vertices / triangles | 261,121 / 518,866 |
| Other installed maps, separate export | 5,257 heightfields, 48 rotated |

The decoder retains uint16 height samples, material bytes, quantization, transforms and source hashes. Material 255 marks a hole. Full row-major affine transforms are preserved; the native heightfield consumer supports yaw rotation and rejects unsupported tilt/shear. The warped landscape mesh preserves float vertices and indexed faces, bakes its nonuniform transform and uses a BVH for native queries.

The scan inspects all applicable world packages, including cells you have never visited. Archive presence does not prove a cell is reachable or that the client streams everything successfully.

## Winstead settlement platform — latest local work

The configured lab automatically sends Winstead platform metadata through the native settlement replication path. Before enabling movement, it verifies the current accepted actor, actual streamed package, loaded/visible level and placement, then admits **256 locally extracted platform heightfields** into a private collision world for that player. With the **2,669 base Verra tiles**, that world contains **2,925 tiles**. Other players without verified platform acceptance retain the base world.

A controlled three-pulse route crossed the previously failing floor seam over about **36.18 metres**. All 43 sampled native poses remained grounded, platform contact was tied to the admitted loaded level, and the three server trace windows had 106 acknowledged updates with zero corrections. This establishes the sampled platform crossing, not every slope, building or route.

The clean release still uses base Verra terrain and an empty prop cache by default. The private platform manifest/buffers are excluded from Git, and the standard `Export-Terrain.ps1` does not generate or configure that extra candidate. The saved native platform admission is build-specific; do not assume a visible settlement alone means the server has matching collision.

Live settlement tier controls and transitions across **0–6 (Metropolis)** remain unfinished. Saved Winstead service selection produced empty filtered groups at tiers 5 and 6; changing tier metadata alone is not a populated city. See the [checkpoint handoff](PAUSED_DEVELOPMENT.md) for the remaining work.

## Outputs

All outputs are ignored and generated under `CPP/data/terrain-offline/`:

| Directory/file | Purpose |
| --- | --- |
| `inventory/` | Indexed files and asset-registry metadata |
| `mappings/` | Local copies of build-matched parser definitions |
| `cooked/`, `cooked-mesh/` | Source Chaos collision and package manifests |
| `collision-metadata.json` | Owner collision settings/overrides from archives |
| `collision-defaults.json` | Pinned class-default settings |
| `decoded/`, `decoded-mesh/` | Native buffers and admitted manifests |
| `native-loader-verification.json` | Native validation report |

The C# project pins `CUE4Parse 1.2.2.202610` and `Microsoft.Bcl.Memory 10.0.9`, targeting .NET 10. See the [upstream parser](https://github.com/FabianFG/CUE4Parse). The Oodle path comes from `ASHES_OODLE_LIBRARY`; the wrapper sets and restores that environment variable.

## Manual reproduction

The wrapper in the README runs this sequence with the appropriate absolute paths:

```powershell
$env:ASHES_OODLE_LIBRARY = 'D:\YourTools\oodle-data-shared.dll'
dotnet build .\CPP\tools\terrain-collision\TerrainCollision.csproj -c Release
# Copy config/terrain-mappings into data/terrain-offline/mappings first.
# Copy config/terrain-defaults.json to data/terrain-offline/collision-defaults.json.
$parser = '.\CPP\tools\terrain-collision\bin\Release\net10.0\TerrainCollision.dll'
$paks = 'D:\YourClient\Game\AOC\Content\Paks'
$inventory = '.\CPP\data\terrain-offline\inventory'
dotnet $parser $paks $inventory --scan
dotnet $parser $paks $inventory --mesh-scan
dotnet $parser $paks $inventory --collision-metadata
python .\CPP\tools\decode_terrain_collision.py
python .\CPP\tools\decode_terrain_mesh.py
python .\CPP\tools\admit_terrain_collision.py
.\CPP\build\msvc\Release\ashes_terrain_tests.exe .\CPP
```

To investigate other installed maps separately:

```powershell
dotnet $parser $paks $inventory --other-worlds
python .\CPP\tools\decode_terrain_collision.py cooked-other-worlds decoded-other-worlds
```

Other-map output is an offline research artifact. It is not admitted into the active Verra cache; mixing maps can produce false floors where coordinates overlap. Map selection, admission and travel need further implementation.

The default `config/empty-collision.json` deliberately contains no props. Native mesh primitives exist for future local caches, but comprehensive prop extraction, instance placement and collision response/channel fidelity remain future work.
