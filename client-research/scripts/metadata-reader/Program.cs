using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;

if(args.Length!=2)throw new ArgumentException("module-manifest.tsv output.jsonl");
using var output=new StreamWriter(args[1]);
foreach(string line in File.ReadLines(args[0])) {
 var fields=line.Split('\t'); if(fields.Length!=2)throw new InvalidDataException("Manifest needs path and expected SHA256");
 string path=fields[0], expected=fields[1];
 try {
  using var stream=File.OpenRead(path);
  string hash=Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
  if(hash!=expected)throw new InvalidDataException("Input SHA256 changed");stream.Position=0;
  using var pe=new PEReader(stream);
  if(!pe.HasMetadata)throw new InvalidDataException("No managed metadata");
  var metadata=pe.GetMetadataReader();
  string TypeName(TypeDefinitionHandle handle) {
   var type=metadata.GetTypeDefinition(handle);string name=metadata.GetString(type.Name);
   var parent=type.GetDeclaringType();
   if(!parent.IsNil)return TypeName(parent)+"+"+name;
   string ns=metadata.GetString(type.Namespace);return ns.Length>0?ns+"."+name:name;
  }
  int methods=0, bodies=0;
  foreach(var handle in metadata.TypeDefinitions) {
   var type=metadata.GetTypeDefinition(handle);string owner=TypeName(handle);
   foreach(var methodHandle in type.GetMethods()) {
    var method=metadata.GetMethodDefinition(methodHandle);
    string? bodyError=null, ilHash=null, importModule=null, importName=null;
    int? ilBytes=null,maxStack=null,exceptionRegions=null;
    if(method.RelativeVirtualAddress!=0) {
     try {var body=pe.GetMethodBody(method.RelativeVirtualAddress);var il=body.GetILBytes()!;ilBytes=il.Length;maxStack=body.MaxStack;exceptionRegions=body.ExceptionRegions.Length;ilHash=Convert.ToHexString(SHA256.HashData(il)).ToLowerInvariant();bodies++;}
     catch(Exception error){bodyError=error.Message;}
    }
    if(method.Attributes.HasFlag(MethodAttributes.PinvokeImpl)) {
     var import=method.GetImport();importName=metadata.GetString(import.Name);
     if(!import.Module.IsNil)importModule=metadata.GetString(metadata.GetModuleReference(import.Module).Name);
    }
    output.WriteLine(JsonSerializer.Serialize(new{kind="method",path,sha256=hash,owner,name=metadata.GetString(method.Name),token=MetadataTokens.GetToken(methodHandle),rva=method.RelativeVirtualAddress,attributes=method.Attributes.ToString(),implementation=method.ImplAttributes.ToString(),signature=Convert.ToHexString(metadata.GetBlobBytes(method.Signature)),ilBytes,maxStack,exceptionRegions,ilHash,bodyError,importModule,importName}));methods++;
   }
  }
  output.WriteLine(JsonSerializer.Serialize(new{kind="module",path,sha256=hash,status="metadata_parsed",types=metadata.TypeDefinitions.Count,methods,bodies}));
 }catch(Exception error){output.WriteLine(JsonSerializer.Serialize(new{kind="module",path,status="failed",error=error.ToString()}));}
 output.Flush();
}
