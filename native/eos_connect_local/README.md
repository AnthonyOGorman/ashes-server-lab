# Local EOS Connect compatibility

Own implementation of the 25 EOS delay imports used by the installed client. It makes no network calls and accepts only the fixed local marker supplied by this lab. It does not authenticate with Epic or implement anti-cheat protection.

Build in this directory with `cmd.exe /d /c build.cmd`. Run `C:\Tools\Python310\python.exe test_connect.py` for ABI, asynchronous login, context lifetime, ID and export coverage. Stage builds separately; installation requires stopping the client because the SDK DLL is loaded for the process lifetime.

The lab profile `data/eos-local-compat.json` supplies local deployment tags only when the installed SDK hash matches. `evidence/eos_local_install_manifest.json` identifies the installed path, original backup and hashes. To roll back, stop the client, verify the original backup hash, restore that exact DLL, and remove the explicit lab profile.

Verified on client PID 49892 / run 29ed7987271b: SDK and platform initialization, successful local login callback, world entry, accepted HUD and pawn possession, true replicated BeginPlay, and a visible in-world character with gameplay UI. The original client EXE is unchanged. Screenshot: `evidence/eos-local-character-ui-49892.png`.

Fresh forward input produced 15 decoded nonzero input reports, but no position change. Server physics and movement responses remain unimplemented. Spawn is below terrain, gameplay stats are incomplete, and this is not full EOS emulation or a completed playable server.
