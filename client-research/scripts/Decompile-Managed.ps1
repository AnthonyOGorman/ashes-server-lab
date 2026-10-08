$ErrorActionPreference = 'Stop'
$researchRoot = Split-Path -Parent $PSScriptRoot
$launcherRoot = 'E:\Games\Steam Library\steamapps\common\Ashes of Creation\Launcher'
$env:DOTNET_ROOT = 'E:\Ashes Of Creation GPT\CPP\vendor\terrain\dotnet-sdk10'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$ilspyPath = Join-Path $researchRoot 'tools\ilspy\ilspycmd.exe'
$assemblies = @('IntrepidStudiosLauncher.dll','Patcher.dll','PatchModels.dll','IcsProtos.dll','GrpcUtils.dll','WebQueueUtils.dll','Analytics.dll','SteamHelper\SteamHelper.dll')
foreach ($assembly in $assemblies) {
    $assemblyPath = Join-Path $launcherRoot $assembly
    $assemblyName = [System.IO.Path]::GetFileNameWithoutExtension($assemblyPath)
    $outPath = Join-Path $researchRoot "decompiled\managed\$assemblyName"
    $tablePath = Join-Path $researchRoot "index\managed-$assemblyName-methods.json"
    & $ilspyPath -p -o $outPath -r $launcherRoot $assemblyPath
    if ($LASTEXITCODE -ne 0) { throw "Decompile failed: $assembly" }
    & $ilspyPath --dump-table MethodDef --json $assemblyPath | Set-Content -LiteralPath $tablePath -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "Method table failed: $assembly" }
    Write-Output "DECOMPILED $assemblyName"
}
