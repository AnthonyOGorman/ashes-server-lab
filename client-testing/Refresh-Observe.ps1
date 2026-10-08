param([int]$ClientProcessId = 0)
$ErrorActionPreference = 'Stop'
$clientExe = 'E:\Games\Steam Library\steamapps\common\Ashes of Creation\Game\AOC\Binaries\Win64\AOCClient-Win64-Shipping.exe'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$candidates = @(Get-Process -Name 'AOCClient-Win64-Shipping' -ErrorAction SilentlyContinue | Where-Object Path -EQ $clientExe)
if ($ClientProcessId -eq 0) {
    if ($candidates.Count -ne 1) { throw 'Exactly one running inventoried client is required; pass -ClientProcessId explicitly.' }
    $ClientProcessId = $candidates[0].Id
}
if (-not ($candidates | Where-Object Id -EQ $ClientProcessId)) { throw 'Requested PID is not the inventoried Ashes client.' }
$temporaryBinding = Join-Path $PSScriptRoot ('binding-' + [Guid]::NewGuid().ToString('N') + '.tmp.json')
try {
    # Existing inspector is read-only and verifies the executable hash/lifetime itself.
    & (Join-Path $workspaceRoot 'CPP\build\msvc\Release\ashes_inspect.exe') $ClientProcessId (Join-Path $workspaceRoot 'CPP\config\backend.json') $temporaryBinding
    if ($LASTEXITCODE -ne 0) { throw 'Read-only inspection failed; previous binding is preserved.' }
    $snapshot = Get-Content -LiteralPath $temporaryBinding -Raw | ConvertFrom-Json
    if ($snapshot.client_proof.pid -ne $ClientProcessId -or $snapshot.local_players.Count -ne 1) { throw 'Fresh unique LocalPlayer binding required.' }
    Move-Item -LiteralPath $temporaryBinding -Destination (Join-Path $PSScriptRoot 'binding.json') -Force
    Write-Output ('Fresh read-only binding stored for PID ' + $ClientProcessId + '. Start a new bridge process if the client lifetime changed.')
} finally {
    if (Test-Path -LiteralPath $temporaryBinding) { Remove-Item -LiteralPath $temporaryBinding }
}
