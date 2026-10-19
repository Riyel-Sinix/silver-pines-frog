"""Read a cached Steam depot manifest without Steam, network access or game writes.

usage: python -P -E scripts/steam_manifest.py <depot_manifest> <output.json>

Exports plaintext file names, original sizes and content SHA1s from Steam's
protobuf manifest sections. Encrypted file names and legacy binary manifests
are rejected. The manifest signature is inventoried, not authenticated.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path, PurePosixPath


PAYLOAD = 0x71F617D0
METADATA = 0x1F4812BE
SIGNATURE = 0x1B81B817
END = 0x32C415AB


def varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("Truncated protobuf varint")
        byte = data[offset]
        offset += 1
        if shift == 63 and byte > 1:
            raise ValueError("Protobuf varint exceeds 64 bits")
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
    raise ValueError("Invalid protobuf varint")


def fields(data):
    """Yield protobuf (field number, wire type, value), checking every boundary."""
    offset = 0
    while offset < len(data):
        tag, offset = varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError("Invalid zero protobuf field number")
        if wire == 0:
            value, offset = varint(data, offset)
        else:
            if wire == 2:
                length, offset = varint(data, offset)
            elif wire in (1, 5):
                length = 8 if wire == 1 else 4
            else:
                raise ValueError(f"Unsupported protobuf wire type: {wire}")
            end = offset + length
            if end > len(data):
                raise ValueError("Truncated protobuf field")
            value = data[offset:end]
            offset = end
        yield number, wire, value


def parse_manifest(path):
    path = Path(path)
    raw = path.read_bytes()
    offset = 0
    sections = {}
    while offset + 4 <= len(raw):
        magic = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        if magic == END:
            if offset != len(raw):
                raise ValueError("Unexpected bytes after Steam manifest end marker")
            break
        if magic not in (PAYLOAD, METADATA, SIGNATURE) or magic in sections:
            raise ValueError(f"Unknown or duplicate Steam manifest section: 0x{magic:X}")
        if offset + 4 > len(raw):
            raise ValueError("Truncated Steam manifest section length")
        length = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        if offset + length > len(raw):
            raise ValueError("Truncated Steam manifest section")
        sections[magic] = raw[offset:offset + length]
        offset += length
    else:
        raise ValueError("Missing Steam manifest end marker")
    if PAYLOAD not in sections or METADATA not in sections:
        raise ValueError("Missing Steam manifest payload or metadata")

    metadata = {number: value for number, wire, value in fields(sections[METADATA]) if wire == 0}
    if metadata.get(4, 0):
        raise ValueError("Manifest file names are encrypted")
    files = []
    seen = set()
    for number, wire, message in fields(sections[PAYLOAD]):
        if number != 1 or wire != 2:
            continue
        mapping = {}
        chunks = 0
        for key, field_wire, value in fields(message):
            if key == 6 and field_wire == 2:
                chunks += 1
            elif key in (1, 4, 5, 7) and field_wire == 2:
                mapping[key] = value
            elif key in (2, 3) and field_wire == 0:
                mapping[key] = value
        name = mapping.get(1, b"").decode("utf-8").replace("\\", "/")
        if not name or name.startswith("/") or ".." in PurePosixPath(name).parts:
            raise ValueError(f"Invalid manifest path: {name!r}")
        if name.casefold() in seen:
            raise ValueError(f"Duplicate manifest path: {name}")
        seen.add(name.casefold())
        digest = mapping.get(5, b"")
        flags = mapping.get(3, 0)
        if digest and len(digest) != 20:
            raise ValueError(f"Invalid SHA1 for {name}")
        if not flags & 64 and not digest:
            raise ValueError(f"Missing file SHA1 for {name}")
        files.append({
            "path": name,
            "size": mapping.get(2, 0),
            "flags": flags,
            "sha1": digest.hex() if digest else None,
            "chunks": chunks,
        })
    disk_size = sum(f["size"] for f in files if not f["flags"] & 64)
    if metadata.get(5) != disk_size:
        raise ValueError(f"Manifest total size mismatch: {disk_size} != {metadata.get(5)}")
    return {
        "source": str(path.resolve()),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "depot_id": metadata.get(1),
        "manifest_id": str(metadata.get(2)),
        "creation_time_unix": metadata.get(3),
        "filenames_encrypted": False,
        "size_original": disk_size,
        "size_compressed": metadata.get(6),
        "unique_chunks": metadata.get(7),
        "signature_size": len(sections.get(SIGNATURE, b"")),
        "signature_authenticated": False,
        "file_count": sum(not f["flags"] & 64 for f in files),
        "mapping_count": len(files),
        "files": files,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = parse_manifest(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Depot {result['depot_id']}, manifest {result['manifest_id']}: "
          f"{result['file_count']} files, {result['size_original']} bytes -> {args.output}")


if __name__ == "__main__":
    main()
