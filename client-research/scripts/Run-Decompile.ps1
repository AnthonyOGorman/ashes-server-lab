param(
    [string]$Manifest = 'initial.tsv',
    [string]$BatchName = 'initial',
    [ValidateRange(1,300)][int]$TimeoutSeconds = 30
)
$ErrorActionPreference = 'Stop'
$researchRoot = Split-Path -Parent $PSScriptRoot
$ghidraRoot = 'C:\Tools\ghidra_12.0.2_PUBLIC_20260129\ghidra_12.0.2_PUBLIC'
$javaPath = 'C:\Program Files\Amazon Corretto\jdk21.0.6_7\bin\java.exe'
if ($BatchName -notmatch '^[a-zA-Z0-9_-]+$') { throw 'BatchName must contain letters, digits, underscores or hyphens.' }
$manifestPath = Join-Path (Join-Path $researchRoot 'batches') $Manifest
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Manifest missing: $manifestPath" }
& $javaPath '-Xmx4G' '-XX:ParallelGCThreads=2' '-XX:CICompilerCount=2' '-Djava.system.class.loader=ghidra.GhidraClassLoader' '-Dfile.encoding=UTF8' '-Duser.language=en' '-Duser.country=US' "-Dapplication.settingsdir=$researchRoot\ghidra-user\settings" "-Dapplication.cachedir=$researchRoot\ghidra-user\cache" "-Dapplication.tempdir=$researchRoot\ghidra-user\temp" '-cp' "$ghidraRoot\Ghidra\Framework\Utility\lib\Utility.jar" ghidra.Ghidra ghidra.app.util.headless.AnalyzeHeadless "$researchRoot\ghidra-project" AshesExactClient -process AOCClient-Win64-Shipping.exe -noanalysis -scriptPath $PSScriptRoot -postScript BatchDecompile.java $manifestPath "$researchRoot\decompiled\$BatchName" $TimeoutSeconds -max-cpu 2 -log "$researchRoot\ghidra-$BatchName.log"
if ($LASTEXITCODE -ne 0) { throw "Ghidra failed: $LASTEXITCODE" }
