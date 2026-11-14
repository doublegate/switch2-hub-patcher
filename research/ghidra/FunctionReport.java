// Whole-bank function report for an RTD2142 bank program.
// Args: <out-tsv> [hexaddr ...]. Functions are first created at the given addresses
// (for example cross-bank entry points found from the bank-call stubs). Then one row per
// function: entry, name, size, caller count, callee entries, XDATA (EXTMEM) reads and
// writes. research/ghidra/auto_names.py turns the report into subsystem-prefixed names.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class FunctionReport extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        AddressSpace code = currentProgram.getAddressFactory().getAddressSpace("CODE");
        int made = 0;
        for (int i = 1; i < args.length; i++) {
            Address a = code.getAddress(Long.parseLong(args[i], 16));
            if (getFunctionAt(a) != null) continue;
            if (getInstructionAt(a) == null) disassemble(a);
            if (getInstructionAt(a) != null && createFunction(a, null) != null) made++;
        }
        PrintWriter out = new PrintWriter(new FileWriter(args[0]));
        out.println("entry\tname\tsize\tcallers\tcallees\treads\twrites");
        int rows = 0;
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            Set<String> callees = new TreeSet<>(), reads = new TreeSet<>(), writes = new TreeSet<>();
            for (Instruction ins : currentProgram.getListing().getInstructions(f.getBody(), true)) {
                for (Reference r : ins.getReferencesFrom()) {
                    Address to = r.getToAddress();
                    String space = to.getAddressSpace().getName();
                    if (r.getReferenceType().isCall() && space.equals("CODE")) {
                        callees.add(String.format("%04x", to.getOffset()));
                    } else if (space.equals("EXTMEM")) {
                        String hex = String.format("%04x", to.getOffset());
                        if (r.getReferenceType().isWrite()) writes.add(hex);
                        if (r.getReferenceType().isRead() || !r.getReferenceType().isWrite()) reads.add(hex);
                    }
                }
            }
            int callers = 0;
            for (Reference r : getReferencesTo(f.getEntryPoint())) if (r.getReferenceType().isCall()) callers++;
            out.printf("%04x\t%s\t%d\t%d\t%s\t%s\t%s%n", f.getEntryPoint().getOffset(), f.getName(),
                f.getBody().getNumAddresses(), callers, String.join(",", callees),
                String.join(",", reads), String.join(",", writes));
            rows++;
        }
        out.close();
        println("functions created " + made + ", reported " + rows);
    }
}
