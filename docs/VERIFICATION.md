# Verification

Verified locally on 2026-10-07, Windows x64, Visual Studio 2022 / MSVC 19.44, .NET SDK 10.0.401, against the executable identity in `CPP/config/supported-client.json`.

## Packaged source

| Check | Result |
| --- | --- |
| Fresh MSVC Release build with no client/terrain files bundled | Passed |
| Source-only native protocol/movement/collision checks | 86 passed |
| Local EOS ABI/behavior tests | 9 passed |
| Client preparation from the actual owned PE | Executable hash and all 9 reviewed code ranges matched |
| Installer on a separate client test folder | Installed built shim, verified original backup, restored original, refused unexpected DLL |
| Native backend on separate loopback ports | Dashboard, lobby, world and tether started successfully |
| Full-cache native backend API | 2,669 tiles, one terrain mesh, empty geometry error, nonempty terrain wireframe |
| Offline extractor build | Passed, 0 warnings / 0 errors |
| Packaged `Export-Terrain.ps1` from the owned archives | Completed end to end, no package or decode failures |
| Native public terrain suite | **11,452 checks passed** |

The terrain run indexed 182,278 files, scanned 16,025 Verra world packages in each geometry pass and inspected 2,670 collision components in 651 packages for admission. It loaded 2,669 heightfields and one 518,866-triangle landscape mesh. It sampled solid floors in 2,659 tiles and holes in all 288 tiles containing holes, and checked all 82 rotated components. Ten heightfields contain no solid cells. Source hashes, cooked formats, dimensions, finite bounds, transforms, mesh indices and collision overrides are validated.

The public suite also checks warped-mesh floors/capsule sweeps, far-outside queries, floor ceilings, geometry output, unsupported tilt, changed buffer hashes, failed-reload preservation and disabled-component exclusion. The measured spawn-area ground-query average was approximately 0.0033 ms across 10,000 queries on the test machine; this is not a general performance guarantee.

Commands for contributors:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\CPP\tools\Build-CPP.ps1 -Configuration Release
python .\CPP\native\eos_connect_local\test_connect.py
# After generating your terrain:
.\CPP\build\msvc\Release\ashes_terrain_tests.exe .\CPP
```

## Real client and media

The original active lab was observed with character actor acceptance, possession, HUD, BeginPlay, initial stats and live speed-stat readback. Real movement remained animated after speed changes. Walking correction pushback persists; the period-key walk toggle can stop movement handling. Flying reduced that symptom in the session.

The published GIFs now use player-supplied recordings of the client and Web UI. They replace the earlier assistant-captured images and altitude demonstration. The recording lab includes an older incomplete static-prop cache; the packaged default has no prop geometry. GIF previews are excerpts; linked full-length GIFs retain the complete recordings with reduced frame rate/resolution.

The fresh packaged build was checked with native services and complete locally regenerated terrain. A separate fresh-client lobby-to-gameplay reconnect using that packaged executable was **not** performed during packaging, so the observed client session is evidence from the existing lab, not a claim of a second fresh-install playthrough. The setup installer was checked independently against the same client build in a separate folder.

## Earlier private fixtures

The original research workspace passed 12,071 terrain checks with two native runtime terrain references and 487 previous checks including 101 baseline movement simulation steps. Game-derived buffers and executable byte ranges from that workspace are not included. The public source-only checks use synthetic geometry and generated protocol fixtures; the public terrain suite runs on data regenerated from your own client.

Native reference comparison is still optional if a developer independently supplies a local `CPP/baseline/evidence/terrain_epoch18_49892/manifest.json`. The absence of those private references is reported as zero reference matches, not a successful comparison.
