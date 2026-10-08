using CUE4Parse.FileProvider;
using CUE4Parse.UE4.Versions;
using CUE4Parse.UE4.AssetRegistry;
using System.Security.Cryptography;
using System.Text.Json;
using CUE4Parse.Compression;
using CUE4Parse.UE4.Assets;
using CUE4Parse.MappingsProvider;
using CUE4Parse.UE4.Objects.UObject;
using JsonConvert=Newtonsoft.Json.JsonConvert;
using CUE4Parse.UE4.Assets.Exports;
using Serilog;
using CUE4Parse.UE4.Assets.Readers;
using CUE4Parse.UE4.IO.Objects;

if(args.Length<2||args.Length>6)throw new ArgumentException("Archive-directory output-directory [--headers|--bytecode|--class-metadata|--class-schema|--defaults|--asset-values] [limit] [structs-json] [enums-json]");
string source=Path.GetFullPath(args[0]), output=Path.GetFullPath(args[1]);
Directory.CreateDirectory(output);
string oodle=Path.GetFullPath(Path.Combine(AppContext.BaseDirectory,"../../../../../../CPP/vendor/terrain/oodle-data-shared.dll"));
if(File.Exists(oodle))OodleHelper.Initialize(oodle);
bool bytecodeMode=args.Length>=3&&args[2]=="--bytecode";
bool defaultsMode=args.Length>=3&&args[2]=="--defaults";
bool assetValuesMode=args.Length>=3&&args[2]=="--asset-values";
var valueClasses=new HashSet<string>{"InputAction","AOCInputMappingContext","PlayerInputConfig","DataTable","BehaviorTree","BlackboardData","StateTree"};
bool schemaMode=args.Length>=3&&(args[2]=="--class-schema"||defaultsMode||assetValuesMode);
bool classMode=args.Length>=3&&(args[2]=="--class-metadata"||schemaMode);
if(schemaMode&&args.Length!=6)throw new ArgumentException("--class-schema requires structs and enums JSON paths");
string classPrefix=assetValuesMode?"asset-values-"+Path.GetFileName(args[4]).Split('-')[3]:defaultsMode?"blueprint-defaults-"+Path.GetFileName(args[4]).Split('-')[3]:schemaMode?"blueprint-class-schema-v3-consumption":"blueprint-class-metadata";
string? schemaHash=schemaMode?Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[4]))).ToLowerInvariant():null;
string? enumSchemaHash=schemaMode?Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[5]))).ToLowerInvariant():null;
CUE4Parse.Globals.FatalObjectSerializationErrors=true;
var warningSink=new ResearchWarningSink();
CUE4Parse.CUE4ParseLog.UseLogger(new Serilog.LoggerConfiguration().MinimumLevel.Debug().WriteTo.Console().WriteTo.Sink(warningSink).CreateLogger());
var game=bytecodeMode||classMode?EGame.GAME_AshesOfCreation:EGame.GAME_UE5_6;
var version=new VersionContainer(game);
using var provider=new DefaultFileProvider(source,SearchOption.TopDirectoryOnly,version,StringComparer.OrdinalIgnoreCase);
// The IoPackage constructor insists on a mappings container even for header access.
// Empty mappings permit header construction; no UObject export is deserialized here.
if(args.Length>=3&&args[2]=="--headers")provider.MappingsContainer=new HeaderOnlyMappings();
if(bytecodeMode){provider.MappingsContainer=new FunctionOnlyMappings();provider.ReadScriptData=true;}
if(classMode)provider.MappingsContainer=schemaMode?new SdkCandidateMappings(args[4],args[5]):new ClassMetadataMappings();
provider.Initialize();provider.Mount();provider.LoadVirtualPaths();
File.WriteAllText(Path.Combine(output,"unmounted-containers.json"),JsonSerializer.Serialize(provider.UnloadedVfs.Select(v=>new{type=v.GetType().FullName,name=v.GetType().GetProperty("Name")?.GetValue(v)?.ToString(),path=v.GetType().GetProperty("Path")?.GetValue(v)?.ToString()})));
using(var writer=new StreamWriter(Path.Combine(output,"archive-files.jsonl"))) {
 foreach(var f in provider.Files.Values.OrderBy(f=>f.Path))writer.WriteLine(JsonSerializer.Serialize(new{path=f.Path,size=f.Size}));
}
using var reader=provider.CreateReader("AOC/AssetRegistry.bin");
var registry=new FAssetRegistryState(reader);
using(var writer=new StreamWriter(Path.Combine(output,"assets.jsonl"))) {
 foreach(var a in registry.PreallocatedAssetDataBuffers)writer.WriteLine(JsonSerializer.Serialize(new{package=a.PackageName.Text,path=a.PackagePath.Text,name=a.AssetName.Text,cls=a.AssetClass.Text,chunks=a.ChunkIDs,package_flags=(uint)a.PackageFlags,tags=a.TagsAndValues.ToDictionary(p=>p.Key.Text,p=>p.Value)}));
}
var summary=new {
 source, parser="CUE4Parse 1.2.2.202610", version=game.ToString(),
 mounted=provider.MountedVfs.Count,unloaded=provider.UnloadedVfs.Count,
 files=provider.Files.Count,assets=registry.PreallocatedAssetDataBuffers.Length,
 dependency_nodes=registry.PreallocatedDependsNodeDataBuffers.Length,
 package_records=registry.PreallocatedPackageDataBuffers.Length,
 asset_classes=registry.PreallocatedAssetDataBuffers.GroupBy(a=>a.AssetClass.Text).OrderByDescending(g=>g.Count()).ToDictionary(g=>g.Key,g=>g.Count()),
 limitations=new[]{"Archive and registry inventory does not prove per-asset property or Blueprint bytecode decoding.","No encryption keys supplied; unmounted containers are recorded as gaps.","UE5.6 is a parser version assumption to validate against package serialization and binary build strings."}
};
string json=JsonSerializer.Serialize(summary,new JsonSerializerOptions{WriteIndented=true});
File.WriteAllText(Path.Combine(output,classMode?classPrefix+"-parser-summary.json":bytecodeMode?"bytecode-parser-summary.json":"asset-summary.json"),json);Console.WriteLine(json);
if(args.Length==3&&args[2]=="--headers") {
 var classes=new HashSet<string>{"Blueprint","WidgetBlueprint","AnimBlueprint","InputAction","AOCInputMappingContext","PlayerInputConfig","DataTable","StateTree","BehaviorTree","BlackboardData"};
 var packages=registry.PreallocatedAssetDataBuffers.Where(a=>classes.Contains(a.AssetClass.Text)).Select(a=>a.PackageName.Text).Distinct().Order().ToArray();
 string headerFile=Path.Combine(output,"package-headers-v2.jsonl");
 var done=new HashSet<string>();
 if(File.Exists(headerFile))foreach(string line in File.ReadLines(headerFile)){using var doc=JsonDocument.Parse(line);done.Add(doc.RootElement.GetProperty("package").GetString()!);}
 using var writer=new StreamWriter(headerFile,true);
 int ok=0,failed=0;
 foreach(string path in packages.Where(p=>!done.Contains(p))) {
  try {
   var package=provider.LoadPackage(path);
   if(package is not IoPackage io)throw new InvalidDataException("Expected IoStore package");
   var exports=io.ExportMap.Select((e,i)=>new{index=i,name=io.CreateFNameFromMappedName(e.ObjectName).Text,cls=io.ResolveObjectIndex(e.ClassIndex)?.Name.Text,size=e.CookedSerialSize,offset=e.CookedSerialOffset,flags=e.ObjectFlags.ToString()}).ToArray();
   writer.WriteLine(JsonSerializer.Serialize(new{package=path,status="headers_parsed",scope="Header tables only; empty schema container; UObject properties and Blueprint bytecode not deserialized",names=io.NameMap.Select(n=>n.Name).ToArray(),exports}));ok++;
  }catch(Exception e){writer.WriteLine(JsonSerializer.Serialize(new{package=path,status="failed",error=e.ToString()}));failed++;}
  if((ok+failed)%100==0){writer.Flush();Console.WriteLine(JsonSerializer.Serialize(new{header_ok=ok,header_failed=failed,selected=packages.Length,previously_done=done.Count}));}
 }
 writer.Flush();Console.WriteLine(JsonSerializer.Serialize(new{header_ok=ok,header_failed=failed,selected=packages.Length,previously_done=done.Count}));
}
if(bytecodeMode) {
 int limit=args.Length>=4?int.Parse(args[3]):10;
 if(limit<1||limit>10000)throw new ArgumentOutOfRangeException("limit");
 var candidates=new List<string>();
 foreach(string line in File.ReadLines(Path.Combine(output,"package-headers-v2.jsonl"))) {
  using var doc=JsonDocument.Parse(line);var p=doc.RootElement;
  if(p.GetProperty("exports").EnumerateArray().Any(e=>e.TryGetProperty("cls",out var c)&&c.GetString()=="Function"))candidates.Add(p.GetProperty("package").GetString()!);
 }
 using var writer=new StreamWriter(Path.Combine(output,"blueprint-bytecode.jsonl"),true);
 var done=new HashSet<string>();
 string progressFile=Path.Combine(output,"bytecode-packages.jsonl");
 if(File.Exists(progressFile))foreach(string line in File.ReadLines(progressFile)){using var doc=JsonDocument.Parse(line);done.Add(doc.RootElement.GetProperty("package").GetString()!);}
 using var progress=new StreamWriter(progressFile,true);
 int parsed=0,failed=0,packages=0;
 foreach(string path in candidates.Where(p=>!done.Contains(p)).Take(limit)) {
  int packageParsed=0,packageFailed=0;
  try {
   var io=(IoPackage)provider.LoadPackage(path);
   for(int i=0;i<io.ExportMap.Length;i++) {
    if(io.ResolveObjectIndex(io.ExportMap[i].ClassIndex)?.Name.Text!="Function")continue;
    string name=io.CreateFNameFromMappedName(io.ExportMap[i].ObjectName).Text;
    try {
     var f=((IPackage)io).GetExport(i) as UFunction??throw new InvalidDataException("Function export was not UFunction");
     var script=f.ScriptBytecode;
     string status=script==null||script.Length==0?"no_decoded_script":script.Last().Token.ToString()=="EX_EndOfScript"?"decoded_script_candidate":"partial_script_candidate";
     writer.WriteLine(JsonSerializer.Serialize(new{package=path,name,status,flags=f.FunctionFlags.ToString(),expressions=script?.Length??0,script_json=JsonConvert.SerializeObject(f)}));parsed++;packageParsed++;
    }catch(Exception e){writer.WriteLine(JsonSerializer.Serialize(new{package=path,name,status="failed",error=e.ToString()}));failed++;packageFailed++;}
   }
  }catch(Exception e){writer.WriteLine(JsonSerializer.Serialize(new{package=path,status="package_failed",error=e.ToString()}));failed++;packageFailed++;}
  progress.WriteLine(JsonSerializer.Serialize(new{package=path,parsed=packageParsed,failed=packageFailed}));writer.Flush();progress.Flush();packages++;
 }
 Console.WriteLine(JsonSerializer.Serialize(new{packages,parsed,failed,selected=candidates.Count,previously_done=done.Count}));
}
if(classMode) {
 int limit=args.Length>=4?int.Parse(args[3]):10;
 if(limit<1||limit>10000)throw new ArgumentOutOfRangeException("limit");
 var candidates=new List<string>();
 foreach(string line in File.ReadLines(Path.Combine(output,"package-headers-v2.jsonl"))) {
  using var doc=JsonDocument.Parse(line);var p=doc.RootElement;
  if(p.GetProperty("exports").EnumerateArray().Any(e=>e.TryGetProperty("cls",out var c)&&(assetValuesMode?valueClasses.Contains(c.GetString()??""):c.GetString()?.EndsWith("BlueprintGeneratedClass")==true)))candidates.Add(p.GetProperty("package").GetString()!);
 }
 using var writer=new StreamWriter(Path.Combine(output,classPrefix+".jsonl"),true);
 var done=new HashSet<string>();string progressFile=Path.Combine(output,classPrefix+"-packages.jsonl");
 // Keep the original empty-schema checkpoint filename for compatibility.
 if(!schemaMode)progressFile=Path.Combine(output,"class-metadata-packages.jsonl");
 if(File.Exists(progressFile))foreach(string line in File.ReadLines(progressFile)){using var doc=JsonDocument.Parse(line);done.Add(doc.RootElement.GetProperty("package").GetString()!);}
 using var progress=new StreamWriter(progressFile,true);int parsed=0,failed=0,packages=0;
 foreach(string path in candidates.Where(p=>!done.Contains(p)).Take(limit)) {
  int packageParsed=0,packageFailed=0;
  try {
   var io=(IoPackage)provider.LoadPackage(path);
   for(int i=0;i<io.ExportMap.Length;i++) {
    string? cls=io.ResolveObjectIndex(io.ExportMap[i].ClassIndex)?.Name.Text;
    if(assetValuesMode?!valueClasses.Contains(cls??""):defaultsMode?!io.ExportMap[i].ObjectFlags.HasFlag(EObjectFlags.RF_ClassDefaultObject):cls?.EndsWith("BlueprintGeneratedClass")!=true)continue;
    string name=io.CreateFNameFromMappedName(io.ExportMap[i].ObjectName).Text;
    warningSink.Messages.Clear();
    try {
     var obj=((IPackage)io).GetExport(i)??throw new InvalidDataException("Missing export object");
     var c=obj as UClass;
     // IoPackage can return partially constructed exports after a swallowed parser
     // exception. Require the terminal UClass records, not just an object instance.
     if(!defaultsMode&&!assetValuesMode&&(c==null||c.FuncMap==null||c.ClassWithin==null||c.ClassDefaultObject==null||!c.bCooked))throw new InvalidDataException("Incomplete class export; terminal UClass metadata missing");
     // Empty metaclass schemas are admissible only when there are no property values.
     if(!schemaMode&&obj.Properties.Count!=0)throw new InvalidDataException("Unexpected properties with empty schema");
     long? consumedSerialBytes=null,expectedSerialBytes=null;
     if(schemaMode) {
      // Independently replay this export with a visible archive cursor. The library's
      // normal lazy loader hides the final position and does not enforce consumption.
      // This offset formula is restricted to the inspected UE5.3+ IoStore path.
      if(game<EGame.GAME_UE5_3)throw new InvalidDataException("Consumption replay requires UE5.3+ layout");
      using var raw=provider.CreateReader(path+".uasset");
      var ar=new FAssetArchive(raw,io);
      var zen=new FZenPackageSummary(ar);
      ar.AbsoluteOffset=(int)(zen.CookedHeaderSize-zen.HeaderSize);
      long start=(long)zen.HeaderSize+(long)io.ExportMap[i].CookedSerialOffset;
      ar.Position=start;expectedSerialBytes=(long)io.ExportMap[i].CookedSerialSize;
      var replay=(UObject)(Activator.CreateInstance(obj.GetType())??throw new InvalidDataException("Cannot construct replay object"));
      replay.Name=obj.Name;replay.Class=obj.Class;replay.Outer=obj.Outer;replay.Super=obj.Super;replay.Template=obj.Template;replay.Flags=obj.Flags;
      replay.Deserialize(ar,start+expectedSerialBytes.Value);
      consumedSerialBytes=ar.Position-start;
     }
     string objectJson=JsonConvert.SerializeObject(obj);
     writer.WriteLine(JsonSerializer.Serialize(new{package=path,name,cls,status=assetValuesMode?"inferred_schema_asset_candidate":defaultsMode?"inferred_schema_default_candidate":schemaMode?"inferred_schema_class_candidate":"class_metadata_candidate",schemaHash,enumSchemaHash,expectedSerialBytes,consumedSerialBytes,properties=obj.Properties.Count,fields=c?.ChildProperties?.Length??0,functions=c?.FuncMap?.Count??0,parserWarnings=warningSink.Messages.ToArray(),class_json=objectJson}));parsed++;packageParsed++;
    }catch(Exception e){writer.WriteLine(JsonSerializer.Serialize(new{package=path,name,cls,status="failed",parserWarnings=warningSink.Messages.ToArray(),error=e.ToString()}));failed++;packageFailed++;}
   }
  }catch(Exception e){writer.WriteLine(JsonSerializer.Serialize(new{package=path,status="package_failed",error=e.ToString()}));failed++;packageFailed++;}
  progress.WriteLine(JsonSerializer.Serialize(new{package=path,parsed=packageParsed,failed=packageFailed}));writer.Flush();progress.Flush();packages++;
 }
 Console.WriteLine(JsonSerializer.Serialize(new{packages,parsed,failed,selected=candidates.Count,previously_done=done.Count}));
}

