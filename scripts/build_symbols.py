"""Build a compact RVA -> name symbol index from Il2CppDumper script.json.

usage: python -I build_symbols.py <script.json> <symbols.pkl>
"""
import json
import pickle
import sys


def main():
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    methods = {}
    for m in data["ScriptMethod"]:
        methods.setdefault(m["Address"], m["Name"])
    meta = {}
    for m in data["ScriptMetadata"]:
        meta[m["Address"]] = m["Name"]
    for m in data["ScriptMetadataMethod"]:
        meta[m["Address"]] = "MethodInfo:" + m["Name"]
    for s in data["ScriptString"]:
        v = s["Value"]
        meta[s["Address"]] = "str:" + (v if len(v) < 60 else v[:57] + "...")
    with open(sys.argv[2], "wb") as f:
        pickle.dump({"methods": methods, "meta": meta}, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"methods={len(methods)} meta={len(meta)}")


if __name__ == "__main__":
    main()
