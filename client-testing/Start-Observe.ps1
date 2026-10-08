$ErrorActionPreference = 'Stop'
& 'C:\Tools\Python310\python.exe' (Join-Path $PSScriptRoot 'cli.py') --tool get_player_state
if ($LASTEXITCODE -ne 0) { throw 'Client observation unavailable. Refresh the server client inspection for the current game session.' }
