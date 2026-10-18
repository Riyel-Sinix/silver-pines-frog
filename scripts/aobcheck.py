"""Check that Cheat Engine AOB patterns are unique in GameAssembly.dll and land where expected.

usage: python -P -E aobcheck.py <GameAssembly.dll> <symbols.pkl> <patterns.json>
patterns.json: {"NAME": {"aob": "48 8B 05 ?? ...", "expect_rva": "0x...", "patch_off": 0, "patch_len": 0}, ...}
"""
import json
import pickle
import re
import sys

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
    pats = json.load(open(sys.argv[3], encoding="utf-8"))
    ok = True
    for name, p in pats.items():
        rx = to_regex(p["aob"])
        hits = []
        for va, end, ptr, size, sec in img.sections:
            blob = img.data[ptr:ptr + size]
            for m in rx.finditer(blob):
                hits.append((va + m.start(), sec))
        exp = int(p["expect_rva"], 16) if p.get("expect_rva") else None
        status = "OK"
        if len(hits) != 1:
            status = f"NOT UNIQUE ({len(hits)} hits)"
            ok = False
        elif exp is not None and hits[0][0] != exp:
            status = f"WRONG LOCATION (expected 0x{exp:X})"
            ok = False
        print(f"[{status}] {name}: {len(p['aob'].split())} bytes")
        for rva, sec in hits[:8]:
            fstart, _ = img.bounds(rva)
            extra = ""
            if p.get("patch_len"):
                b = img.read(rva + p["patch_off"], p["patch_len"])
                extra = f" patch@+0x{p['patch_off']:X} = {b.hex(' ').upper()}"
            print(f"      {sec}:0x{rva:X} in {methods.get(fstart, '?')}{extra}")
    print("ALL OK" if ok else "PROBLEMS FOUND")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
