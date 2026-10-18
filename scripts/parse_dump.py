"""Parse Il2CppDumper dump.cs into JSON (types, fields with offsets, methods with RVAs).

usage: python -I parse_dump.py <dump.cs> <out.json> [image_name ...]
"""
import json
import re
import sys

TYPE_RE = re.compile(
    r"^(?P<decl>.*?)\b(?P<kind>class|struct|enum|interface)\s+(?P<name>[^:{]+?)"
    r"(?:\s*:\s*(?P<bases>.+?))?\s*//\s*TypeDefIndex:\s*(?P<idx>\d+)\s*$"
)
FIELD_RE = re.compile(r"^\s+(?P<decl>.+?)\s+(?P<name>[^\s;]+);\s*//\s*0x(?P<off>[0-9A-Fa-f]+)\s*$")
CONST_RE = re.compile(r"^\s+(?P<decl>.*\bconst\b.+?)\s+(?P<name>[^\s=]+)\s*=\s*(?P<val>.+);\s*$")
RVA_RE = re.compile(r"^\s+// RVA: (?P<rva>0x[0-9A-Fa-f]+|-1) Offset: (?P<off>0x[0-9A-Fa-f]+|-1) VA: (?P<va>0x[0-9A-Fa-f]+|-1)")
METHOD_RE = re.compile(r"^\s+(?P<sig>[^/].*\))\s*\{\s*\}\s*$")


def main():
    src, out = sys.argv[1], sys.argv[2]
    wanted = set(sys.argv[3:])
    images = []  # (name, first_idx)
    types = []
    cur = None
    pending_rva = None
    namespace = ""
    with open(src, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("// Image "):
                m = re.match(r"// Image (\d+): (.+?) - (\d+)", line)
                images.append((m.group(2), int(m.group(3))))
                continue
            if line.startswith("// Namespace: "):
                namespace = line[len("// Namespace: "):].strip()
                continue
            m = TYPE_RE.match(line)
            if m and not line.startswith("\t"):
                idx = int(m.group("idx"))
                img = None
                for name, first in images:
                    if first <= idx:
                        img = name
                cur = {
                    "idx": idx,
                    "image": img,
                    "ns": namespace,
                    "kind": m.group("kind"),
                    "name": m.group("name").strip(),
                    "decl": m.group("decl").strip(),
                    "bases": (m.group("bases") or "").strip(),
                    "fields": [],
                    "consts": [],
                    "methods": [],
                }
                types.append(cur)
                pending_rva = None
                continue
            if cur is None:
                continue
            m = RVA_RE.match(line)
            if m:
                pending_rva = m.group("rva")
                continue
            m = FIELD_RE.match(line)
            if m and "(" not in m.group("decl"):
                cur["fields"].append({
                    "name": m.group("name"),
                    "decl": m.group("decl").strip(),
                    "offset": int(m.group("off"), 16),
                    "static": " static " in f" {m.group('decl')} ",
                })
                continue
            m = CONST_RE.match(line)
            if m:
                cur["consts"].append({"name": m.group("name"), "decl": m.group("decl").strip(), "value": m.group("val").strip()})
                continue
            m = METHOD_RE.match(line)
            if m:
                cur["methods"].append({"sig": m.group("sig").strip(), "rva": pending_rva})
                pending_rva = None
                continue
    if wanted:
        types = [t for t in types if t["image"] in wanted]
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"images": images, "types": types}, f, ensure_ascii=False)
    print(f"{len(types)} types written to {out}")


if __name__ == "__main__":
    main()
