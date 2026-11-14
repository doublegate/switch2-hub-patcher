// Seed a raw 64 KiB 8051 bank: disassemble vectors and every LCALL/LJMP target that
// lands on non-erased bytes, then create functions there. Prints counts.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*;
import java.util.*;

public class SeedFunctions extends GhidraScript {
    @Override
    public void run() throws Exception {
        AddressSpace code = currentProgram.getAddressFactory().getAddressSpace("CODE");
        Memory mem = currentProgram.getMemory();
        byte[] img = new byte[0x10000];
        mem.getBytes(code.getAddress(0), img);
        Map<Integer, Integer> targets = new TreeMap<>();
        for (int v : new int[] {0x00, 0x03, 0x0B, 0x13, 0x1B, 0x23, 0x2B}) targets.merge(v, 1, Integer::sum);
        for (int at = 0; at + 2 < 0x10000; at++) {
            int op = img[at] & 0xFF;
            if (op != 0x12 && op != 0x02) continue;
            int t = ((img[at + 1] & 0xFF) << 8) | (img[at + 2] & 0xFF);
            if (t < 0x0030 || (img[t] & 0xFF) == 0xFF) continue;
            targets.merge(t, 1, Integer::sum);
        }
        int made = 0;
        for (int t : targets.keySet()) {
            Address a = code.getAddress(t);
            if (getInstructionAt(a) == null) disassemble(a);
        }
        for (Map.Entry<Integer, Integer> e : targets.entrySet()) {
            Address a = code.getAddress(e.getKey());
            if (getInstructionAt(a) == null || getFunctionAt(a) != null) continue;
            if (getFunctionContaining(a) != null && e.getValue() < 2) continue;
            if (createFunction(a, null) != null) made++;
        }
        println("seed targets " + targets.size() + ", functions created " + made
            + ", total functions " + currentProgram.getFunctionManager().getFunctionCount());
    }
}
