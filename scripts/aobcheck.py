"""Check CE signatures, patch bytes and IL2CPP references in GameAssembly.dll.

usage: python -P -E aobcheck.py <GameAssembly.dll> <symbols.pkl> <patterns.json>
patterns.json: {"NAME": {"aob": "48 8B 05 ?? ...", "expect_rva": "0x...", "patch_off": 0, "patch_len": 0}, ...}
Optional expect_method validates the enclosing IL2CPP method; rip_ref validates a RIP-relative
metadata reference (ins_off, disp_off, ins_len, expect_meta); patch_bytes accepts AOB wildcards.
Only executable sections are scanned, matching the table's '+X' protection filter.
"""
import json
import pickle
import re
import struct
import sys

import capstone
import pefile

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from disasm import Image  # noqa: E402


def to_regex(aob):
    parts = []
    for tok in aob.split():
        parts.append(b"." if tok in ("??", "?", "*") else re.escape(bytes([int(tok, 16)])))
    return re.compile(b"".join(parts), re.DOTALL)


def main():
    img = Image(sys.argv[1])
    syms = pickle.load(open(sys.argv[2], "rb"))
    methods = syms["methods"]
    by_name = {}
    for rva, name in methods.items():
        by_name.setdefault(name, []).append(rva)
    pats = json.load(open(sys.argv[3], encoding="utf-8"))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    ok = True
    for name, p in pats.items():
        rx = to_regex(p["aob"])
        hits = []
        for section, (va, end, ptr, size, sec) in zip(img.pe.sections, img.sections):
            # Match AOBScanModuleUnique(..., '+X') in SilverPines.CT.
            if not section.Characteristics & pefile.SECTION_CHARACTERISTICS["IMAGE_SCN_MEM_EXECUTE"]:
                continue
            blob = img.data[ptr:ptr + size]
            for m in rx.finditer(blob):
                hits.append((va + m.start(), sec))
        exp = int(p["expect_rva"], 16) if p.get("expect_rva") else None
        issues = []
        if len(hits) != 1:
            issues.append(f"NOT UNIQUE ({len(hits)} hits)")
        elif exp is not None and hits[0][0] != exp:
            issues.append(f"WRONG LOCATION (expected 0x{exp:X})")
        if len(hits) == 1:
            rva = hits[0][0]
            if p.get("expect_method"):
                # A method can have several .pdata fragments or shared/overloaded names.
                ranges = [img.bounds(a) for a in by_name.get(p["expect_method"], [])]
                if not any(start <= rva < end for start, end in ranges):
                    issues.append(f"WRONG METHOD (expected {p['expect_method']})")
            if p.get("rip_ref"):
                ref = p["rip_ref"]
                ins = rva + ref.get("ins_off", 0)
                disp = struct.unpack("<i", img.read(ins + ref["disp_off"], 4))[0]
                target = ins + ref["ins_len"] + disp
                if syms["meta"].get(target) != ref["expect_meta"]:
                    issues.append(f"WRONG REFERENCE (0x{target:X}, expected {ref['expect_meta']})")
            if p.get("patch_len"):
                off, length = p["patch_off"], p["patch_len"]
                data = img.read(rva + off, length)
                if p.get("patch_bytes") and not to_regex(p["patch_bytes"]).fullmatch(data):
                    issues.append("WRONG PATCH BYTES")
                prefix = img.read(rva, off)
                if (sum(i.size for i in md.disasm(prefix, rva)) != off or
                        sum(i.size for i in md.disasm(data, rva + off)) != length):
                    issues.append("PATCH SPLITS AN INSTRUCTION")
        status = "; ".join(issues) if issues else "OK"
        ok = ok and not issues
        print(f"[{status}] {name}: {len(p['aob'].split())} bytes")
        for rva, sec in hits[:8]:
            fstart, _ = img.bounds(rva)
            extra = ""
            if p.get("patch_len"):
                b = img.read(rva + p["patch_off"], p["patch_len"])
                extra = f" patch@+0x{p['patch_off']:X} = {b.hex(' ').upper()}"
            owner = p.get("expect_method") if not issues else None
            print(f"      {sec}:0x{rva:X} in {owner or methods.get(fstart, '?')}{extra}")
    print("ALL OK" if ok else "PROBLEMS FOUND")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
