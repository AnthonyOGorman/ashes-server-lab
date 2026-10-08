# Development paused — 2026-10-08

The user requested that all development stop and the current work be committed locally in `E:\Ashes Of Creation GPT\Releases\ashes-cpp-lab`. Do not push this checkpoint. The cooperating server, client-testing and client-research chats have stopped implementation, builds, native readers, input tests and heavy research jobs. The running game and server were left in place; this document does not certify their present state.

This checkpoint includes the current C++ implementation, native adapter sources, client-testing bridge and guards, research notes and authored scripts, and the earlier Python lab and helper sources. Existing release documentation, dependency headers, portable configuration examples and terrain setup helpers are retained. The [source snapshot manifest](checkpoints/source-snapshot-20261008.json) records source and exported SHA256 values, including the few existing release portability adaptations retained during export.

The historical [workspace README](legacy-workspace-readme.md), [resume notes](historical-workspace-resume.md), research notes and [loading status](checkpoints/loading-readiness-status-20261008.md) contain older process identities and earlier next-step instructions. They are reference material. This pause takes precedence; none of those instructions authorizes another run.

The later README/documentation refresh is documentation-only. It reconciles the public pages with the saved results below and regenerates the site; it does not resume gameplay development, native research, server builds or input tests. See [verification](VERIFICATION.md) for the current evidence summary.

## Results saved before the pause

- The server chat reported all five Release CTest suites passed for the last deployed source, including 109 movement checks. That executable had SHA256 `8a657da7c3fa57fbb4659291c931fb51c4090b44e95046551f9f6510161a7364`. No build or live test was run for this export, and the release packaging adaptations have not been rebuilt.
- Character selection identity was reflected in the in-world name. Health, mana and stamina current/max bars were initialized and verified from configurable local-test values; this does not establish combat, regeneration or sprint costs.
- The configured lab automatically streamed the Winstead platform and admitted 256 matching private collision tiles before enabling movement. Native actor, visible loaded package and placement were verified. An earlier 36.18-metre, three-pulse route crossed the floor seam with 43 grounded native samples and 106 acknowledged updates/zero corrections. This applies to the tested foundation/route; wider town content, prop collision and other routes remain incomplete. The clean terrain setup does not generate or configure the private platform candidate.
- A brief stationary, one-count jump with no held jump input was accepted against native samples and the complete server trace. Ordinary gravity is `-980 × 2.5 × 0.5 = -1225 cm/s²`, with jump velocity `900 cm/s`. Before the fix, 56 new moves produced 52 acknowledgements and four corrections, with maximum prediction error `19.9653 cm`. After the fix, 55 new moves produced 55 acknowledgements and zero corrections or resolution moves, with maximum error `0.0062488 cm`. Native samples showed a `329.052736 cm` rise, zero horizontal displacement and a grounded landing; the sampled rise is not a continuous apex measurement. See the [acceptance receipt](checkpoints/stationary-gravity-accepted-20261008.json) and independent [before](checkpoints/research-stationary-jump-before-review.json) / [after](checkpoints/research-stationary-jump-after-review.json) reviews.
- Loading readiness requires the current world, all 31 initialization stages, controller input release and native walkable floor contact. An earlier post-ready W trial was accepted with 113 acknowledgements, zero corrections and approximately 12 metres of displacement. Its lifetime later left the world, so that result is historical. The fixed native 22-second loading-screen hold remains unresolved; improved bootstrap timings do not establish faster visible entry.
- The reviewed C++ input adapter uses protocol 2 and build ID `0x0c32ad42`. Its immutable local Release DLL had SHA256 `2b582aba70a23fce5f162469488807bbaf9b33e0edf6cc46deda0d547748a34c`. The hidden fixture, attachment guards and UI entry were checked before the pause. No live Shift sprint trial was performed.

## Unfinished work preserved

- Moving jumps, horizontal air control, slopes and landing parity still need live comparison. Research found an air-control boost based on pre-loop planar speed strictly below 25; the implementation and acceptance work remain incomplete.
- `client-testing/sprint_driver.py` and the narrow W / Shift-W comparison path in `coordinated_traversal.py` are staged. Their guards were checked, but live sprint behavior and resource consumption were not verified. The general MCP input allowlist still exposes WASD and Space only.
- `client-testing/stamina.py` is work in progress. It was syntax checked, but has no completed live acceptance or integration. Fresh owner-scoped stamina observations before, during and after movement remain necessary.
- Settlement tiers 0–6 and real transitions are unfinished. Maximum-tier metadata alone does not establish a populated city. The current Winstead selection yielded empty filtered service groups for tiers 5 and 6; see the [candidate receipt](checkpoints/research-winstead-service-selection-candidates.json).
- The testing bridge and research scripts retain local workspace paths, executable identities and reviewed adapter pins. They are saved development tools, not a newly configured portable testing installation. A copied receipt is historical evidence, not permission to reuse stale pointers, process IDs or input leases.

## Local artifacts retained outside Git

The original workspace at `E:\Ashes Of Creation GPT` is unchanged by the export. Build products, game libraries, extracted collision/terrain, generated SDK schemas, databases, catalogues, decompiled output, large native traces, screenshots and test sessions remain there under the package's exclusions. Small hash-bound acceptance and review receipts are copied under `docs/checkpoints/`; raw evidence is not discarded.

Key original paths:

- `client-testing/runs/stationary-gravity-accepted-73c24cf47e2a484b82d2d501b50b1425.json`
- `client-testing/runs/stationary-space-39003a4a34ce40418dc68ebb0f959aa4.json`
- `client-testing/runs/resume-readiness-f0939c65285e4588b6d7d8f39064c616.json`
- `CPP/runs/character-movement-followup-20261007/stationary-space-gravity-before.json`
- `CPP/runs/character-movement-followup-20261007/stationary-space-gravity-after.json` — SHA256 `8ca25482a2693fc0b28d8247253c29773cdc095de32e446d72a04afcbb363d75`
- `CPP/runs/gravity-repeat-20261008/stationary-comparison.json`
- `CPP/runs/loading-readiness-20261008/shift-release-candidate-0c32ad42/`
- `client-research/proofs/`, `client-research/index/`, `client-research/catalogs/`, `client-research/decompiled/`, `client-research/schemas/`

At the last coordinated check, the backend was PID `633760` / creation FILETIME `134359013996695814`, and the client was PID `658928` / creation FILETIME `134359014322564314`, connection `d5c8ce7da986b381834b6b63`. Input was released at the end of the accepted testing window. A later research observation contained nonzero velocity of unknown cause; current idle state is not asserted. Revalidate all identities, source hashes, readiness and exclusive ownership only after the user explicitly resumes work.

Coordination: server chat `01a1167a-dcaf-7bd3-82b8-6acf396b15ae`; research chat `01a115b6-17ec-7ee2-a180-41f2c6ecd797`; testing chat `01a116ae-2ec4-7de0-b563-31251b0c4533`. All remain paused. The user will handle any later push.
