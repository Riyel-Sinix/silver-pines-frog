"""Disassemble GameAssembly.dll functions by RVA with IL2CPP symbol annotations.

usage: python -I disasm.py <GameAssembly.dll> <symbols.pkl> <rva|Name$$Method> [...]
Function bounds come from the x64 .pdata table (falls back to int3 padding for leaf functions).
"""
import bisect
import pickle
import struct
import sys

import capstone
import pefile


class Image:
    def __init__(self, path):
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.data = open(path, "rb").read()
        self.sections = [
            (s.VirtualAddress, s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData, s.SizeOfRawData,
             s.Name.rstrip(b"\0").decode())
            for s in self.pe.sections
        ]
        exc = self.pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
        raw = self.read(exc.VirtualAddress, exc.Size)
        self.funcs = sorted(struct.iter_unpack("<III", raw))
        self.starts = [f[0] for f in self.funcs]

    def off(self, rva):
        for va, end, ptr, size, _ in self.sections:
            if va <= rva < end and rva - va < size:
                return ptr + (rva - va)
        return None

    def read(self, rva, n):
        o = self.off(rva)
        return self.data[o:o + n] if o is not None else b""

    def section_of(self, rva):
        for va, end, _, _, name in self.sections:
            if va <= rva < end:
                return name
        return None

    def chained(self, unwind_rva):
        hdr = self.read(unwind_rva, 1)
        return bool(hdr) and (hdr[0] >> 3) & 0x4  # UNW_FLAG_CHAININFO

    def bounds(self, rva):
        i = bisect.bisect_right(self.starts, rva) - 1
        if i >= 0 and self.funcs[i][0] <= rva < self.funcs[i][1]:
            start, end = self.funcs[i][0], self.funcs[i][1]
            # MSVC splits one function into several .pdata entries (chained unwind info)
            j = i + 1
            while j < len(self.funcs) and self.funcs[j][0] == end and self.chained(self.funcs[j][2]):
                end = self.funcs[j][1]
                j += 1
            return start, end
        # leaf function: scan to int3 padding
        buf = self.read(rva, 0x400)
        end = buf.find(b"\xcc\xcc")
        return rva, rva + (end if end > 0 else 0x100)


def main():
    img = Image(sys.argv[1])
    syms = pickle.load(open(sys.argv[2], "rb"))
    methods, meta = syms["methods"], syms["meta"]
    by_name = {}
    for a, n in methods.items():
        by_name.setdefault(n, a)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    for arg in sys.argv[3:]:
        rva = int(arg, 16) if arg.lower().startswith("0x") else by_name.get(arg)
        if rva is None:
            print(f"### {arg}: unknown")
            continue
        start, end = img.bounds(rva)
        print(f"### {methods.get(start, '?')}  RVA 0x{start:X}-0x{end:X} ({end - start} bytes)")
        code = img.read(start, end - start)
        for ins in md.disasm(code, start):
            note = ""
            for op in ins.operands:
                tgt = None
                if op.type == capstone.x86.X86_OP_IMM and ins.group(capstone.CS_GRP_JUMP) or op.type == capstone.x86.X86_OP_IMM and ins.group(capstone.CS_GRP_CALL):
                    tgt = op.imm
                elif op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    tgt = ins.address + ins.size + op.mem.disp
                if tgt is not None:
                    if tgt in methods:
                        note = f"  ; {methods[tgt]}"
                    elif tgt in meta:
                        note = f"  ; [{meta[tgt]}]"
                    elif ins.group(capstone.CS_GRP_CALL) or ins.group(capstone.CS_GRP_JUMP):
                        if not (start <= tgt < end):
                            note = f"  ; -> 0x{tgt:X}"
                    else:
                        note = f"  ; {img.section_of(tgt)}:0x{tgt:X}"
            print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<34} {ins.mnemonic} {ins.op_str}{note}")
        print()


if __name__ == "__main__":
    main()
