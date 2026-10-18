"""Find the bundle that holds a CAB (the archive name a PPtr's external file entry points at), reading only each
bundle's header and directory, so all ~2400 bundles take a couple of seconds.

usage: python -P -E find_cab.py CAB-0123456789abcdef0123456789abcdef
"""
import os
import struct
import sys

from UnityPy.helpers import CompressionHelper

GAME = os.environ.get("SILVER_PINES", r"D:/Games/Silver Pines")  # the game folder; set SILVER_PINES if elsewhere
AA = GAME + "/Carpenter_Data/StreamingAssets/aa/StandaloneWindows64"

def nodes(path):
    """Node names (CAB, .resS, ...) of one UnityFS bundle."""
    with open(path, "rb") as f:
        data = f.read(4096)
        if not data.startswith(b"UnityFS\0"):
            return []
        p = 8
        ver = struct.unpack_from(">I", data, p)[0]; p += 4
        for _ in range(2):
            p = data.index(b"\0", p) + 1
        size, csize, usize, flags = struct.unpack_from(">qIII", data, p); p += 20
        if ver >= 7:
            p = (p + 15) // 16 * 16
        if flags & 0x80:
            f.seek(-csize, 2); blk = f.read(csize)
        else:
            f.seek(p); blk = f.read(csize)
    comp = flags & 0x3F
    if comp in (2, 3):
        blk = CompressionHelper.decompress_lz4(blk, usize)
    elif comp == 1:
        blk = CompressionHelper.decompress_lzma(blk)
    q = 16
    nb = struct.unpack_from(">i", blk, q)[0]; q += 4 + nb * 10
    nn = struct.unpack_from(">i", blk, q)[0]; q += 4
    out = []
    for _ in range(nn):
        q += 20
        e = blk.index(b"\0", q); out.append(blk[q:e].decode()); q = e + 1
    return out

def main():
    want = sys.argv[1].lower()
    for fn in sorted(os.listdir(AA)):
        if fn.endswith(".bundle"):
            try:
                ns = nodes(os.path.join(AA, fn))
            except (OSError, ValueError, struct.error):
                continue
            if any(n.lower() == want for n in ns):
                print(fn, ns)


if __name__ == "__main__":
    main()
