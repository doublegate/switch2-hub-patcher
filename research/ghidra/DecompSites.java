// Decompile the functions that contain the given CODE addresses; print callers too.
// Args: <out-file> <hexaddr> [hexaddr...]
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class DecompSites extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        PrintWriter out = new PrintWriter(new FileWriter(args[0]));
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        AddressSpace code = currentProgram.getAddressFactory().getAddressSpace("CODE");
        Set<Function> done = new LinkedHashSet<>();
        for (int i = 1; i < args.length; i++) {
            Address a = code.getAddress(Long.parseLong(args[i], 16));
            Function f = getFunctionContaining(a);
            if (f == null) {
                disassemble(a);
                f = getFunctionContaining(a);
                if (f == null) f = createFunction(a, null);  // cross-bank entry (stub target)
            }
            if (f == null) {
                out.println("== site " + args[i] + ": no function");
                continue;
            }
            out.println("== site " + args[i] + " -> " + f.getName() + " @ " + f.getEntryPoint());
            if (!done.add(f)) continue;
        }
        for (Function f : done) {
            out.println();
            out.println("################ " + f.getName() + " @ " + f.getEntryPoint()
                + "  size " + f.getBody().getNumAddresses());
            StringBuilder callers = new StringBuilder();
            for (Reference r : getReferencesTo(f.getEntryPoint())) {
                Function c = getFunctionContaining(r.getFromAddress());
                callers.append(" ").append(r.getFromAddress())
                    .append(c == null ? "" : "(" + c.getName() + ")");
            }
            out.println("callers:" + callers);
            DecompileResults res = dec.decompileFunction(f, 60, monitor);
            out.println(res.decompileCompleted() ? res.getDecompiledFunction().getC()
                : "decompile failed: " + res.getErrorMessage());
        }
        out.close();
    }
}
