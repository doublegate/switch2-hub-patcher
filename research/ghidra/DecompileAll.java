// Decompile every function of an RTD2142 bank program into one C-like file.
// Args: <out-file>. Each function is preceded by its address, size, callers and comment.
// The output is derived from vendor firmware: keep it outside the repository.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;

public class DecompileAll extends GhidraScript {
    @Override
    public void run() throws Exception {
        PrintWriter out = new PrintWriter(new FileWriter(getScriptArgs()[0]));
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        int ok = 0, failed = 0;
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            StringBuilder callers = new StringBuilder();
            for (Reference r : getReferencesTo(f.getEntryPoint())) {
                if (!r.getReferenceType().isCall()) continue;
                Function c = getFunctionContaining(r.getFromAddress());
                callers.append(' ').append(c == null ? r.getFromAddress().toString() : c.getName());
            }
            out.println();
            out.println("/* ==== " + f.getName() + " @ " + f.getEntryPoint() + "  size "
                + f.getBody().getNumAddresses() + "  callers:" + callers + " */");
            DecompileResults res = dec.decompileFunction(f, 60, monitor);
            if (res.decompileCompleted()) {
                out.println(res.getDecompiledFunction().getC());
                ok++;
            } else {
                out.println("/* decompile failed: " + res.getErrorMessage() + " */");
                failed++;
            }
        }
        out.close();
        println("decompiled " + ok + ", failed " + failed);
    }
}
