# Demo GIFs

These exports come from player-supplied recordings made on 2026-10-07, using the supported AOC-CL-438018 client and local C++ lab.

| File | Content | Duration / size |
| --- | --- | --- |
| `exploration.gif` | Inline preview of movement through the game world | 8 seconds, 800 px wide, about 9.3 MB |
| `exploration-full.gif` | Complete exploration recording | About 30 seconds, 480 px wide, about 7.7 MB |
| `live-world.gif` | Inline preview of the live server collision view | 8 seconds, 960 px wide, about 9.1 MB |
| `live-world-full.gif` | Complete live-view recording | About 23 seconds, 560 px wide, about 7.9 MB |

The previews use seconds 4–12 of their recordings. Timing is preserved; frame rate and color count are reduced for GIF export. Full recordings use a smaller image and six frames per second to keep file sizes below 10 MB. No recording is sped up. GIFs contain no audio; original videos and recording metadata are not distributed.

The game preview shows the supplied client's scenery and movement. The Web UI preview shows real server positions, terrain, movement state and collision wireframes. The recording lab has an earlier incomplete static-prop cache, whose geometry is not distributed. The clean repository defaults to terrain-only collision. Rendered scenery and amber wireframes do not imply full prop collision or gameplay support.

The earlier assistant-captured screenshots and GIF have been removed from the published tree. The player-provided source recordings remain outside this repository.
