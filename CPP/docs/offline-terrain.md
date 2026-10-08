# Offline terrain collision export

The installed build's terrain collision was extracted directly from its IoStore archives. No character traversal, game-function calls, memory writes or archive modifications were used.

The parser indexed 182,278 files and inspected all 16,173 installed world packages. It exported and decoded:

- Verra: 2,669 landscape heightfields, including 82 rotated components.
- Verra's warped landscape: one triangle collision mesh, with 261,121 vertices and 518,866 triangles.
- Other installed maps: 5,257 heightfields, including 48 rotated components.

All scans and decodes completed without failures. Heightfields preserve uint16 height samples, min/quantization, material bytes (255 indicates a hole), complete transform chains and affine matrices. Other maps remain separate because their coordinates can overlap Verra. The warped landscape preserves its float vertices, triangle indices, material indices and face/vertex remapping. Source cooked Chaos blobs are retained with SHA-256 hashes.

The offline export matched both earlier native runtime reference tiles byte-for-byte for heights and materials, and exactly for origins, scales, minima and quantization. This is representative native validation; it is not a runtime comparison of every tile.

## Outputs

- `data/terrain-offline/inventory/archive-files.json`: mounted archive inventory.
- `data/terrain-offline/inventory/terrain-assets.json`: Verra world and landscape asset registry entries.
- `data/terrain-offline/mappings/`: 268 build-matched native class/struct definitions, 59 enums and read-only executable proof.
- `data/terrain-offline/cooked/manifest.json`: Verra heightfield package identities and source cooked blobs.
- `data/terrain-offline/decoded/manifest.json`: all decoded Verra heightfields and buffer hashes.
- `data/terrain-offline/decoded-mesh/manifest.json`: the warped landscape's decoded collision mesh.
- `data/terrain-offline/decoded-other-worlds/manifest.json`: decoded terrain in other installed maps.
- `data/terrain-offline/verification.json`: archive coverage and native reference verification results.

The active C++ collision world now loads all 2,669 Verra heightfields and the warped landscape mesh. Rotated heightfields preserve their yaw, hole cells produce no floor or sweep triangles, and the warped mesh is transformed with its nonuniform scale before BVH indexing. Static mesh buildings, rocks and props are outside this terrain-only export; the earlier admitted static prop cache remains alongside the full terrain cache, and its coverage is still incomplete. Other maps remain separate.

The archive metadata scan checked all 2,670 Verra terrain components in 651 packages. None has an actor collision override or BodyInstance override. Read-only reflection of the exact build confirmed that both Landscape and LandscapeStreamingProxy class defaults enable actor collision and use QueryAndPhysics with the BlockAll profile. These defaults and metadata are retained in `collision-defaults.json` and `collision-metadata.json`; decoded manifests include explicit collision admission. Disabled components are excluded. Unknown overrides must be reviewed before admission.

Validation passed 12,071 native terrain checks, including surface queries in every tile with solid cells, hole queries in all 288 tiles containing holes, all rotated transforms, representative warped-mesh floors and capsule sweeps, both native runtime reference tiles, failed-reload preservation and disabled-terrain exclusion. The 487 existing C++ checks still pass, including the 101 captured baseline movement steps. Ground queries averaged about 0.006 ms in a 10,000-query spawn-area sample. Native-loader and active-server results are recorded under `data/terrain-offline/`. Live geometry API queries succeeded near spawn, a rotated landscape and the warped landscape. After deployment and reconnect, the live player used the full cache with native possession, HUD, BeginPlay, stats and 600 cm/s client speed readback verified.

Walking pushback and the period-key walk toggle remain unresolved movement issues; loading terrain is not a claim that client/server movement prediction now matches.

## Reproducing

Run `tools/export_terrain_mappings_readonly.py <owned-client-pid>` to refresh native terrain schemas for this exact executable. A current client is needed for definitions, but it need not visit terrain cells. Offline extraction then runs independently of the client.

Build `tools/terrain-collision/TerrainCollision.csproj` with the isolated SDK under `vendor/terrain/dotnet-sdk10`. Run the resulting DLL with the installed Paks directory, the inventory output directory, and one of `--scan`, `--mesh-scan`, or `--other-worlds`. Decode with `tools/decode_terrain_collision.py`, `tools/decode_terrain_mesh.py`, and `tools/decode_terrain_collision.py cooked-other-worlds decoded-other-worlds`.

The maintained CUE4Parse 1.2.2.202610 package is pinned, with Microsoft.Bcl.Memory 10.0.9. The older stable parser failed on this build's container-header offset format; the maintained parser reads it correctly. The local Oodle library was copied from the existing FModel installation. Nothing was installed globally.

After decoding Verra, run the extractor with `--collision-metadata`, run `tools/inspect_terrain_defaults_readonly.py <owned-client-pid>`, then `tools/admit_terrain_collision.py`. Build with the MSVC preset and run `ashes_terrain_tests.exe <CPP-root>` to validate the native consumer. The active paths are `terrain_manifest` and `terrain_mesh_manifest` in `config/backend.json`; `reload_geometry` builds and validates a replacement outside the server movement lock, then swaps it while preserving player state.

Parser reference: https://github.com/FabianFG/CUE4Parse
