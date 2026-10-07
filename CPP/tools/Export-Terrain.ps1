[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OodleLibrary,
    [string]$Python = 'python',
    [string]$DotNet = 'dotnet',
    [string]$PackageCache
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskConfig = Get-Content -LiteralPath (Join-Path $taskRoot 'config\backend.json') -Raw | ConvertFrom-Json
$taskExe = $taskConfig.client_exe
if ((Get-FileHash -LiteralPath $taskExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskConfig.client_sha256) { throw 'Client build differs.' }
$taskBin = Split-Path -Parent $taskExe
$taskGame = Split-Path -Parent (Split-Path -Parent $taskBin)
$taskPaks = Join-Path $taskGame 'Content\Paks'
if (-not (Test-Path -LiteralPath $taskPaks)) { throw "Paks directory missing: $taskPaks" }
$taskOodle = (Resolve-Path -LiteralPath $OodleLibrary).Path
$taskOldOodle = $env:ASHES_OODLE_LIBRARY
$taskOutput = Join-Path $taskRoot 'data\terrain-offline'
New-Item -ItemType Directory -Path "$taskOutput\mappings","$taskOutput\inventory" -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $taskRoot 'config\terrain-mappings\structs.json'),(Join-Path $taskRoot 'config\terrain-mappings\enums.json') -Destination "$taskOutput\mappings"
Copy-Item -LiteralPath (Join-Path $taskRoot 'config\terrain-defaults.json') -Destination "$taskOutput\collision-defaults.json"
try {
    $env:ASHES_OODLE_LIBRARY = $taskOodle
    $taskProject = Join-Path $PSScriptRoot 'terrain-collision\TerrainCollision.csproj'
    $taskRestore = @('restore', $taskProject, '--configfile', (Join-Path $PSScriptRoot 'terrain-collision\NuGet.Config'))
    if ($PackageCache) { $taskRestore += @('--packages', $PackageCache) }
    & $DotNet @taskRestore
    if ($LASTEXITCODE -ne 0) { throw 'Offline extractor dependency restore failed.' }
    & $DotNet build $taskProject -c Release --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Offline extractor build failed.' }
    $taskParser = Join-Path $PSScriptRoot 'terrain-collision\bin\Release\net10.0\TerrainCollision.dll'
    foreach ($taskMode in @('--scan','--mesh-scan','--collision-metadata')) {
        & $DotNet $taskParser $taskPaks "$taskOutput\inventory" $taskMode
        if ($LASTEXITCODE -ne 0) { throw "Archive extraction failed: $taskMode" }
    }
    foreach ($taskScript in @('decode_terrain_collision.py','decode_terrain_mesh.py','admit_terrain_collision.py')) {
        & $Python (Join-Path $PSScriptRoot $taskScript)
        if ($LASTEXITCODE -ne 0) { throw "Terrain preparation failed: $taskScript" }
    }
    $taskTest = Join-Path $taskRoot 'build\msvc\Release\ashes_terrain_tests.exe'
    & $taskTest $taskRoot
    if ($LASTEXITCODE -ne 0) { throw 'Native terrain validation failed.' }
    Write-Host 'Terrain prepared. Start the lab, or use Reload collision cache if it is already running.'
} finally { $env:ASHES_OODLE_LIBRARY = $taskOldOodle }
