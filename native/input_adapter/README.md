Experimental offline Ashes input adapter
=======================================

Build from the workspace with `cmd /c native\input_adapter\build.cmd`.
The build produces a DLL, a hidden fixture executable and SHA256 manifest under
`build`. Run the fixture with the absolute DLL path:

```powershell
& '.\native\input_adapter\build\ashes_input_fixture.exe' "$PWD\native\input_adapter\build\ashes_input_adapter.dll"
python -m unittest discover -s tests -p test_automation.py -v
```

`lab.automation.AttachedWindowsDriver(game_pid)` retains the HWND-scoped
PrintWindow screenshot and PostMessage input APIs. Its constructor verifies the
exact installed game path and SHA256 from `evidence/client_inventory.json`, and
the compiled DLL hash from the build manifest. It then loads this fixed local DLL
into that PID through LoadLibraryW. It resolves the actual owner of LoadLibraryW
(including KernelBase forwarding) in both processes instead of assuming shared
module addresses. It never writes the original executable file.

The DLL accepts only its own process's Ashes client or the named fixture. The
main executable's USER32 import table is changed reversibly; no instruction
detours, security hooks or anti-cheat changes are present. The adapter installs
these 23 replacements only on explicit activation:

* Position: GetCursorPos, SetCursorPos, WindowFromPoint, GetClipCursor, ClipCursor.
* Cursor appearance: SetCursor, ShowCursor.
* Key state: GetKeyState, GetAsyncKeyState.
* Capture: GetCapture, SetCapture, ReleaseCapture.
* Focus: GetForegroundWindow, GetActiveWindow, GetFocus, SetFocus,
  SetActiveWindow, SetForegroundWindow, AllowSetForegroundWindow.
* Global input: SendInput.
* Window activation: ShowWindow, SetWindowPos, SetWindowPlacement.

Active getters use process-local virtual cursor, key, focus and capture state.
Active cursor/input/focus setters update that state or return without desktop
input. Window placement calls preserve NOACTIVATE behavior. The attached driver
posts WM_ACTIVATEAPP and WM_SETFOCUS notifications only while this virtualization
is active. It sends inactive/kill-focus cleanup notifications before deactivation
when the real foreground belongs to another process. It never sends WM_ACTIVATE.
Inactive replacements call the original APIs. The ordinary background/foreground
tester drivers are unchanged.

Commands use a fixed 24-byte request and 48-byte response over
`\\.\pipe\ashes-lab-input-<PID>`. The pipe permits the process user and SYSTEM,
rejects remote clients and permits no arbitrary addresses, memory contents,
function calls or RPCs. Commands are status, activate, bounded client-coordinate
cursor position, allowlisted key/button state, deactivate, and restore. Responses
include the real foreground PID through the original API, not the virtual getter.
Protocol v2 is staged in the source and build script: each future build generates
a random identity embedded in the DLL and build manifest, and the Python client
rejects a different resident identity. The current compiled and live-tested DLL
remains protocol v1, SHA256
`b79bea66e150bd7a31b00e2fafb5eda398ed8ec42d358301d5427891fa69730a`.
The Python client accepts that v1 manifest until it is retired. V2 has not yet
been compiled or exercised by the native fixture. Exit the game before rebuilding
a loaded DLL, then run `build.cmd` and the fixture commands above. Restart the Lab
helper before adopting the new build. Do not rebuild while PID 29312 retains the
current DLL.

Click and key actions deactivate in cleanup. A native watchdog clears virtual
state after five seconds without commands, including IPC loss. `restore()` also
returns the patched import slots to their original values. The DLL remains
loaded until client exit, because unloading while another thread executes a
callback would be unsafe. Process exit removes the adapter completely.

The fixture verifies 23 installed/restored IAT slots, virtual position/key/focus
getters, command validation, unchanged real foreground, and lease expiration.
It creates a hidden window and issues no desktop cursor/focus setters or real
input. Python fake-driver tests cover failure, cancellation, exact HWND/PID
matching, focus-notification ordering, cursor movement by the user, build-response
validation and cleanup. All 42 automation tests passed after these changes. The
fixture evidence applies to the compiled v1 DLL; it does not validate staged v2.

Saved screenshots include real cursor positions and before/after foreground
evidence. Cursor movement and switches between other user applications are
recorded without blocking. A transition from another application into the game
stops subsequent controls. These observations do not attribute changes to human
activity versus game behavior.

Only main-executable USER32 imports are intercepted. Direct GetProcAddress
calls, other loaded modules, raw-input paths, and internal USER32 behavior remain
outside this experiment. Live tests must inspect the real foreground/cursor
evidence and game screenshots before claiming independent background controls.
This adapter does not create a pawn or prove world movement.

The live run `01180dc73b284b5b841172b3c59324b6` on 2026-10-06 demonstrates
independent control of the inventoried client through Play, server Welcome and
Verra loading. The report is
`runs/190860ede89f/tests/01180dc73b284b5b841172b3c59324b6/result.json`; the Play
action is step 3, with screenshot `003-after.png`. Client PID 29312 and HWND
10295506 received the targeted control. Real foreground PID 10304 remained
unchanged before and after the action, and the real desktop cursor remained
`(-2246, 919)`. The adapter status after the action records `active=0`, `held=0`,
and 23 installed but inactive import replacements. Welcome and World loaded
steps passed. The complete run correctly failed on the unobserved
`player_spawned` milestone; pawn spawning and walking were not achieved. This
proves the recorded background action, rather than universal behavior across
arbitrary UI states or every future client build.

Binary evidence motivating the adapter: the inventoried client has a small
cursor accessor at RVA `0x18057F0`, with GetCursorPos called at `0x18057FE`, and
a foreground accessor at `0x180B6E0` calling GetForegroundWindow at `0x180B6E9`.
The desktop cursor API uses screen coordinates; posted mouse-message coordinates
do not replace that accessor. See [Microsoft GetCursorPos documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getcursorpos).
