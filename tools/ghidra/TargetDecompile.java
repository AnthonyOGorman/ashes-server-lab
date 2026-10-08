// Import the exact PE with -noanalysis, then analyze only named function ranges.
// Arguments: output-directory start-rva:end-rva [start-rva:end-rva ...]
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

public class TargetDecompile extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2 || args.length > 17) throw new IllegalArgumentException("Output and 1..16 bounded ranges required");
        Path output = Path.of(args[0]);
        Files.createDirectories(output);
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            for (int i = 1; i < args.length; i++) {
                String[] range = args[i].split(":");
                if (range.length != 2) throw new IllegalArgumentException("start:end required");
                long startRva = Long.decode(range[0]), endRva = Long.decode(range[1]);
                if (startRva < 0 || endRva <= startRva || endRva - startRva > 65536) throw new IllegalArgumentException("Range must be <=64KiB");
                Address start = currentProgram.getImageBase().add(startRva);
                Address end = currentProgram.getImageBase().add(endRva - 1);
                AddressSet body = new AddressSet(start, end);
                new DisassembleCommand(start, body, true).applyTo(currentProgram, monitor);
                Function function = getFunctionAt(start);
                if (function == null) function = currentProgram.getFunctionManager().createFunction("target_" + Long.toHexString(startRva), start, body, ghidra.program.model.symbol.SourceType.USER_DEFINED);
                DecompileResults result = decompiler.decompileFunction(function, 45, monitor);
                String text = "/* Exact PE entry range RVA " + range[0] + ".." + range[1] + "; targeted disassembly; decompiler may follow tail jumps outside this entry range; inferred types require validation. */\n";
                text += result.decompileCompleted() ? result.getDecompiledFunction().getC() : "/* Decompilation failed: " + result.getErrorMessage() + " */\n";
                Files.writeString(output.resolve("function_" + Long.toHexString(startRva) + ".c"), text, StandardCharsets.UTF_8);
                println("TARGET " + range[0] + " completed=" + result.decompileCompleted());
            }
        } finally { decompiler.dispose(); }
    }
}
