"""Find RIP-relative code references to a GameAssembly.dll global (e.g. Foo_TypeInfo) and show their use.

usage: python -P -E xrefs.py <GameAssembly.dll> <symbols.pkl> <rva|MetadataName> [context_instructions]
"""
import pickle
import sys

import capstone
import numpy as np

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from disasm import Image  # noqa: E402


def find_refs(img, target):
    refs = []
    for va, end, ptr, size, name in img.sections:
        if name != ".text" and name != "il2cpp":
            continue
        buf = img.data[ptr:ptr + size]
        for align in range(4):
            n = (len(buf) - align) // 4
            ints = np.frombuffer(buf, dtype="<i4", count=n, offset=align).astype(np.int64)
            pos = va + align + 4 * np.arange(n, dtype=np.int64)  # RVA of the disp32 field
            for tail in (4, 5, 8):  # disp32 followed by nothing / imm8 / imm32
                hit = np.nonzero(ints + pos + tail == target)[0]
                refs.extend((int(pos[k]), tail) for k in hit)
    return sorted(set(refs))


def main():
    img = Image(sys.argv[1])
    syms = pickle.load(open(sys.argv[2], "rb"))
    methods, meta = syms["methods"], syms["meta"]
    arg = sys.argv[3]
    if arg.lower().startswith("0x"):
        target = int(arg, 16)
    else:
        target = next(a for a, n in meta.items() if n == arg)
    ctx = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    print(f"target 0x{target:X} ({meta.get(target, '?')})")
    for disp_rva, tail in find_refs(img, target):
        fstart, fend = img.bounds(disp_rva)
        # decode from function start to find the instruction that owns this displacement
        code = img.read(fstart, fend - fstart)
        insns = list(md.disasm(code, fstart))
        idx = next((i for i, ins in enumerate(insns) if ins.address < disp_rva < ins.address + ins.size), None)
        if idx is None:
            continue  # not an instruction boundary match (false positive)
        ins = insns[idx]
        is_branch = ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x")
        if ins.address + ins.size - tail != disp_rva or not ("rip" in ins.op_str or is_branch):
            continue
        print(f"--- {methods.get(fstart, '?')} (0x{fstart:X}) ref @0x{ins.address:X}")
        for j in insns[idx: idx + ctx]:
            print(f"    {j.address:08X}  {j.bytes.hex(' '):<30} {j.mnemonic} {j.op_str}")


if __name__ == "__main__":
    main()
