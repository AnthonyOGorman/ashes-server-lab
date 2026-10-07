[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',
    [switch]$SkipTests,
    [string]$DependencyBin = 'C:\msys64\mingw64\bin'
)

$ErrorActionPreference = 'Stop'
$cppRoot = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) {
    throw 'Visual Studio Installer is missing. Install Visual Studio 2022 with Desktop development with C++.'
}
$visualStudio = & $vswhere -latest -version '[17.0,18.0)' -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $visualStudio) { throw 'Visual Studio 2022 C++ tools were not found.' }
$cmakeDirectory = Join-Path $visualStudio 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin'
$cmake = Join-Path $cmakeDirectory 'cmake.exe'
$ctest = Join-Path $cmakeDirectory 'ctest.exe'
foreach ($tool in @($cmake, $ctest)) {
    if (-not (Test-Path -LiteralPath $tool)) { throw "Required Visual Studio CMake tool is missing: $tool" }
}

foreach ($library in @('nghttp2', 'sqlite3', 'crypto')) {
    if (-not (Test-Path -LiteralPath (Join-Path $cppRoot "vendor\lib\$library.lib"))) {
        & (Join-Path $PSScriptRoot 'prepare_import_libs.ps1') -VisualStudioPath $visualStudio -DependencyBin $DependencyBin
        break
    }
}

Push-Location $cppRoot
try {
    & $cmake --preset windows-msvc "-DCMAKE_GENERATOR_INSTANCE=$visualStudio" "-DASHES_DEPENDENCY_BIN=$DependencyBin"
    if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed.' }
    $preset = $Configuration.ToLowerInvariant()
    & $cmake --build --preset $preset --parallel
    if ($LASTEXITCODE -ne 0) { throw 'C++ build failed. Stop the isolated C++ lab before rebuilding its executable.' }
    if (-not $SkipTests) {
        & $ctest --preset $preset
        if ($LASTEXITCODE -ne 0) { throw 'Native C++ tests failed.' }
    }
    Write-Host "Built with Visual Studio: $(Join-Path $cppRoot "build\msvc\$Configuration\ashes_lab.exe")"
} finally {
    Pop-Location
}
