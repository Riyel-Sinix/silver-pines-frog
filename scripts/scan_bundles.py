"""Scan every bundle in a folder for Sprite/Texture2D objects whose names match a regex.

usage: python -P -E scan_bundles.py <folder> <regex> [skip-substring]
"""
import os
import re
import sys

import UnityPy


def main():
    folder, rx = sys.argv[1], re.compile(sys.argv[2], re.I)
    skip = sys.argv[3] if len(sys.argv) > 3 else None
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".bundle") or (skip and skip in fn):
            continue
        try:
            env = UnityPy.load(os.path.join(folder, fn))
        except Exception as e:  # noqa: BLE001
            print(f"!! {fn}: {e}")
            continue
        hits = []
        for o in env.objects:
            if o.type.name in ("Sprite", "Texture2D"):
                try:
                    n = o.peek_name() if hasattr(o, "peek_name") else o.read().m_Name
                except Exception:  # noqa: BLE001
                    n = "?"
                if n and rx.search(n):
                    hits.append(f"{o.type.name[0]}:{n}")
        if hits:
            print(f"{fn}  ({len(hits)})  {hits[:8]}")


if __name__ == "__main__":
    main()
