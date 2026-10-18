"""List AnimationClip / AnimatorController / AnimatorOverrideController names per bundle.

usage: python -P -E scan_clips.py <folder> <regex> [out.txt]
"""
import os
import re
import sys

import UnityPy


def main():
    folder, rx = sys.argv[1], re.compile(sys.argv[2], re.I)
    out = open(sys.argv[3], "w", encoding="utf-8") if len(sys.argv) > 3 else sys.stdout
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".bundle"):
            continue
        try:
            env = UnityPy.load(os.path.join(folder, fn))
        except Exception as e:  # noqa: BLE001
            print(f"!! {fn}: {e}", file=out)
            continue
        hits = []
        for o in env.objects:
            if o.type.name in ("AnimationClip", "AnimatorController", "AnimatorOverrideController"):
                try:
                    n = o.peek_name()
                except Exception:  # noqa: BLE001
                    n = "?"
                if n and rx.search(n):
                    hits.append(f"{o.type.name[:5]}:{n}")
        if hits:
            print(f"{fn}  ({len(hits)})  {hits}", file=out, flush=True)


if __name__ == "__main__":
    main()
