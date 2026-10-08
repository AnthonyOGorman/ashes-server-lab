# Ashes Server Lab verification

This page records tests and observed client behavior for the experimental Ashes of Creation exploration server. Results distinguish synthetic source checks, privately generated terrain and real-client observations; none establish a complete server emulator.

The earlier portable-package checks below were recorded on 2026-10-07, Windows x64, Visual Studio 2022 / MSVC 19.44, .NET SDK 10.0.401, against the executable identity in `CPP/config/supported-client.json`. Later lab results were saved on 2026-10-08 before development paused. The exported checkpoint was not rebuilt or given a fresh-install playthrough.

## Latest lab checkpoint — 2026-10-08

| Check | Saved result and scope |
| --- | --- |
| Last deployed Release | All five CTest suites passed: 530 protocol/core, 109 movement, 12,077 private terrain, 11 executable-identity cache and 11 loading-readiness checks |
| Selected character and resources | In-world name matched selection; health, mana and stamina current/max values were initialized and verified from a configurable local-test profile |
| Loading input lock | Early W input produced no displacement in 15 locked native samples; movement was released only after all 31 stages, native floor contact and current gameplay presentation readiness |
| Post-ready walking | About 12 metres, 113 new moves/113 acknowledgements, zero corrections, maximum prediction error 0.26965 cm; one bounded trial |
| Winstead foundation | Native settlement metadata, actual visible streamed platform and placement verified; 256 matching collision tiles admitted for the accepted player, giving 2,925 tiles with base Verra |
| Winstead seam crossing | Three bounded W pulses, about 36.18 metres and 43 grounded native samples; exact platform contact, 106 acknowledged updates, zero corrections/resolution moves and a later stationary observation |
| Stationary jump after gravity fix | 55 new moves/55 acknowledgements, zero corrections/resolution moves, maximum prediction error 0.0062488 cm; native ascent, descent and grounded landing |
| Reviewed input DLL | Protocol 2 fixture/attachment checks and automated login/Play passed; no live Shift sprint trial |

The [walking review](checkpoints/research-loading-positive-control-review.json) and [stationary jump receipt](checkpoints/stationary-gravity-accepted-20261008.json), with independent [before](checkpoints/research-stationary-jump-before-review.json) and [after](checkpoints/research-stationary-jump-after-review.json) reviews, preserve the accepted evidence. The [pause handoff](PAUSED_DEVELOPMENT.md) records the workspace artifact locations and tested executable hash. These results came from separate controlled lifetimes; they are not one continuous session or proof of every route.

Ordinary gravity was corrected from −2450 to **−1225 cm/s²**, matching native world gravity −980 × movement scale 2.5 × character scale 0.5. Jump velocity remains **900 cm/s**. Before the fix, a brief stationary Space pulse caused four corrections and about 19.9653 cm maximum disagreement. Afterward, 44 native samples showed a **329.052736 cm sampled rise**, zero horizontal displacement and a safe landing. Sampling does not establish the exact continuous apex. Moving jumps, air control, slopes and landing parity remain unverified.

Native bootstrap/inspection work improved, but the client retains its 22-second loading-screen hold. The measurements do not establish faster visible entry. Health/mana/stamina bars do not establish damage, regeneration, ability costs or sprint consumption. Adapter Shift handling is not evidence that the client activated sprint. The platform result does not establish complete building/service collision, every settlement, or working tier transitions.

## Earlier packaged source — 2026-10-07

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

The original active lab was observed with character actor acceptance, possession, HUD, BeginPlay, initial stats and live speed-stat readback. Real movement remained animated after speed changes. Later controlled walking and jump trials improved as described above, but some walking jitter remains; the period-key walk toggle still needs investigation. Flying reduced pushback in the earlier session.

The published GIFs use player-supplied recordings of the client and Web UI from 2026-10-07. They predate the latest loading, settlement-platform and stationary-gravity fixes. The recording lab includes an older incomplete static-prop cache; the packaged default has no prop geometry. GIF previews are excerpts; linked full-length GIFs retain the complete recordings with reduced frame rate/resolution.

The fresh packaged build was checked with native services and complete locally regenerated terrain. A separate fresh-client lobby-to-gameplay reconnect using that packaged executable was **not** performed during packaging, so the observed client session is evidence from the existing lab, not a claim of a second fresh-install playthrough. The setup installer was checked independently against the same client build in a separate folder.

## Earlier private fixtures

The original research workspace passed 12,071 terrain checks with two native runtime terrain references and 487 previous checks including 101 baseline movement simulation steps. Game-derived buffers and executable byte ranges from that workspace are not included. The public source-only checks use synthetic geometry and generated protocol fixtures; the public terrain suite runs on data regenerated from your own client.

Native reference comparison is still optional if a developer independently supplies a local `CPP/baseline/evidence/terrain_epoch18_49892/manifest.json`. The absence of those private references is reported as zero reference matches, not a successful comparison.
