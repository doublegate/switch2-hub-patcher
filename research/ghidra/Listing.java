// Print disassembly for CODE ranges. Args: <out-file> <start-end> [start-end...] (hex)
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import java.io.*;

public class Listing extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        PrintWriter out = new PrintWriter(new FileWriter(args[0]));
        AddressSpace code = currentProgram.getAddressFactory().getAddressSpace("CODE");
        for (int i = 1; i < args.length; i++) {
            String[] r = args[i].split("-");
            Address s = code.getAddress(Long.parseLong(r[0], 16));
            Address e = code.getAddress(Long.parseLong(r[1], 16));
            disassemble(s);
            out.println("---- " + args[i]);
            Address a = s;
            while (a.compareTo(e) <= 0) {
                Instruction ins = getInstructionAt(a);
                if (ins == null) {
                    disassemble(a);
                    ins = getInstructionAt(a);
                }
                if (ins == null) {
                    out.printf("%s  db %02x%n", a, getByte(a) & 0xff);
                    a = a.add(1);
                    continue;
                }
                Function f = getFunctionAt(a);
                if (f != null) out.println(f.getName() + ":");
                out.printf("%s  %s%n", a, ins);
                a = ins.getMaxAddress().add(1);
            }
        }
        out.close();
    }
}
