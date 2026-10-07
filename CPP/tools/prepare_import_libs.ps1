param([string]$VisualStudioPath='C:\Program Files\Microsoft Visual Studio\2022\Community',[string]$DependencyBin='C:\msys64\mingw64\bin')
$ErrorActionPreference='Stop'
$cppRoot=Split-Path -Parent $PSScriptRoot
$msvcToolRoot=(Get-ChildItem (Join-Path $VisualStudioPath 'VC\Tools\MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName+'\bin\Hostx64\x64'
New-Item -ItemType Directory -Path (Join-Path $cppRoot 'vendor\lib') -Force | Out-Null
foreach($entry in @(@{Name='nghttp2';Dll='libnghttp2-14.dll'},@{Name='sqlite3';Dll='libsqlite3-0.dll'},@{Name='crypto';Dll='libcrypto-3-x64.dll'})){
  $exports=& "$msvcToolRoot\dumpbin.exe" /exports (Join-Path $DependencyBin $entry.Dll)
  $lines=@("LIBRARY $($entry.Dll)",'EXPORTS')
  foreach($line in $exports){if($line -match '^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+(\S+)'){$lines+=$Matches[1]}}
  if($lines.Count -lt 3){throw 'DLL export enumeration failed'}
  $def=Join-Path $cppRoot "vendor\lib\$($entry.Name).def"
  Set-Content -LiteralPath $def -Value $lines -Encoding ascii
  & "$msvcToolRoot\lib.exe" /nologo /machine:x64 "/def:$def" "/out:$cppRoot\vendor\lib\$($entry.Name).lib"
  if($LASTEXITCODE -ne 0){throw 'Import library creation failed'}
}
