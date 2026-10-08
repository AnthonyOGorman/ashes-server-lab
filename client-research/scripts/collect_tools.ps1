$ErrorActionPreference = 'Stop'
$researchRoot = Split-Path -Parent $PSScriptRoot
$toolsToInspect = @(
    @{ name='Ghidra'; path='C:\Tools\ghidra_12.0.2_PUBLIC_20260129\ghidra_12.0.2_PUBLIC\Ghidra\Framework\Utility\lib\Utility.jar'; version='12.0.2'; purpose='Native disassembly and C pseudocode'; source='https://github.com/NationalSecurityAgency/ghidra'; status='Headless decompilation tested' },
    @{ name='JDK'; path='C:\Program Files\Amazon Corretto\jdk21.0.6_7\bin\java.exe'; version='21.0.6'; purpose='Ghidra runtime'; source='https://github.com/corretto/corretto-21'; status='Tested with Ghidra' },
    @{ name='ILSpyCmd'; path=(Join-Path $researchRoot 'tools\ilspy\ilspycmd.exe'); version='11.1.0.9782'; purpose='C# decompilation and managed metadata'; source='https://github.com/icsharpcode/ILSpy'; status='Installed from NuGet and tested' },
    @{ name='Capstone'; path=(Join-Path $researchRoot 'vendor\capstone\lib\capstone.dll'); version='5.0.6'; purpose='Automated x64 instruction and reference index'; source='https://www.capstone-engine.org'; status='Installed from PyPI and tested' },
    @{ name='CUE4Parse'; path=(Join-Path $researchRoot 'scripts\asset-index\bin\Release\net10.0\CUE4Parse.dll'); version='1.2.2.202610'; purpose='Unreal archives, registry, headers, Blueprint bytecode and bounded class metadata'; source='https://github.com/FabianFG/CUE4Parse'; status='Cached package built and tested; partial class exports explicitly rejected' },
    @{ name='ManagedMetadataReader'; path=(Join-Path $researchRoot 'scripts\metadata-reader\bin\Release\net10.0\MetadataReader.dll'); version='Local research helper'; purpose='Read-only MethodDef ownership, signatures and IL fingerprints'; source='https://learn.microsoft.com/dotnet/api/system.reflection.metadata'; status='Built and tested across all 640 installed managed modules without loading assemblies' },
    @{ name='FModel'; path='C:\Tools\FModel\FModel.exe'; version='Read file metadata'; purpose='Unreal asset inspection GUI'; source='https://github.com/4sval/FModel'; status='Existing installation inventoried; GUI not launched' },
    @{ name='x64dbg'; path='C:\Tools\x64dbg\release\x64\x64dbg.exe'; version='Read file metadata'; purpose='Native debugger'; source='https://github.com/x64dbg/x64dbg'; status='Existing installation inventoried; debugger not attached' },
    @{ name='dnSpy'; path='C:\Tools\dnSpy-net-win64\dnSpy.Console.exe'; version='Read file metadata'; purpose='Independent managed decompiler'; source='https://github.com/dnSpy/dnSpy'; status='Launcher decompilation tested; older output has async reconstruction artifacts' },
    @{ name='UnrealPak'; path='C:\Tools\UnrealPakTool-master\UnrealPak.exe'; version='Read file metadata'; purpose='Pak archive listing and extraction'; source='https://github.com/EpicGames/UnrealEngine'; status='Existing installation inventoried; historical listing evidence exists' },
    @{ name='Dumper7'; path='E:\Ashes Of Creation\AOC-SDK\SDK\Basic.hpp'; version='Existing generated SDK'; purpose='Unreal reflection type and wrapper inventory'; source='https://github.com/Encryqed/Dumper-7'; status='Saved SDK parsed; dumper not injected' }
)
$records = foreach ($tool in $toolsToInspect) {
    $record = @{} + $tool
    $record.exists = Test-Path -LiteralPath $tool.path
    if ($record.exists) {
        $file = Get-Item -LiteralPath $tool.path
        $record.size = $file.Length
        $record.sha256 = (Get-FileHash -LiteralPath $tool.path -Algorithm SHA256).Hash.ToLowerInvariant()
        $record.fileVersion = $file.VersionInfo.FileVersion
    }
    $record
}
$records | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $researchRoot 'toolchain.json') -Encoding utf8
$records | ForEach-Object { [pscustomobject]$_ } | Select-Object name,exists,status
