"""Print one or more parsed types (fields with offsets, methods with RVAs).

usage: python -I show_type.py <game_types.json> <TypeName> [TypeName ...]
       a name ending in '*' matches as a prefix
"""
import json
import sys


def main():
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    for want in sys.argv[2:]:
        prefix = want.endswith("*")
        key = want.rstrip("*")
        hits = [t for t in data["types"] if (t["name"].startswith(key) if prefix else t["name"] == key)]
        if not hits:
            print(f"### {want}: not found\n")
        for t in hits:
            print(f"### [{t['idx']}] {t['decl']} {t['kind']} {t['ns'] + '.' if t['ns'] else ''}{t['name']} : {t['bases']}")
            for c in t["consts"]:
                print(f"    const {c['name']} = {c['value']}")
            for fl in t["fields"]:
                print(f"    +0x{fl['offset']:<4X} {fl['decl']} {fl['name']}")
            for m in t["methods"]:
                print(f"    {m['rva'] or '-':>10}  {m['sig']}")
            print()


if __name__ == "__main__":
    main()
