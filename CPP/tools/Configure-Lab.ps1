[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ClientRoot,
    [switch]$InstallLocalEOS,
    [switch]$RestoreOriginalEOS,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
if ($InstallLocalEOS -and $RestoreOriginalEOS) { throw 'Choose install or restore.' }
$taskExe = Join-Path $ClientRoot 'Game\AOC\Binaries\Win64\AOCClient-Win64-Shipping.exe'
if ($InstallLocalEOS -or $RestoreOriginalEOS) {
    $taskResolvedExe = (Resolve-Path -LiteralPath $taskExe).Path
    foreach ($taskProcess in (Get-Process -Name AOCClient-Win64-Shipping -ErrorAction SilentlyContinue)) {
        if ($taskProcess.Path -eq $taskResolvedExe) { throw 'Close this game client before replacing its EOS library.' }
    }
}
$taskArguments = @((Join-Path $PSScriptRoot 'configure_client.py'), '--client-root', $ClientRoot)
if ($InstallLocalEOS) { $taskArguments += '--install-eos' }
if ($RestoreOriginalEOS) { $taskArguments += '--restore-eos' }
& $Python @taskArguments
if ($LASTEXITCODE -ne 0) { throw 'Client preparation failed.' }