sealed class ResearchWarningSink:Serilog.Core.ILogEventSink {
 public readonly List<string> Messages=new();
 public void Emit(Serilog.Events.LogEvent e){if(e.Level>=Serilog.Events.LogEventLevel.Warning)Messages.Add(e.RenderMessage());}
}

sealed class HeaderOnlyMappings:AbstractTypeMappingsProvider {
 public override TypeMappings? MappingsForGame{get;protected set;}=new TypeMappings();
 public override void Reload(){}
 public override void Load(string path,StringComparer? comparer=null)=>throw new NotSupportedException("Header-only analysis");
 public override void Load(byte[] bytes,StringComparer? comparer=null)=>throw new NotSupportedException("Header-only analysis");
}

sealed class FunctionOnlyMappings:JsonTypeMappingsProvider {
 public FunctionOnlyMappings()=>Reload();
 public override void Reload()=>AddStructs("[{\"name\":\"Object\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"Field\",\"superType\":\"Object\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"Struct\",\"superType\":\"Field\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"Function\",\"superType\":\"Struct\",\"propertyCount\":0,\"properties\":[]}]");
 public override void Load(string path,StringComparer? comparer=null)=>throw new NotSupportedException("Function-only analysis");
 public override void Load(byte[] bytes,StringComparer? comparer=null)=>throw new NotSupportedException("Function-only analysis");
}

