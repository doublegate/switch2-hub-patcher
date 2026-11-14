// Apply research/rtd2142_symbols.tsv (and optional extra TSVs) to one RTD2142 bank program.
// Args: <bank number> <tsv> [tsv...]. Rows: bank, space, hex address, name, note.
// Functions are renamed; other addresses get a primary label. Notes become comments.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.nio.file.*;

public class RenameSymbols extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String bank = args[0];
        int functions = 0, labels = 0;
        for (int i = 1; i < args.length; i++) {
            for (String line : Files.readAllLines(Paths.get(args[i]))) {
                if (line.isBlank() || line.startsWith("#")) continue;
                String[] f = line.split("\t");
                if (f.length < 4 || !(f[0].equals("*") || f[0].equals(bank))) continue;
                AddressSpace space = currentProgram.getAddressFactory().getAddressSpace(f[1]);
                if (space == null) {
                    printerr("unknown space " + f[1] + " in: " + line);
                    continue;
                }
                Address a = space.getAddress(Long.parseLong(f[2], 16));
                String note = f.length > 4 ? f[4] : "";
                Function fn = f[1].equals("CODE") ? getFunctionAt(a) : null;
                if (fn != null) {
                    fn.setName(f[3], SourceType.USER_DEFINED);
                    if (!note.isEmpty()) fn.setComment(note);
                    functions++;
                } else {
                    Symbol s = createLabel(a, f[3], true, SourceType.USER_DEFINED);
                    if (s != null) labels++;
                    if (!note.isEmpty()) setEOLComment(a, note);
                }
            }
        }
        println("bank " + bank + ": renamed " + functions + " functions, " + labels + " labels");
    }
}
