"""Find which objects in the given bundles contain any of the given byte strings (raw object data).

usage: python -P -E find_bytes.py <bundle> [<bundle> ...] -- <text> [<text> ...]
"""
import os
import sys
from collections import Counter

import UnityPy

AA = os.environ.get("SILVER_PINES", r"D:/Games/Silver Pines") + "/Carpenter_Data/StreamingAssets/aa/StandaloneWindows64"


def main():
    k = sys.argv.index("--")
    bundles, needles = sys.argv[1:k], [t.encode() for t in sys.argv[k + 1:]]
    for fn in bundles:
        path = fn if os.path.exists(fn) else os.path.join(AA, fn)
        env = UnityPy.load(path)
        types = Counter(o.type.name for o in env.objects)
        print(f"== {os.path.basename(path)}: {dict(types.most_common(12))}")
        for o in env.objects:
            raw = o.get_raw_data()
            hits = [n.decode() for n in needles if n in raw]
            if hits:
                try:
                    name = o.peek_name()
                except Exception:  # noqa: BLE001
                    name = "?"
                print(f"  {o.type.name:22s} {o.path_id:>22d} {name!s:40s} {hits}")


if __name__ == "__main__":
    main()
