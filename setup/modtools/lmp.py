#!/usr/bin/env python3
"""
lmp.py - Read, list, extract and build Snowblind .lmp archives (Justice League Heroes).

Format (same on Xbox and PSP):
  u32 count
  count x { u32 name_offset, u32 data_offset, u32 size }
  12 zero bytes (terminator entry)
  name strings (NUL-terminated), then file data aligned to 0x80

Usage:
  python lmp.py list    file.lmp
  python lmp.py extract file.lmp outdir
  python lmp.py build   indir file.lmp      (rebuild from an extracted folder; order kept via _order.txt)
"""
import os
import struct
import sys

ALIGN = 0x80


def read(path):
    return read_bytes(open(path, "rb").read())


def read_bytes(d):
    n = struct.unpack_from("<I", d, 0)[0]
    out = []
    for i in range(n):
        no, do, sz = struct.unpack_from("<III", d, 4 + i * 12)
        end = d.index(b"\0", no)
        out.append((d[no:end].decode("latin-1"), d[do:do + sz], do))
    return out


def build(entries, path):
    """entries: list of (name, bytes)"""
    n = len(entries)
    names = b"".join(nm.encode("latin-1") + b"\0" for nm, _ in entries)
    hdr = 4 + n * 12 + 12
    pos = hdr + len(names)
    pos = (pos + ALIGN - 1) // ALIGN * ALIGN
    table, blob, name_off, seen = [], bytearray(), hdr, {}
    for i, (nm, data) in enumerate(entries):
        if data in seen:  # identical data is stored once and shared
            table.append((name_off, seen[data], len(data)))
            name_off += len(nm) + 1
            continue
        seen[data] = pos
        table.append((name_off, pos, len(data)))
        name_off += len(nm) + 1
        blob += data
        pad = (-len(data)) % ALIGN if i < n - 1 else 0
        blob += b"\0" * pad
        pos += len(data) + pad
    out = bytearray(struct.pack("<I", n))
    for t in table:
        out += struct.pack("<III", *t)
    out += b"\0" * 12
    out += names
    out += b"\0" * ((-len(out)) % ALIGN)
    out += blob
    open(path, "wb").write(out)


def main():
    cmd = sys.argv[1]
    if cmd == "list":
        for name, data, off in read(sys.argv[2]):
            print(f"{off:08X} {len(data):8d}  {name}")
    elif cmd == "extract":
        out = sys.argv[3]
        os.makedirs(out, exist_ok=True)
        ents = read(sys.argv[2])
        with open(os.path.join(out, "_order.txt"), "w") as f:
            for name, data, _ in ents:
                open(os.path.join(out, name), "wb").write(data)
                f.write(name + "\n")
        print(f"{len(ents)} files -> {out}")
    elif cmd == "build":
        src = sys.argv[2]
        names = open(os.path.join(src, "_order.txt")).read().split()
        build([(n, open(os.path.join(src, n), "rb").read()) for n in names], sys.argv[3])
        print(f"{len(names)} files -> {sys.argv[3]}")


if __name__ == "__main__":
    main()
