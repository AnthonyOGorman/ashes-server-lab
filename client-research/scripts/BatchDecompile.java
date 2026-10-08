// Manifest TSV: start-rva end-rva descriptive-label. Persistent isolated research project.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class BatchDecompile extends GhidraScript {
    public void run() throws Exception {
        String[] args=getScriptArgs();
        if(args.length<2||args.length>3)throw new IllegalArgumentException("manifest output-directory [timeout-seconds]");
        int timeout=args.length==3?Integer.parseInt(args[2]):30;
        if(timeout<1||timeout>300)throw new IllegalArgumentException("Timeout must be 1..300 seconds");
        List<String> lines=Files.readAllLines(Path.of(args[0]),StandardCharsets.UTF_8);
        if(lines.size()>256)throw new IllegalArgumentException("Use batches of <=256 ranges");
        Path output=Path.of(args[1]);Files.createDirectories(output);
        DecompInterface decompiler=new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            for(String line:lines) {
                monitor.checkCancelled();
                if(line.isBlank()||line.startsWith("#"))continue;
                String[] fields=line.split("\t",3);
                long begin=Long.decode(fields[0]),end=Long.decode(fields[1]);
                if(end<=begin||end-begin>65536)throw new IllegalArgumentException("Invalid range");
                Path resultFile=output.resolve("function_"+Long.toHexString(begin)+".c");
                if(Files.exists(resultFile)){println("SKIP "+fields[0]);continue;}
                try {
                    Address start=currentProgram.getImageBase().add(begin);
                    AddressSet body=new AddressSet(start,currentProgram.getImageBase().add(end-1));
                    new DisassembleCommand(start,body,true).applyTo(currentProgram,monitor);
                    Function function=getFunctionAt(start);
                    if(function==null)function=currentProgram.getFunctionManager().createFunction("candidate_"+Long.toHexString(begin),start,body,SourceType.USER_DEFINED);
                    DecompileResults result=decompiler.decompileFunction(function,timeout,monitor);
                    String header="/* Binary SHA256: "+currentProgram.getExecutableSHA256()+"\n * Candidate label: "+fields[2]+"\n * Entry range: "+fields[0]+".."+fields[1]+"\n * Inferred types and names require validation. */\n";
                    String text=result.decompileCompleted()?result.getDecompiledFunction().getC():"/* Decompilation failed: "+result.getErrorMessage()+" */\n";
                    Files.writeString(resultFile,header+text,StandardCharsets.UTF_8);
                    println("DECOMPILE "+fields[0]+" completed="+result.decompileCompleted());
                }catch(Exception e) {
                    Files.writeString(output.resolve("error_"+Long.toHexString(begin)+".txt"),e.toString());
                    println("FAILED "+fields[0]+" "+e);
                }
            }
        }finally{decompiler.dispose();}
    }
}
