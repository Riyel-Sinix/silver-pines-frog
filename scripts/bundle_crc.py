"""Compute CRC32 candidates of a UnityFS bundle's uncompressed data and look them up in an Addressables catalog.

usage: python -P -E bundle_crc.py <catalog.bin> <bundle> [<bundle> ...]
"""
import struct
import sys
import zlib

import lz4.block


def read_cstr(b, o):
    e = b.index(b"\0", o)
    return b[o:e].decode(), e + 1


def decompress_bundle(path):
    b = open(path, "rb").read()
    sig, o = read_cstr(b, 0)
    assert sig == "UnityFS", sig
    version = struct.unpack_from(">I", b, o)[0]
    o += 4
    _, o = read_cstr(b, o)
    _, o = read_cstr(b, o)
    size, csize, usize, flags = struct.unpack_from(">qIII", b, o)
    o += 20
    if version >= 7:
        o = (o + 15) // 16 * 16
    if flags & 0x80:
        info_raw = b[len(b) - csize:]
        data_start = o
    else:
        info_raw = b[o:o + csize]
        data_start = o + csize
    comp = flags & 0x3F
    info = info_raw if comp == 0 else lz4.block.decompress(info_raw, uncompressed_size=usize)
    p = 16
    nblocks = struct.unpack_from(">i", info, p)[0]
    p += 4
    blocks = []
    for _ in range(nblocks):
        u, c, f = struct.unpack_from(">IIH", info, p)
        p += 10
        blocks.append((u, c, f))
    if flags & 0x200:
        data_start = (data_start + 15) // 16 * 16
    out = bytearray()
    q = data_start
    for u, c, f in blocks:
        chunk = b[q:q + c]
        q += c
        out += chunk if (f & 0x3F) == 0 else lz4.block.decompress(chunk, uncompressed_size=u)
    nnodes = struct.unpack_from(">i", info, p)[0]
    p += 4
    nodes = []
    for _ in range(nnodes):
        off, sz, nf = struct.unpack_from(">qqI", info, p)
        p += 20
        name, p = read_cstr(info, p)
        nodes.append((name, off, sz))
    return bytes(out), nodes


def main():
    cat = open(sys.argv[1], "rb").read()
    for path in sys.argv[2:]:
        data, nodes = decompress_bundle(path)
        cands = {"all-data": zlib.crc32(data)}
        for name, off, sz in nodes:
            cands[name] = zlib.crc32(data[off:off + sz])
        print(path.rsplit("/", 1)[-1], f"uncompressed={len(data)}")
        for k, v in cands.items():
            pos = cat.find(struct.pack("<I", v))
            print(f"   crc32[{k}] = {v:08X}  {'FOUND in catalog @' + hex(pos) if pos >= 0 else 'not in catalog'}")


if __name__ == "__main__":
    main()
