using CUE4Parse.FileProvider;
using CUE4Parse.UE4.Versions;
using System.Text.Json;
using Serilog;
using Serilog.Core;
using Serilog.Events;
using CUE4Parse.Compression;
using CUE4Parse.UE4.AssetRegistry;
using CUE4Parse.MappingsProvider;
using Newtonsoft.Json.Linq;
using CUE4Parse.UE4.Assets;
using CUE4Parse.UE4.Assets.Exports;
using CUE4Parse.UE4.Assets.Exports.Component;
using CUE4Parse.UE4.Assets.Readers;
using CUE4Parse.UE4.Assets.Objects;
using CUE4Parse.UE4.Objects.UObject;
using System.Security.Cryptography;
Log.Logger=new LoggerConfiguration().MinimumLevel.Information().WriteTo.Sink(new ConsoleLog()).CreateLogger();
if(args.Length<2)throw new ArgumentException("Paks path and output directory required");
var directory=args[0];var output=args[1];
var game=Enum.GetNames<EGame>().Contains("GAME_UE5_6")?Enum.Parse<EGame>("GAME_UE5_6"):EGame.GAME_UE5_5;
if(args.Length<2)throw new ArgumentException("Usage: TerrainCollision <Paks> <inventory-directory> [--scan|--mesh-scan|--collision-metadata|--other-worlds]");
var oodle=Environment.GetEnvironmentVariable("ASHES_OODLE_LIBRARY") ?? throw new ArgumentException("Set ASHES_OODLE_LIBRARY to your own Oodle DLL");
OodleHelper.Initialize(Path.GetFullPath(oodle));
using var provider=new DefaultFileProvider(directory,SearchOption.TopDirectoryOnly,new VersionContainer(game),StringComparer.OrdinalIgnoreCase);
provider.MappingsContainer=new TerrainMappings(Path.GetFullPath(Path.Combine(output,"../mappings")));
provider.MappingsContainer.Reload();
provider.Initialize();provider.Mount();provider.LoadVirtualPaths();
var files=provider.Files.Values.Select(f=>new{path=f.Path,size=f.Size}).OrderBy(f=>f.path).ToArray();
Directory.CreateDirectory(output);File.WriteAllText(Path.Combine(output,"archive-files.json"),JsonSerializer.Serialize(files));
var world=files.Where(f=>f.path.Contains("Verra",StringComparison.OrdinalIgnoreCase)).ToArray();
File.WriteAllText(Path.Combine(output,"verra-files.json"),JsonSerializer.Serialize(world));
Console.WriteLine(JsonSerializer.Serialize(new{game=game.ToString(),files=files.Length,verra=world.Length,mounted=provider.MountedVfs.Count,unloaded=provider.UnloadedVfs.Count}));
using var registryReader=provider.CreateReader("AOC/AssetRegistry.bin");
var registry=new FAssetRegistryState(registryReader);
var assets=registry.PreallocatedAssetDataBuffers.Select(a=>new{package=a.PackageName.Text,name=a.AssetName.Text,cls=a.AssetClass.Text,tags=a.TagsAndValues.ToDictionary(p=>p.Key.Text,p=>p.Value)}).ToArray();
var terrain=assets.Where(a=>a.cls.Contains("Landscape") || (a.cls=="World"&&a.package.Contains("Verra"))).ToArray();
File.WriteAllText(Path.Combine(output,"terrain-assets.json"),JsonSerializer.Serialize(terrain));
Console.WriteLine(JsonSerializer.Serialize(new{registry_assets=assets.Length,terrain_assets=terrain.Length,classes=terrain.GroupBy(a=>a.cls).ToDictionary(g=>g.Key,g=>g.Count())}));
if(args.Length>2&&args[2]=="--collision-metadata") {
 ObjectTypeRegistry.RegisterClass("LandscapeHeightfieldCollisionComponent",typeof(TerrainCollisionComponent));
 ObjectTypeRegistry.RegisterClass("LandscapeMeshCollisionComponent",typeof(TerrainCollisionComponent));
 var records=new List<object>();var failures=new List<object>();int scanned=0;
 var packages=new HashSet<string>();
 foreach(string folder in new[]{"cooked","cooked-mesh"}) {
  using var source=JsonDocument.Parse(File.ReadAllText(Path.GetFullPath(Path.Combine(output,"../"+folder+"/manifest.json"))));
  foreach(var tile in source.RootElement.GetProperty("tiles").EnumerateArray())packages.Add(tile.GetProperty("package").GetString()!);
 }
 foreach(string path in packages.Order()) {
  try {
   var package=provider.LoadPackage(path);if(package is not IoPackage io)throw new InvalidDataException("Expected IoStore package");
   for(int i=0;i<io.ExportMap.Length;i++) {
    var entry=io.ExportMap[i];string cls=io.ResolveObjectIndex(entry.ClassIndex)?.Name.Text??"unknown";
    if(cls!="LandscapeHeightfieldCollisionComponent"&&cls!="LandscapeMeshCollisionComponent")continue;
    var component=(TerrainCollisionComponent)package.GetExport(i)!;var owner=component.Outer?.Object?.Value??throw new InvalidDataException("Landscape owner missing");
    var body=owner.Properties.FirstOrDefault(p=>p.Name.Text=="BodyInstance");
    var bodyJson=body==null?null:Newtonsoft.Json.JsonConvert.SerializeObject(body);
    records.Add(new{package=path,name=component.Name,cls,owner=owner.Name,owner_cls=owner.ExportType,actor_enabled=owner.GetOrDefault<bool>("bActorEnableCollision",true),body_json=bodyJson,owner_properties=owner.Properties.Select(p=>p.Name.Text).ToArray(),template=owner.Template?.Name.Text});
   }
  }catch(Exception e){failures.Add(new{package=path,error=e.Message});}
  if(++scanned%100==0)Console.WriteLine(JsonSerializer.Serialize(new{scanned,records=records.Count,failures=failures.Count}));
 }
 File.WriteAllText(Path.GetFullPath(Path.Combine(output,"../collision-metadata.json")),JsonSerializer.Serialize(new{scanned,records,failures},new JsonSerializerOptions{WriteIndented=true}));
 Console.WriteLine(JsonSerializer.Serialize(new{scanned,records=records.Count,failures=failures.Count}));
}
if(args.Length>2 && (args[2]=="--scan"||args[2]=="--mesh-scan"||args[2]=="--other-worlds")){
 bool meshOnly=args[2]=="--mesh-scan";
 bool otherWorlds=args[2]=="--other-worlds";
 ObjectTypeRegistry.RegisterClass("LandscapeHeightfieldCollisionComponent",typeof(TerrainCollisionComponent));
 ObjectTypeRegistry.RegisterClass("LandscapeMeshCollisionComponent",typeof(TerrainCollisionComponent));
 var tiles=new List<object>();var failures=new List<object>();var classes=new Dictionary<string,int>();int scanned=0;
 int limit=args.Length>3?int.Parse(args[3]):int.MaxValue;
 string collisionOut=Path.GetFullPath(Path.Combine(output,otherWorlds?"../cooked-other-worlds":meshOnly?"../cooked-mesh":"../cooked"));Directory.CreateDirectory(collisionOut);
 var worlds=otherWorlds?assets.Where(a=>a.cls=="World"&&!a.package.Contains("Verra")):terrain.Where(a=>a.cls=="World");
 foreach(var asset in worlds.Take(limit)){
  try{
   var package=provider.LoadPackage(asset.package);
   if(package is not IoPackage io)throw new InvalidDataException("Expected IoStore package");
   for(int i=0;i<io.ExportMap.Length;i++){
    var entry=io.ExportMap[i];string cls=io.ResolveObjectIndex(entry.ClassIndex)?.Name.Text??"unknown";
    classes[cls]=classes.GetValueOrDefault(cls)+1;
    if(cls!=(meshOnly?"LandscapeMeshCollisionComponent":"LandscapeHeightfieldCollisionComponent") || entry.ObjectFlags.HasFlag(EObjectFlags.RF_ClassDefaultObject))continue;
    var component=(TerrainCollisionComponent)package.GetExport(i)!;
    if(component.CookedBytes.Length==0)throw new InvalidDataException("Empty cooked landscape collision");
    string hash=Convert.ToHexString(SHA256.HashData(component.CookedBytes)).ToLowerInvariant();
    string filename=hash+".chaos";File.WriteAllBytes(Path.Combine(collisionOut,filename),component.CookedBytes);
    var chain=new List<object>();USceneComponent? node=component;
    for(int depth=0;node!=null&&depth<8;depth++){
     chain.Add(new{name=node.Name,cls=node.ExportType,location=new[]{node.RelativeLocation.X,node.RelativeLocation.Y,node.RelativeLocation.Z},rotation=new[]{node.RelativeRotation.Pitch,node.RelativeRotation.Yaw,node.RelativeRotation.Roll},scale=new[]{node.RelativeScale3D.X,node.RelativeScale3D.Y,node.RelativeScale3D.Z}});
     node=node.AttachParent?.ResolvedObject?.Object?.Value as USceneComponent;
    }
    tiles.Add(new{package=asset.package,name=component.Name,cls,section_x=component.GetOrDefault<int>("SectionBaseX"),section_y=component.GetOrDefault<int>("SectionBaseY"),quads=component.GetOrDefault<int>("CollisionSizeQuads"),simple_quads=component.GetOrDefault<int>("SimpleCollisionSizeQuads"),collision_scale=component.GetOrDefault<float>("CollisionScale"),transform_chain=chain,cooked=filename,cooked_bytes=component.CookedBytes.Length,sha256=hash});
   }
  }catch(Exception e){failures.Add(new{package=asset.package,error=e.Message});}
  scanned++;if(scanned%100==0)Console.WriteLine(JsonSerializer.Serialize(new{scanned,tiles=tiles.Count,failures=failures.Count}));
 }
 File.WriteAllText(Path.Combine(collisionOut,"manifest.json"),JsonSerializer.Serialize(new{status="cooked_collision_extracted_not_yet_decoded",scanned,tiles,failures,classes},new JsonSerializerOptions{WriteIndented=true}));
 Console.WriteLine(JsonSerializer.Serialize(new{scanned,tiles=tiles.Count,failures=failures.Count}));
}
class ConsoleLog:ILogEventSink {public void Emit(LogEvent e){Console.Error.WriteLine(e.RenderMessage());if(e.Exception!=null)Console.Error.WriteLine(e.Exception);}}
class TerrainMappings(string directory):JsonTypeMappingsProvider {
 public override void Load(string path,StringComparer? comparer=null){AddStructs(File.ReadAllText(path));}
 public override void Load(byte[] data,StringComparer? comparer=null){AddStructs(System.Text.Encoding.UTF8.GetString(data));}
 public override void Reload(){AddStructs(File.ReadAllText(Path.Combine(directory,"structs.json")));var enums=JObject.Parse(File.ReadAllText(Path.Combine(directory,"enums.json")));foreach(var item in enums.Properties())MappingsForGame!.Enums[item.Name]=((JObject)item.Value).Properties().ToDictionary(p=>long.Parse(p.Name),p=>p.Value.ToString());}
 public TerrainMappings():this(""){}
 public override TypeMappings? MappingsForGame {get;protected set;}
}
class TerrainCollisionComponent:USceneComponent {
 public byte[] CookedBytes=[];
 public override void Deserialize(FAssetArchive ar,long validPos){
  base.Deserialize(ar,validPos);
  if(!ar.ReadBoolean())throw new InvalidDataException("Expected cooked landscape collision");
  int elementSize=ar.Read<int>(),count=ar.Read<int>();
  if(elementSize!=1||count<0||count>64*1024*1024||ar.Position+count>validPos)throw new InvalidDataException($"Cooked collision array bounds: {elementSize}, {count}");
  CookedBytes=ar.ReadBytes(count);
 }
}
