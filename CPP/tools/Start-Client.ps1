[CmdletBinding()]
param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$cppRoot = Split-Path -Parent $PSScriptRoot
$config = Get-Content -LiteralPath (Join-Path $cppRoot 'config\backend.json') -Raw | ConvertFrom-Json
$baseUrl = "http://127.0.0.1:$($config.dashboard_port)"
function Get-LabState {
    try { return Invoke-RestMethod -Uri "$baseUrl/api/state" -TimeoutSec 3 } catch { return $null }
}
try {
    $state = Get-LabState
    if (-not $state) {
        $backend = Join-Path $cppRoot 'build\msvc\Release\ashes_lab.exe'
        if (-not (Test-Path -LiteralPath $backend)) { $backend = Join-Path $cppRoot 'build\msvc\Debug\ashes_lab.exe' }
        if (-not (Test-Path -LiteralPath $backend)) { throw 'Build the C++ lab first using CPP\tools\Build-CPP.ps1.' }
        $logDirectory = Join-Path $cppRoot 'logs'
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
        $arguments = '--root "{0}" --start-services' -f $cppRoot
        $backendProcess = Start-Process -FilePath $backend -ArgumentList $arguments -WorkingDirectory $cppRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory 'launcher-backend-stdout.log') -RedirectStandardError (Join-Path $logDirectory 'launcher-backend-stderr.log')
        $deadline = [DateTime]::UtcNow.AddSeconds(45)
        do {
            Start-Sleep -Milliseconds 300
            $state = Get-LabState
            if ($state) { break }
            if ($backendProcess.HasExited) { throw "The C++ backend exited. See $logDirectory\launcher-backend-stderr.log." }
        } while ([DateTime]::UtcNow -lt $deadline)
        if (-not $state) { throw 'The C++ dashboard did not become ready within 45 seconds.' }
    }
    if ($state.backend -ne 'C++') { throw "A different service is using $baseUrl. Close it or change the C++ dashboard port." }
    $result = Invoke-RestMethod -Uri "$baseUrl/api/control" -Method Post -ContentType 'application/json' -Body '{"action":"launch_client"}' -TimeoutSec 45
    if (-not $result.ok) { throw $result.message }
    Write-Host $result.message
    if (-not $NoBrowser) { Start-Process "$baseUrl/" }
} catch {
    Write-Host "Could not start the local client: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