sealed class ClassMetadataMappings:JsonTypeMappingsProvider {
 public ClassMetadataMappings()=>Reload();
 public override void Reload()=>AddStructs("[{\"name\":\"Object\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"Field\",\"superType\":\"Object\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"Struct\",\"superType\":\"Field\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"Class\",\"superType\":\"Struct\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"BlueprintGeneratedClass\",\"superType\":\"Class\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"WidgetBlueprintGeneratedClass\",\"superType\":\"BlueprintGeneratedClass\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"AnimBlueprintGeneratedClass\",\"superType\":\"BlueprintGeneratedClass\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"ControlRigBlueprintGeneratedClass\",\"superType\":\"BlueprintGeneratedClass\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"GameplayAbilityBlueprintGeneratedClass\",\"superType\":\"BlueprintGeneratedClass\",\"propertyCount\":0,\"properties\":[]},{\"name\":\"RigVMBlueprintGeneratedClass\",\"superType\":\"BlueprintGeneratedClass\",\"propertyCount\":0,\"properties\":[]}]");
 public override void Load(string path,StringComparer? comparer=null)=>throw new NotSupportedException("Class metadata only");
 public override void Load(byte[] bytes,StringComparer? comparer=null)=>throw new NotSupportedException("Class metadata only");
}

sealed class SdkCandidateMappings:JsonTypeMappingsProvider {
 private readonly string structsPath,enumsPath;
 public SdkCandidateMappings(string structs,string enums){structsPath=structs;enumsPath=enums;Reload();}
 public override void Reload(){AddStructs(File.ReadAllText(structsPath));AddEnums(File.ReadAllText(enumsPath));}
 public override void Load(string path,StringComparer? comparer=null)=>throw new NotSupportedException("Explicit SDK candidate files only");
 public override void Load(byte[] bytes,StringComparer? comparer=null)=>throw new NotSupportedException("Explicit SDK candidate files only");
}
